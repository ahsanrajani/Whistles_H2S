#!/usr/bin/env python3
"""Guru Ears portal — JSON API.

    pip install -r requirements.txt
    npm run db:up && python app.py      -> http://127.0.0.1:5000

Flask serves only the versioned `/api/v1/*` JSON API (blueprint in `api/`); the
browser UI is the Next app in `apps/web/`, which proxies `/api/*` here with the
first-party session cookie. Persistence is Postgres via SQLAlchemy (`db/`);
collection and scoring run in real worker threads. Nothing here is simulated.
"""
import json
import os
import re
import secrets
import socket
import threading
import uuid
from datetime import datetime, timedelta, timezone

from flask import (Flask, abort, has_request_context, jsonify, request,
                   send_from_directory, session)
from flask_session import Session as FlaskSession
from dotenv import load_dotenv

from core import care_bridge, classify, collector, dm_sync, sentiment, sources
from db import repositories as repo
from db.bootstrap import ensure_schema, seed
from db.legacy import LegacyConn, operator_conn
from db.session import get_operator_session
from jobs import runner, scheduler, worker
import websession
from websession import idle
from obs import logs as obs_logs
from obs import metrics as obs_metrics

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(HERE, ".env")
load_dotenv(ENV_PATH)
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("GURU_SECRET_KEY", "guru-ears-poc-local-secret")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# Structured JSON logs + a per-request correlation id (X-Request-Id) on every
# line. Installed first so anything that logs during a request is correlated.
obs_logs.configure_logging()
obs_logs.install(app)
# Prometheus /metrics + /healthz + /readyz, request-latency hook, DB collector.
obs_metrics.install(app)


def _session_store():
    """Redis client for the server-side session store. `REDIS_URL` unset →
    in-process fakeredis: fine for the test suite and a throwaway local run,
    but it does not survive a restart and is not shared across processes, so
    dev/prod must set `REDIS_URL` (see `ops/compose/docker-compose.yml`)."""
    url = (os.environ.get("REDIS_URL") or "").strip()
    if url:
        import redis
        return redis.Redis.from_url(url)
    import fakeredis
    app.logger.warning("REDIS_URL unset — sessions are using in-process fakeredis.")
    return fakeredis.FakeStrictRedis()


# One Redis client for the whole process: Flask-Session (below) and the
# framework-neutral websession store (used by ported FastAPI routes in P1.10)
# read and write the same keys with the same wire format.
_session_redis = _session_store()
websession.configure(_session_redis)

app.config.update(
    SESSION_TYPE="redis",
    SESSION_REDIS=_session_redis,
    SESSION_KEY_PREFIX=websession.KEY_PREFIX,
    SESSION_PERMANENT=True,
    PERMANENT_SESSION_LIFETIME=timedelta(days=7),
)
FlaskSession(app)

from auth import oauth as _oauth       # noqa: E402  (needs app + config above)

_oauth.register(app)

_jobs = {}
_lock = threading.Lock()


def db():
    """The per-request DB handle, row-level-security enforced (role guru_app).
    The caller must `set_tenant(ws)` before querying tenant data."""
    return LegacyConn()


def db_operator():
    """A BYPASSRLS handle (role guru_operator) for the operator/admin surface
    and for system jobs — spans tenants by design."""
    return operator_conn()


def now():
    return datetime.now(timezone.utc).isoformat()


# Starter listening vocabulary offered in the onboarding wizard (step 3). Mirrors
# the banking context in entity.SEED but is generic enough to edit for any brand.
STARTER_CONTEXT = [
    r"\baccount\b", r"\bapp\b", r"\bservice\b", r"\bsupport\b", r"\bcustomer\b",
    r"\bbranch\b", r"\bcard\b", r"\bpayment\b", r"\btransfer\b", r"\bfees?\b",
    r"\bcomplaint\b", r"\bissue\b", r"\bhelp\b", r"\blogin\b", r"\bwebsite\b",
]


def slugify(name, c=None):
    """URL-safe slug for a workspace name, unique if a connection is given."""
    base = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-") or "workspace"
    if c is None:
        return base
    slug, n = base, 1
    while repo.workspaces.slug_taken(c.session, slug):
        n += 1
        slug = f"{base}-{n}"
    return slug


def phrase_regex(text):
    """`\\bword\\s+word\\b` for a plain phrase — tolerant of real whitespace."""
    words = [w for w in re.split(r"\s+", (text or "").strip()) if w]
    if not words:
        return ""
    return r"\b" + r"\s+".join(re.escape(w) for w in words) + r"\b"


def brand_patterns(name):
    """Auto-generate a match-rule set from a plain brand name for the wizard."""
    words = [w for w in re.split(r"\s+", (name or "").strip()) if w]
    spaced = r"\b" + r"\s*".join(re.escape(w) for w in words) + r"\b"
    joined = r"\b" + re.escape("".join(words)).lower() + r"\b"
    safe = [spaced] if words else []
    if len(words) > 1:
        safe.append(joined)
    return {"safe": safe, "gated": {}, "context": list(STARTER_CONTEXT),
            "exclude": []}


def init():
    """Bring the schema to head and seed first-boot data. Safe to call repeatedly."""
    ensure_schema()
    c = db_operator()          # seed writes across workspaces / shared config
    try:
        seed(c, now())
        # P2.7: one per-source collection tick per workspace
        from collection import schedule as _sched
        from core import owned_analytics as _owned
        for (wid,) in c.execute("SELECT id FROM workspace").fetchall():
            _sched.ensure_workspace_tick(c.session, wid)
            _owned.ensure_workspace_schedule(c.session, wid)
            dm_sync.ensure_workspace_schedule(c.session, wid)
            repo.projects.ensure_default(c.session, wid)
        c.commit()
    finally:
        c.close()


def keys(ws=None):
    """Effective credentials for a workspace: env var > workspace row > shared."""
    session = get_operator_session()
    try:
        k = repo.keys.shared_values(session)
        if ws:
            k.update(repo.keys.workspace_values(session, ws))
    finally:
        session.close()
    for var, _ in sources.KEYS:                 # env always wins
        if os.environ.get(var):
            k[var] = os.environ[var]
    from integrations.llm import vertex
    if vertex.enabled():                        # Vertex AI counts as "a model is configured"
        k["GOOGLE_API_KEY"] = vertex.SENTINEL
    return k


def persist_key(ws, var, val):
    """Upsert one allow-listed credential for a workspace (0 = shared)."""
    labels = dict(sources.KEYS)
    if var not in labels:
        abort(400, "Unknown API setting")
    if "\n" in (val or "") or "\r" in (val or ""):
        abort(400, "API setting values must be single-line")
    session = get_operator_session()
    try:
        repo.keys.upsert(session, workspace_id=ws, env_var=var, label=labels[var],
                         value=val or None, status="present" if val else "missing",
                         last_checked=now())
        session.commit()
    finally:
        session.close()


def audit(*, actor, tenant_id, action, target=None, before=None, after=None, ip=None):
    """Append one row to ``audit_event`` on its own committed transaction, so the
    record survives whatever the calling request does. ``before`` / ``after`` are
    JSON-serialised; ``ip`` is filled from the request when not given."""
    if ip is None and has_request_context():
        forwarded = request.headers.get("X-Forwarded-For", "")
        ip = forwarded.split(",")[0].strip() or request.remote_addr or None
    session = get_operator_session()
    try:
        repo.audit.record(
            session, actor=actor, tenant_id=tenant_id, action=action,
            target=target, at=now(),
            before=json.dumps(before) if before is not None else None,
            after=json.dumps(after) if after is not None else None, ip=ip)
        session.commit()
    finally:
        session.close()


def persist_env_value(var, value):
    """Persist one allow-listed provider setting to the local ignored .env."""
    allowed = {name for name, _ in sources.KEYS}
    if var not in allowed:
        abort(400, "Unknown API setting")
    if "\n" in value or "\r" in value:
        abort(400, "API setting values must be single-line")
    lines = []
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, encoding="utf-8") as env_file:
            lines = env_file.read().splitlines()
    replacement = f"{var}={value}"
    prefix = var + "="
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            lines[index] = replacement
            break
    else:
        if lines and lines[-1]:
            lines.append("")
        lines.append(replacement)
    temporary = ENV_PATH + ".tmp"
    with open(temporary, "w", encoding="utf-8", newline="\n") as env_file:
        env_file.write("\n".join(lines) + "\n")
    os.replace(temporary, ENV_PATH)
    if value:
        os.environ[var] = value
    else:
        os.environ.pop(var, None)


def _user_home_ws(c, sess=None):
    """The workspace a viewer is pinned to, or None for an all-access admin.
    ``sess`` lets a non-Flask caller (the FastAPI routers) pass the session
    dict explicitly instead of the request-bound proxy."""
    store = session if sess is None else sess
    uid = store.get("user_id")
    if not uid:
        return None
    return repo.users.home_workspace_id(c.session, uid)


def current_ws(c, sess=None):
    """Active workspace for this request. A viewer is pinned to its own
    workspace; an admin may switch via session['ws_id']; else the first one."""
    store = session if sess is None else sess
    home = _user_home_ws(c, sess)
    if home is not None:
        return home
    wid = store.get("ws_id")
    if wid and repo.workspaces.exists(c.session, wid):
        return wid
    return repo.workspaces.first_id(c.session)


def latest_run(c, ws):
    return repo.runs.latest_done_id(c.session, ws)


def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(24)
    return session["csrf_token"]


@app.before_request
def protect_portal():
    """Guard for the JSON API. Flask is API-only; the browser UI is served by
    Next, which proxies `/api/*` here with the first-party session cookie."""
    if request.endpoint in ("static", "favicon", "healthz", "readyz", "metrics",
                            "api_v1.csrf",
                            "api_v1.auth_login", "api_v1.auth_me",
                            "api_v1.auth_logout",
                            "api_v1.oauth_google_start",
                            "api_v1.oauth_google_callback"):
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            supplied = request.headers.get("X-CSRF-Token")
            if not supplied or not secrets.compare_digest(supplied, csrf_token()):
                abort(400, "Invalid CSRF token")
        return None
    if "user_id" not in session:
        return jsonify({"error": "authentication required"}), 401
    # Idle-session timeout (Hamza: "logout after 20 mins of inactivity") --
    # the same clock api_fastapi/deps.py::guard() ticks; the two frameworks
    # share one Redis-backed session (websession/store.py), so either one
    # expiring it ends it for both.
    if idle.expired(session):
        session.clear()
        return jsonify({"error": "session expired — please sign in again"}), 401
    idle.touch(session)  # mutates in place; Flask-Session persists on response
    # RBAC (P1.5b): deny-by-default. Every /api/v1 route past the whitelist
    # above must declare @requires(area, verb); an authed user needs that
    # permission in their session's `perms` set.
    need = required_permission(request.endpoint)
    if need is None:
        abort(403)
    if f"{need[0]}:{need[1]}" not in set(session.get("perms") or ()):
        abort(403)
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        supplied = request.headers.get("X-CSRF-Token")
        if not supplied or not secrets.compare_digest(supplied, csrf_token()):
            abort(400, "Invalid CSRF token")
    return None


@app.get("/favicon.ico")
def favicon():
    return send_from_directory(os.path.join(HERE, "static", "brand"),
                               "favicon.ico", mimetype="image/x-icon")


# ------------------------------------------------------------------- refresh
def _worker(run_id, ws, only_sources=None):
    c = db_operator()
    lines = []

    def log(msg):
        lines.append(f"{datetime.now(timezone.utc).strftime('%H:%M:%S')}  {msg}")
        with _lock:
            _jobs[run_id] = {"state": "running", "lines": lines[-40:]}
        repo.runs.set_progress(c.session, run_id, json.dumps(lines[-60:]))
        c.commit()

    try:
        n = collector.run_collection(c, ws, run_id, keys(ws), log,
                                     only_sources=only_sources)
        repo.runs.mark_done(c.session, run_id, finished_at=now(), new_items=n)
        log(f"done · {n} new items")
        # P2.7 follow-on: Care's own ingestion path is webhook-driven, so a
        # real comment/review this run just collected would otherwise never
        # reach an agent's queue without someone remembering to trigger the
        # bridge by hand. Best-effort — a bridge failure must not turn a
        # successful collection run into a failed one.
        try:
            bridged = care_bridge.backfill(c.session, ws, actor="system")
            if bridged["created"]:
                log(f"care bridge · {bridged['created']} new case(s)")
        except Exception as e:                                        # noqa: BLE001
            log(f"care bridge · failed ({e})")
        # Facebook Messenger / Instagram DMs -- a separate inbox from public
        # comments, needs its own permission (pages_messaging /
        # instagram_manage_messages). Same best-effort posture: never fails
        # the run, and silently no-ops for a workspace with no Meta creds.
        try:
            dm = dm_sync.sync(c.session, ws, keys(ws))
            total_new = sum(p.get("ingested", 0) for p in dm.values())
            if total_new:
                log(f"dm sync · {total_new} new message(s)")
        except Exception as e:                                        # noqa: BLE001
            log(f"dm sync · failed ({e})")
        state = "done"
    except Exception as e:
        repo.runs.mark_failed(c.session, run_id, finished_at=now())
        log(f"failed · {e}")
        c.commit()
        c.close()
        with _lock:
            _jobs[run_id] = {"state": "failed", "lines": lines[-40:]}
        raise                                   # let the job queue back off / dead-letter
    c.commit()
    c.close()
    with _lock:
        _jobs[run_id] = {"state": state, "lines": lines[-40:]}


def _score_worker(job_id, ws, reset=False):
    c = db_operator()
    lines = []

    def log(msg):
        lines.append(f"{datetime.now(timezone.utc).strftime('%H:%M:%S')}  {msg}")
        with _lock:
            _jobs[job_id] = {"state": "running", "lines": lines[-40:]}

    try:
        k = keys(ws)
        result = sentiment.score_pending(c, ws, k, log, reset=reset)
        log(f"sentiment done · {result['scored']} scored · {result['skipped']} not_scored")
        cresult = classify.classify_pending(c, ws, k, log, reset=reset)
        log(f"classify done · {cresult['classified']} typed · {cresult['skipped']} skipped")
        state = "done"
    except Exception as e:
        log(f"failed · {e}")
        state = "failed"
        c.close()
        with _lock:
            _jobs[job_id] = {"state": state, "lines": lines[-40:]}
        raise                                   # let the job queue back off / dead-letter
    c.close()
    with _lock:
        _jobs[job_id] = {"state": state, "lines": lines[-40:]}


# The two job kinds the in-process worker drains. Each wraps the legacy worker
# body; the `job` table (P1.7) now owns retry / backoff / dead-letter, while
# `_jobs` + the `run` table stay as the live progress surface for poll / SSE.
@worker.handler("collection")
def _collection_job(payload):
    _worker(payload["run_id"], payload["ws"], only_sources=payload.get("only_sources"))


@worker.handler("collection_tick")
def _collection_tick_job(payload):
    """P2.7 — enqueue a source-scoped collection run for whatever is due."""
    from collection import schedule
    from jobs import runner
    ws = payload["ws"]
    c = db_operator()
    try:
        due = schedule.due_sources(c.session, ws)
        if not due or repo.runs.running_id(c.session, ws):
            return {"ws": ws, "due": due, "enqueued": False}
        run_id = uuid.uuid4().hex[:12]
        repo.runs.create(c.session, run_id=run_id, workspace_id=ws, started_at=now())
        runner.enqueue(c.session, "collection",
                       {"ws": ws, "run_id": run_id, "only_sources": list(due)},
                       max_attempts=1, tenant_id=ws)
        c.commit()
        return {"ws": ws, "due": due, "run_id": run_id, "enqueued": True}
    finally:
        c.close()


@worker.handler("scoring")
def _scoring_job(payload):
    _score_worker(payload["handle"], payload["ws"], bool(payload.get("reset")))


@worker.handler("seo_crawl")
def _seo_crawl_job(payload):
    """The real site crawl + Lighthouse Core Web Vitals run (core/seo_crawl.py),
    moved off the request thread (2026-09-12): it polls for up to ~6.5 minutes
    worst case, which is longer than the browser's connection to the backend
    survives -- every synchronous attempt was hitting ECONNRESET on the proxy
    in front of it, even though the crawl kept running server-side and
    committed real data regardless. Same _jobs/_lock live-progress pattern as
    _worker/_score_worker; the frontend polls via JobConsole."""
    from core import seo_crawl, seo_report
    job_id, ws = payload["job_id"], payload["ws"]
    c = db_operator()
    lines = []

    def log(msg):
        lines.append(f"{datetime.now(timezone.utc).strftime('%H:%M:%S')}  {msg}")
        with _lock:
            _jobs[job_id] = {"state": "running", "lines": lines[-40:]}

    try:
        k = keys(ws)
        brands = [b for b in seo_report.resolve_domains(c.session, ws, k) if b["is_focus"]]
        out = seo_crawl.run(c.session, ws, k, brands,
                            max_pages=payload.get("max_pages", 30), log=log)
        c.commit()
        state = "done"
    except Exception as e:
        log(f"failed · {e}")
        state = "failed"
        c.close()
        with _lock:
            _jobs[job_id] = {"state": state, "lines": lines[-40:]}
        raise                                   # let the job queue back off / dead-letter
    c.close()
    with _lock:
        _jobs[job_id] = {"state": state, "lines": lines[-40:]}
    audit(actor=payload.get("actor"), tenant_id=ws, action="vantage.seo_crawl_run", after=out)


@worker.handler("send_scheduled")
def _send_scheduled_job(payload):
    """P3.8 — a scheduled message's timer fired; deliver it now."""
    from core import cases
    from integrations import write
    connection = db_operator()
    try:
        row = repo.outbound.get(connection.session, payload["action_id"])
        if not row or row["state"] != "pending":
            return {"skipped": True}
        client = write.client_for(row["platform"], keys(row["workspace_id"]))
        result = client.deliver(connection.session, payload["action_id"])
        req = repo.outbound.get(connection.session, payload["action_id"])["request"] or {}
        if result.state == "sent" and payload.get("case_id"):
            cases.post_reply(
                connection.session, payload["case_id"], row["workspace_id"],
                body=req.get("text", ""),
                channel=req.get("channel") or row["platform"],
                platform_ref=row["target_ref"], actor="scheduler",
                outbound_action_id=payload["action_id"])
        connection.commit()
        return {"state": result.state}
    finally:
        connection.close()


@worker.handler("sla_check")
def _sla_check_job(payload):
    """P3.3 — a fired one-shot SLA timer; records a breach event if unmet."""
    from core import routing
    connection = db_operator()
    try:
        result = routing.check_sla(connection.session, payload)
        connection.commit()
        return result
    finally:
        connection.close()


@worker.handler("macro_rule")
def _macro_rule_job(payload):
    """Auto macros — an event or a fired timer; re-check and run the rule's macro."""
    from core import care_audit, macro_rules
    connection = db_operator()
    try:
        result = macro_rules.run(connection.session, payload, keys=keys(payload["ws"]))
        connection.commit()
    finally:
        connection.close()
    if result.get("rule_id"):
        care_audit.emit("care.macro_auto", actor="macro", ws=payload["ws"],
                        target=result["case_id"],
                        after={"rule_id": result["rule_id"], "trigger": result["trigger"],
                               "reply": (result.get("reply") or {}).get("state")})
    return {k: v for k, v in result.items() if k in ("skipped", "rule_id", "case_id")}


@worker.handler("owned_analytics")
def _owned_analytics_job(payload):
    """P4.1 — pull owned social analytics into the metric warehouse."""
    from core import owned_analytics
    connection = db_operator()
    try:
        result = owned_analytics.ingest(
            connection.session, payload["ws"],
            days=int(payload.get("days", 1)), keys=keys(payload["ws"]))
        connection.commit()
        return result
    finally:
        connection.close()


@worker.handler("dm_sync")
def _dm_sync_job(payload):
    """Poll Meta inboxes, commit new Care messages, then push UI events."""
    connection = db_operator()
    try:
        ws = payload["ws"]
        creds = keys(ws)
        if not (creds.get("META_PAGE_ID") and creds.get("META_ACCESS_TOKEN"))                 and not creds.get("INSTAGRAM_LOGIN_ACCESS_TOKEN"):
            # Nothing to poll. Raising here would retry 5x every minute.
            return {"skipped": "Meta credentials not configured"}
        result = dm_sync.sync(connection.session, ws, creds)
        connection.commit()
        dm_sync.publish_events(result, ws)
        return result
    finally:
        connection.close()


@worker.handler("report_email")
def _report_email_job(payload):
    """P4.9 — a report schedule's cron fired; render and email it."""
    from core import report_delivery
    connection = db_operator()
    try:
        result = report_delivery.run(
            connection.session, payload["ws"], payload["schedule_id"],
            keys=keys(payload["ws"]))
        connection.commit()
        return result
    finally:
        connection.close()


@worker.handler("rehash_authors")
def _rehash_authors_job(payload):
    """P2.4 — apply the workspace's retention policy across every stored author."""
    from collection import authors
    connection = db_operator()
    try:
        result = authors.rehash_workspace(connection.session, payload["ws"])
        connection.commit()
        return result
    finally:
        connection.close()


# Register the migration API after the legacy helpers and routes exist. The
# blueprint receives those helpers through the Flask extension registry, which
# keeps the API thin and avoids duplicating analytics or tenant selection.
from api import bp as api_v1_bp
from api.v1.common import required_permission

app.extensions["guru_api"] = {
    "db": db,
    "db_operator": db_operator,
    "current_ws": current_ws,
    "latest_run": latest_run,
    "csrf_token": csrf_token,
    "keys": keys,
    "audit": audit,
    "persist_key": persist_key,
    "persist_env_value": persist_env_value,
    "now": now,
    "jobs": _jobs,
    "jobs_lock": _lock,
    "brand_patterns": brand_patterns,
    "phrase_regex": phrase_regex,
    "slugify": slugify,
    "starter_context": STARTER_CONTEXT,
}
app.register_blueprint(api_v1_bp)


_IN_PROCESS_JOB_KINDS = (
    "collection", "collection_tick", "scoring", "rehash_authors", "sla_check", "macro_rule",
    "send_scheduled", "owned_analytics", "report_email", "dm_sync", "seo_crawl",
)


def start_worker():
    """Start the in-process job worker (dev / single-instance). A real
    deployment runs `python -m jobs.worker` as its own process instead."""
    stop = threading.Event()
    threading.Thread(target=worker.loop, args=(stop,),
                     kwargs={"kinds": _IN_PROCESS_JOB_KINDS},
                     name="job-worker", daemon=True).start()
    return stop


def start_scheduler():
    """Start the in-process scheduler. Safe to run in every process — each tick
    takes a Postgres advisory lock, so only one instance ticks. A real
    deployment runs `python -m jobs.scheduler` as its own process instead."""
    stop = threading.Event()
    threading.Thread(target=scheduler.loop, args=(stop,),
                     name="job-scheduler", daemon=True).start()
    return stop


if __name__ == "__main__":
    init()
    start_worker()
    start_scheduler()
    # Default to localhost. Set GURU_HOST=0.0.0.0 to expose on the LAN or to sit
    # behind a tunnel.
    host = os.environ.get("GURU_HOST", "127.0.0.1")
    port = int(os.environ.get("GURU_PORT", "5000"))
    probe_host = "127.0.0.1" if host in ("0.0.0.0", "", "::") else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.3)
        if probe.connect_ex((probe_host, port)) == 0:
            raise SystemExit(
                f"Port {port} is already serving another process. Stop the stale "
                f"Guru Ears server or set GURU_PORT to another port.")
    print(f"\n  Guru Ears  ->  http://{probe_host}:{port}\n")
    app.run(host=host, debug=False, port=port, threaded=True)
