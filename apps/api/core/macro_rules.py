"""Auto macros: rules that run a macro on a case without an agent clicking.

A rule has **triggers** (any of them starts it) and **filters** (all must hold):

* triggers  ``new_case`` · ``no_response {minutes}`` (the customer's last message
  has sat unanswered) · ``unassigned_for {minutes}`` · ``sla_breach`` ·
  ``keyword {words}`` (an inbound message contains one)
* filters   ``channels`` (any of) · ``vip_only``

Event triggers enqueue a ``macro_rule`` job; time triggers arm a one-shot
``scheduled_task`` (the SLA-timer pattern in ``routing.py``) that re-checks the
condition when it fires, so an agent replying in time silently cancels it. A
rule runs **at most once per case** (``care_macro_run``), which is also the loop
guard. Any reply text goes through the normal write layer — ``hold`` (default)
queues it for approval, ``send`` sends it, and dry-run mode still applies.
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from core import cases, macros
from jobs import runner

log = logging.getLogger("guru.macro_rules")

TRIGGER_TYPES = ("new_case", "no_response", "unassigned_for", "sla_breach", "keyword")
TIMED = {"no_response", "unassigned_for"}
REPLY_MODES = ("none", "hold", "send")
MAX_MINUTES = 7 * 24 * 60
# Auto macros are for live conversations: an inbound message older than this
# (a backfilled historical comment) never arms or fires a rule.
FRESH_WINDOW = timedelta(hours=1)
_SLACK = 5   # seconds a timer may fire early relative to its trigger minutes
_DM = {"messenger", "instagram_dm"}


def _now():
    return datetime.now(timezone.utc)


def _aware(value):
    """A message timestamp as an aware datetime (adapters hand over ISO strings
    or naive UTC datetimes as well as aware ones)."""
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# --- validation / CRUD -----------------------------------------------------
def validate_triggers(triggers) -> list[dict]:
    if not isinstance(triggers, list) or not triggers:
        raise macros.MacroError("choose at least one trigger")
    out, seen = [], set()
    for raw in triggers:
        kind = (raw or {}).get("type")
        if kind not in TRIGGER_TYPES:
            raise macros.MacroError(f"unknown trigger {kind!r}")
        if kind in seen:
            raise macros.MacroError(f"trigger {kind} is listed twice")
        seen.add(kind)
        trig = {"type": kind}
        if kind in TIMED:
            try:
                minutes = int(raw.get("minutes"))
            except (TypeError, ValueError):
                minutes = 0
            if not 1 <= minutes <= MAX_MINUTES:
                raise macros.MacroError(f"{kind} needs minutes between 1 and {MAX_MINUTES}")
            trig["minutes"] = minutes
        elif kind == "keyword":
            words = [str(w).strip().lower() for w in (raw.get("words") or []) if str(w).strip()]
            words = list(dict.fromkeys(words))
            if not words or len(words) > 20:
                raise macros.MacroError("keyword needs 1-20 words")
            trig["words"] = words
        out.append(trig)
    return out


def validate_filters(filters) -> dict:
    f = filters or {}
    out = {}
    channels = [str(c).strip() for c in (f.get("channels") or []) if str(c).strip()]
    if channels:
        out["channels"] = list(dict.fromkeys(channels))
    if f.get("vip_only"):
        out["vip_only"] = True
    return out


def _shape(row) -> dict:
    return dict(row)


def list_rules(session, ws) -> list[dict]:
    rows = session.execute(text("""
        SELECT r.id, r.name, r.active, r.macro_id, r.triggers, r.filters, r.reply_mode,
               r.last_fired_at, r.updated_at, m.name AS macro_name,
               (SELECT count(*) FROM care_macro_run u WHERE u.rule_id = r.id) AS fired_count
        FROM care_macro_rule r JOIN care_template m ON m.id = r.macro_id
        WHERE r.workspace_id = :ws ORDER BY r.active DESC, r.name
    """), {"ws": ws}).mappings().all()
    return [_shape(r) for r in rows]


def save_rule(session, ws, data, *, rule_id=None, actor=None) -> int:
    cur = {}
    if rule_id is not None:
        cur = next((r for r in list_rules(session, ws) if r["id"] == rule_id), None)
        if cur is None:
            raise LookupError("rule not found")
    m = {**cur, **{k: v for k, v in (data or {}).items() if k in (
        "name", "active", "macro_id", "triggers", "filters", "reply_mode")}}
    name = (m.get("name") or "").strip()
    if not name:
        raise macros.MacroError("name is required")
    macro = macros.get_macro(session, ws, m.get("macro_id")) if m.get("macro_id") else None
    if macro is None or not macro["active"]:
        raise macros.MacroError("pick an active macro to run")
    mode = m.get("reply_mode") or "hold"
    if mode not in REPLY_MODES:
        raise macros.MacroError(f"reply_mode must be one of {', '.join(REPLY_MODES)}")
    if mode != "none" and not (macro["body"] or "").strip():
        raise macros.MacroError("this macro has no reply text — set reply_mode to 'none'")
    macros.validate_actions(macro["actions"], allow_self=False)
    params = {"ws": ws, "n": name, "m": macro["id"], "act": m.get("active") is not False,
              "t": macros._json(validate_triggers(m.get("triggers"))),
              "f": macros._json(validate_filters(m.get("filters"))),
              "rm": mode, "by": actor}
    if rule_id is None:
        return int(session.execute(text("""
            INSERT INTO care_macro_rule (workspace_id, macro_id, name, active, triggers,
                                         filters, reply_mode, created_by)
            VALUES (:ws, :m, :n, :act, CAST(:t AS jsonb), CAST(:f AS jsonb), :rm, :by)
            RETURNING id"""), params).scalar_one())
    session.execute(text("""
        UPDATE care_macro_rule SET name=:n, macro_id=:m, active=:act, triggers=CAST(:t AS jsonb),
            filters=CAST(:f AS jsonb), reply_mode=:rm, updated_at=now()
        WHERE id = :i AND workspace_id = :ws"""), {**params, "i": rule_id})
    return rule_id


def delete_rule(session, ws, rule_id) -> bool:
    return bool(session.execute(text(
        "DELETE FROM care_macro_rule WHERE id = :i AND workspace_id = :ws"),
        {"i": rule_id, "ws": ws}).rowcount)


# --- event hooks (called from the case engine; must never break ingestion) --
def _active_rules(session, ws):
    return session.execute(text(
        "SELECT id, macro_id, triggers, filters FROM care_macro_rule "
        "WHERE workspace_id = :ws AND active"), {"ws": ws}).mappings().all()


def _channel_ok(rule, channel) -> bool:
    chans = (rule["filters"] or {}).get("channels")
    return not chans or channel in chans


def _job(session, ws, rule_id, case_id, trigger):
    runner.enqueue(session, "macro_rule", {"ws": ws, "rule_id": rule_id, "case_id": case_id,
                                           "trigger": trigger}, tenant_id=ws)


def _arm(session, ws, rule_id, case_id, trigger, at):
    runner.schedule_once(
        session, name=f"macro:{trigger['type']}:{rule_id}:{case_id}", at=at, kind="macro_rule",
        payload={"ws": ws, "rule_id": rule_id, "case_id": case_id,
                 "trigger": trigger["type"], "minutes": trigger["minutes"]},
        tenant_id=ws)


def on_inbound(session, ws, case_id, *, new, body, channel, sent_at, now=None) -> None:
    """A customer message landed on a case. Arms / enqueues whatever it starts."""
    now, sent_at = now or _now(), _aware(sent_at)
    if now - sent_at > FRESH_WINDOW:
        return
    lowered = (body or "").lower()
    for rule in _active_rules(session, ws):
        if not _channel_ok(rule, channel):
            continue
        for trig in rule["triggers"]:
            kind = trig["type"]
            if kind == "new_case" and new:
                _job(session, ws, rule["id"], case_id, kind)
            elif kind == "keyword" and any(w in lowered for w in trig["words"]):
                _job(session, ws, rule["id"], case_id, kind)
            elif kind == "no_response":
                _arm(session, ws, rule["id"], case_id, trig,
                     max(now, sent_at + timedelta(minutes=trig["minutes"])))
            elif kind == "unassigned_for" and new:
                _arm(session, ws, rule["id"], case_id, trig,
                     max(now, sent_at + timedelta(minutes=trig["minutes"])))


def on_sla_breach(session, ws, case_id) -> None:
    channel = session.execute(text('SELECT channel FROM "case" WHERE id = :c'),
                              {"c": case_id}).scalar()
    for rule in _active_rules(session, ws):
        if _channel_ok(rule, channel) and any(t["type"] == "sla_breach" for t in rule["triggers"]):
            _job(session, ws, rule["id"], case_id, "sla_breach")


def safe(session, fn, *args, **kwargs) -> None:
    """Run a hook inside a savepoint; a hook problem (macro rule or auto-assign) is
    logged, never raised -- it must not break ingestion."""
    try:
        with session.begin_nested():
            fn(session, *args, **kwargs)
    except Exception:                                        # noqa: BLE001
        log.exception("post-ingest hook %s failed", getattr(fn, "__name__", fn))


# --- the job ---------------------------------------------------------------
def _still_true(session, case_id, trigger, minutes, now) -> bool:
    if trigger == "no_response":
        last_in, last_out = session.execute(text("""
            SELECT max(sent_at) FILTER (WHERE direction = 'inbound'),
                   max(sent_at) FILTER (WHERE direction = 'outbound')
            FROM case_message WHERE case_id = :c"""), {"c": case_id}).one()
        return (last_in is not None and (last_out is None or last_out < last_in)
                and (now - last_in).total_seconds() >= minutes * 60 - _SLACK)
    if trigger == "unassigned_for":
        row = session.execute(text('SELECT assignee_id, opened_at FROM "case" WHERE id = :c'),
                              {"c": case_id}).first()
        return bool(row and row[0] is None
                    and (now - row[1]).total_seconds() >= minutes * 60 - _SLACK)
    return True


def run(session, payload, *, keys=None, now=None) -> dict:
    """The ``macro_rule`` job: re-check, then apply the macro once for this case."""
    now = now or _now()
    ws, rule_id, case_id, trigger = (payload["ws"], payload["rule_id"], payload["case_id"],
                                     payload["trigger"])
    rule = session.execute(text("""
        SELECT r.id, r.name, r.macro_id, r.filters, r.reply_mode FROM care_macro_rule r
        WHERE r.id = :r AND r.workspace_id = :ws AND r.active"""),
        {"r": rule_id, "ws": ws}).mappings().first()
    macro = macros.get_macro(session, ws, rule["macro_id"]) if rule else None
    if not rule or not macro or not macro["active"]:
        return {"skipped": "rule_inactive"}
    case = session.execute(text("""
        SELECT c.state, c.channel, COALESCE(cu.vip, false) AS vip
        FROM "case" c JOIN customer cu ON cu.id = c.customer_id
        WHERE c.id = :c AND c.workspace_id = :ws"""), {"c": case_id, "ws": ws}).mappings().first()
    if not case or case["state"] == cases.CLOSED:
        return {"skipped": "case_closed"}
    if not _channel_ok(rule, case["channel"]) or (
            (rule["filters"] or {}).get("vip_only") and not case["vip"]):
        return {"skipped": "filtered"}
    if not _still_true(session, case_id, trigger, int(payload.get("minutes") or 0), now):
        return {"skipped": "condition_cleared"}
    claimed = session.execute(text("""
        INSERT INTO care_macro_run (workspace_id, rule_id, case_id, trigger)
        VALUES (:ws, :r, :c, :t) ON CONFLICT (rule_id, case_id) DO NOTHING RETURNING id"""),
        {"ws": ws, "r": rule_id, "c": case_id, "t": trigger}).first()
    if not claimed:
        return {"skipped": "already_ran"}
    results = macros.apply_actions(session, ws, case_id, macro, actor="macro",
                                   source=f"auto:{rule['name']}")
    reply = None
    if rule["reply_mode"] != "none" and (macro["body"] or "").strip():
        reply = _reply(session, ws, case_id, macro["body"], hold=rule["reply_mode"] == "hold",
                       keys=keys)
    session.execute(text("UPDATE care_macro_rule SET last_fired_at = :n WHERE id = :r"),
                    {"n": now, "r": rule_id})
    out = {"rule_id": rule_id, "case_id": case_id, "trigger": trigger,
           "actions": results, "reply": reply}
    session.execute(text("UPDATE care_macro_run SET result = CAST(:r AS jsonb) WHERE id = :i"),
                    {"r": macros._json(out), "i": claimed[0]})
    return out


def _reply(session, ws, case_id, body, *, hold, keys) -> dict:
    """The macro's reply text, through the same write layer as a manual reply."""
    from integrations import write
    row = session.execute(text("""
        SELECT c.channel, cu.handle, cu.platform,
               (SELECT platform_ref FROM case_message m
                WHERE m.case_id = c.id AND m.direction = 'inbound' AND m.platform_ref IS NOT NULL
                ORDER BY m.sent_at DESC, m.id DESC LIMIT 1) AS last_ref
        FROM "case" c JOIN customer cu ON cu.id = c.customer_id WHERE c.id = :c"""),
        {"c": case_id}).mappings().first()
    rendered = macros.render(body, macros.context(session, ws, case_id))
    is_dm = row["channel"] in _DM
    target_ref = row["handle"] if is_dm else row["last_ref"]
    action = "reply_dm" if is_dm else "reply_public"
    try:
        client = write.client_for(row["platform"], keys or {})
        req = {"text": rendered, "case_id": case_id, "channel": row["channel"]}
        if hold:
            aid = client.create_pending(session, ws, action=action, target_ref=target_ref,
                                        request=req, actor="macro")
            cases._event(session, case_id, "reply_pending", "macro", outbound_action_id=aid)
            return {"state": "pending", "outbound_action_id": aid}
        send = client.reply_dm if is_dm else client.reply_public
        result = send(session, ws, target_ref=target_ref, text=rendered, actor="macro",
                      channel=row["channel"], case_id=case_id)
    except Exception as exc:                                 # noqa: BLE001
        log.exception("auto macro reply failed case=%s", case_id)
        return {"state": "error", "error": str(exc)}
    if result.state in ("sent", "dry_run"):
        ref = result.external_id if (is_dm and result.external_id) else target_ref
        cases.post_reply(session, case_id, ws, body=rendered, channel=row["channel"],
                         platform_ref=ref, actor="macro", outbound_action_id=result.action_id)
    return {"state": result.state, "outbound_action_id": result.action_id}
