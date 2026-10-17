"""Observability at the ASGI edge (P1.10).

Wraps the whole ASGI app so *every* request — FastAPI-native or proxied to the
mounted Flask app — gets one correlation id (minted here, echoed as
``X-Request-Id``) bound on the context the WSGI worker thread inherits.

Access logging and HTTP metrics stay split by who actually served the request:

* proxied-to-Flask (``scope["route"]`` is the ``Mount``) — Flask's own
  ``obs/logs.py`` / ``obs/metrics.py`` hooks emit the line and the metric, with
  the real ``url_rule`` label and the tenant from the session.
* FastAPI-native route — Flask never runs, so this middleware emits the access
  line and the ``guru_http_*`` metrics itself, labelled by the route template.
"""
import time
import uuid

from starlette.datastructures import MutableHeaders
from starlette.routing import Mount

from . import context
from .logs import _QUIET_PATHS
from .metrics import HTTP_LATENCY, HTTP_REQUESTS

import logging

_access = logging.getLogger("guru.access")


class RequestObservability:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {k.lower(): v for k, v in scope["headers"]}
        rid = (headers.get(b"x-request-id", b"").decode().strip() or uuid.uuid4().hex)
        context.bind(request_id=rid)
        start = time.perf_counter()
        seen = {"status": 500}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                seen["status"] = message["status"]
                MutableHeaders(scope=message).setdefault("X-Request-Id", rid)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            route = scope.get("route")
            served_by_flask = route is None or isinstance(route, Mount)
            if not served_by_flask:
                dur = time.perf_counter() - start
                path = scope.get("path", "")
                label = getattr(route, "path", path)
                status = str(seen["status"])
                if path not in _QUIET_PATHS:
                    HTTP_LATENCY.labels(scope["method"], label, status).observe(dur)
                    HTTP_REQUESTS.labels(scope["method"], label, status).inc()
                    _access.info("http_request", extra={
                        "request_id": rid,
                        "tenant_id": context.tenant_id(),
                        "method": scope["method"],
                        "path": path,
                        "endpoint": label,
                        "status": seen["status"],
                        "dur_ms": round(dur * 1000, 1),
                    })
            context.clear()
