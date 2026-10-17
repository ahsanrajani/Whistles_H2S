"""ASGI entrypoint — the Flask → FastAPI migration (P1.10).

FastAPI is the outer app and now owns every ``/api/v1`` route (``api_fastapi/``).
The Flask app is still mounted as the fallback so ``/favicon.ico`` and the obs
probes (``/healthz`` ``/readyz`` ``/metrics``, defined on Flask) keep working;
its ``/api/v1`` blueprint is empty. ``uvicorn asgi:app`` is the entrypoint
(``npm run dev``); ``python app.py`` still runs the Flask dev server too.

The lifespan brings the schema to head and starts the in-process job worker +
scheduler — the work ``app.py``'s ``__main__`` used to do. It does not fire
under the test client (which never enters the lifespan), so the suite still
gets neither, exactly as before.
"""
import os
from contextlib import asynccontextmanager

from a2wsgi import WSGIMiddleware
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.staticfiles import StaticFiles

import app as _app_module
from app import app as _flask_app
from auth import oauth as _google_oauth
from obs.asgi import RequestObservability


@asynccontextmanager
async def _lifespan(_app):
    _app_module.init()
    stops = [_app_module.start_worker(), _app_module.start_scheduler()]
    try:
        yield
    finally:
        for stop in stops:
            stop.set()

from api_fastapi import (admin, admin_ops, alerts, analysis, auth, branches, calibration,
                         care, care_ops, content, content_ai, dashboards, docs, jobs, knowledge, macros, mentions,
                         onboarding, owned_posts, report, reports,
                         tenancy, vantage, ws)
from api_fastapi.deps import ApiError

fastapi_app = FastAPI(
    title="Guru Ears API",
    version="1.0.0",
    # The contract of record is packages/contracts/openapi.yaml; don't serve a
    # second, divergent one.
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=_lifespan,
)

# Correlation id + (for native routes) access log & HTTP metrics, at the edge.
fastapi_app.add_middleware(RequestObservability)

# Google sign-in: build the Authlib Starlette client (no-op / mock mode when the
# creds are absent). Real mode also needs a signed session for the OAuth `state`
# round-trip — a dedicated cookie, separate from the app session.
_google_oauth.register_asgi(fastapi_app)
if not _google_oauth.is_mock():
    from starlette.middleware.sessions import SessionMiddleware

    fastapi_app.add_middleware(
        SessionMiddleware, secret_key=_flask_app.config["SECRET_KEY"],
        session_cookie="guru_oauth", same_site="lax", max_age=600)


@fastapi_app.exception_handler(ApiError)
async def _api_error(_request, exc: ApiError):
    # Match the Flask app: an API auth failure is {"error": ...}, not {"detail": ...}
    return JSONResponse({"error": exc.error}, status_code=exc.status_code)


# Ported routers — registered ABOVE the Flask mount so an explicit route wins
# over the catch-all (Starlette matches in registration order).
for _router in (docs.router, auth.router, branches.router, alerts.router, report.router,
                analysis.router, dashboards.router, mentions.router,
                tenancy.router, calibration.router, jobs.router,
                admin.router, admin_ops.router, onboarding.router, care.router, care_ops.router,
                knowledge.router, macros.router, reports.router, content.router, content_ai.router, vantage.router,
                owned_posts.router, ws.router):
    fastapi_app.include_router(_router)

# Content-calendar media uploads (core/content_media.py) -- real files on
# local disk, same posture as the existing static/brand/ logo serving; the
# Next dev proxy rewrites /uploads/:path* here, mirroring /brand/:path*.
_uploads_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "uploads")
os.makedirs(_uploads_dir, exist_ok=True)
fastapi_app.mount("/static/uploads", StaticFiles(directory=_uploads_dir), name="uploads")

# Fallback: favicon + the obs probes, still served by Flask.
fastapi_app.mount("/", WSGIMiddleware(_flask_app))

app = fastapi_app
