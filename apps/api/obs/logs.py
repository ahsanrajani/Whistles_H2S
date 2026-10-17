"""Structured JSON logging — one object per line on stdout:

    {"ts":"2026-09-03T12:00:00.123+00:00","level":"INFO","logger":"guru.access",
     "msg":"http_request","request_id":"9f2c…","tenant_id":1,"method":"GET",
     "path":"/api/v1/overview","status":200,"dur_ms":12.4}

``configure_logging()`` installs the formatter on the root logger (call once at
startup). ``install(app)`` stamps every request with a correlation id — echoed
back as ``X-Request-Id`` — and emits exactly one access line per request with
the id and the tenant on it.
"""
import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime, timezone

from . import context

# keys already on a bare LogRecord — everything else in record.__dict__ came
# from a caller's logging `extra=` and belongs in the JSON payload
_RESERVED = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}

# probes / scrapes: correlate them but don't log a line every few seconds
_QUIET_PATHS = frozenset({"/healthz", "/readyz", "/metrics"})


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc)
            .isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": context.request_id(),
            "tenant_id": context.tenant_id(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload.setdefault(key, value)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, separators=(",", ":"),
                          ensure_ascii=False)


def configure_logging(level: str | None = None) -> None:
    """Point the root logger at a single stdout handler with the JSON formatter.
    Idempotent — safe to call more than once. ``LOG_LEVEL`` env overrides."""
    level = (level or os.environ.get("LOG_LEVEL") or "INFO").upper()
    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):
        root.removeHandler(handler)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    # Werkzeug's own access log is unstructured and duplicates ours.
    logging.getLogger("werkzeug").setLevel("WARNING")


_access = logging.getLogger("guru.access")


def install(app) -> None:
    """Wire the correlation id + access line onto a Flask app."""
    from flask import g, request, session

    @app.before_request
    def _correlate():
        # When served behind the ASGI edge (obs/asgi.py) the request id is
        # already minted and bound on the context that a2wsgi copied into this
        # thread — adopt it rather than minting a second one.
        rid = (context.request_id()
               or (request.headers.get("X-Request-Id") or "").strip()
               or uuid.uuid4().hex)
        g.guru_request_id = rid
        g.guru_t0 = time.perf_counter()
        context.bind(request_id=rid)

    @app.after_request
    def _access_line(response):
        rid = getattr(g, "guru_request_id", "")
        if rid:
            response.headers.setdefault("X-Request-Id", rid)
        ws = session.get("ws_id")
        if ws is not None:
            context.bind(tenant_id=ws)
        if request.path not in _QUIET_PATHS:
            t0 = getattr(g, "guru_t0", None)
            _access.info("http_request", extra={
                "request_id": rid or None,
                "tenant_id": ws,
                "method": request.method,
                "path": request.path,
                "endpoint": request.endpoint,
                "status": response.status_code,
                "dur_ms": round((time.perf_counter() - t0) * 1000, 1) if t0 else None,
                "remote_addr": (request.headers.get("X-Forwarded-For")
                                or request.remote_addr),
            })
        return response

    @app.teardown_request
    def _uncorrelate(_exc=None):
        context.clear()
