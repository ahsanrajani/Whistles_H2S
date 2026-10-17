"""Prometheus metrics and the health / readiness probes (P1.9b).

Two flavours of metric:

* in-process — HTTP request latency + count (``after_request``) and per-worker
  job outcomes (``record_job``, called from ``jobs/worker.py``). Updated as
  things happen in this process.
* scrape-time — job queue depth, scheduled-tasks-due, and per-source
  collection success. A custom collector reads them from Postgres when
  ``/metrics`` is scraped, so they are correct whichever process answers.

Routes (all unauthenticated, outside ``/api/v1`` — whitelisted in
``protect_portal``):
    GET /metrics   Prometheus exposition
    GET /healthz   liveness — always 200 while the process is up
    GET /readyz    readiness — 200 iff Postgres and Redis both answer, else 503

Only ``install()`` touches Flask, so ``jobs/worker.py`` can import ``record_job``
without dragging in the web layer.
"""
import time

from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, Counter, Histogram, generate_latest
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily
from sqlalchemy import text

_QUIET_PATHS = frozenset({"/metrics", "/healthz", "/readyz"})

HTTP_LATENCY = Histogram(
    "guru_http_request_duration_seconds", "HTTP request latency in seconds",
    ["method", "route", "status"])
HTTP_REQUESTS = Counter(
    "guru_http_requests_total", "HTTP requests handled",
    ["method", "route", "status"])
JOBS = Counter(
    "guru_jobs_total", "Job runs by kind and outcome", ["kind", "outcome"])


def record_job(kind: str, outcome: str) -> None:
    """``outcome`` is ``done`` or ``failed``. Called once per job run."""
    JOBS.labels(kind=kind or "unknown", outcome=outcome).inc()


class _DbCollector:
    """Queue depth + per-source collection success, read from Postgres at
    scrape time. Never raises out of ``collect`` — a metrics scrape must not
    fail because the DB is briefly unavailable."""

    def collect(self):
        try:
            from db.session import OperatorSession
            session = OperatorSession()
        except Exception:
            return
        try:
            depth = GaugeMetricFamily(
                "guru_job_queue_depth", "Jobs by state", labels=["state"])
            for state, n in session.execute(text(
                    "SELECT state, count(*) FROM job GROUP BY state")):
                depth.add_metric([state], n)
            yield depth

            due = GaugeMetricFamily(
                "guru_scheduled_tasks_due",
                "Enabled scheduled_task rows whose next_run has passed")
            due.add_metric([], session.execute(text(
                "SELECT count(*) FROM scheduled_task "
                "WHERE enabled = 1 AND next_run <= now()")).scalar_one())
            yield due

            calls = CounterMetricFamily(
                "guru_collection_calls", "Source adapter calls by outcome",
                labels=["source", "outcome"])
            for source, ok, total in session.execute(text("""
                    SELECT source,
                           COALESCE(SUM(calls) FILTER (WHERE ok = 1), 0),
                           COALESCE(SUM(calls), 0)
                    FROM call_log GROUP BY source""")):
                calls.add_metric([source, "ok"], int(ok))
                calls.add_metric([source, "error"], int(total) - int(ok))
            yield calls
        except Exception:
            return
        finally:
            session.close()


_installed = False


def install(app) -> None:
    """Register /metrics, /healthz, /readyz, the latency hook, and the
    scrape-time DB collector. Idempotent."""
    global _installed
    if _installed:
        return
    _installed = True
    REGISTRY.register(_DbCollector())

    from flask import Response, jsonify, request

    def _route_label():
        if request.url_rule is not None:
            return request.url_rule.rule
        return request.endpoint or "<unmatched>"

    @app.before_request
    def _start_timer():
        request._guru_metrics_t0 = time.perf_counter()

    @app.after_request
    def _measure(response):
        if request.path not in _QUIET_PATHS:
            t0 = getattr(request, "_guru_metrics_t0", None)
            labels = (request.method, _route_label(), str(response.status_code))
            if t0 is not None:
                HTTP_LATENCY.labels(*labels).observe(time.perf_counter() - t0)
            HTTP_REQUESTS.labels(*labels).inc()
        return response

    @app.get("/metrics")
    def metrics():
        return Response(generate_latest(REGISTRY), mimetype=CONTENT_TYPE_LATEST)

    @app.get("/healthz")
    def healthz():
        return jsonify(status="ok")

    @app.get("/readyz")
    def readyz():
        checks = {"database": _check_db(), "redis": _check_redis(app)}
        ok = all(v == "ok" for v in checks.values())
        return jsonify(status="ok" if ok else "degraded", checks=checks), (200 if ok else 503)


def _check_db() -> str:
    try:
        from db.session import operator_engine
        with operator_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return "ok"
    except Exception as exc:                                # noqa: BLE001
        return f"error: {type(exc).__name__}"


def _check_redis(app) -> str:
    try:
        client = app.config.get("SESSION_REDIS")
        if client is None:
            return "error: no client"
        client.ping()
        return "ok"
    except Exception as exc:                                # noqa: BLE001
        return f"error: {type(exc).__name__}"
