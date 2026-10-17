"""Session auth — CSRF token, native login, Google sign-in, logout, the
current-user probe. FastAPI port of api/v1/routers/auth.py. These are the
pre-auth routes, so they use the session helpers in deps.py directly rather
than the `guard` gate."""
import os
from urllib.parse import quote

from fastapi import APIRouter, Body, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from werkzeug.security import check_password_hash

import app as _app
from auth import oauth as google_oauth
from core import features
from db import repositories as repo

from .deps import clear_session, ensure_csrf, establish_session, require_csrf

router = APIRouter(prefix="/api/v1", tags=["auth"])

APP_BASE_URL = (os.environ.get("APP_BASE_URL") or "http://localhost:3000").rstrip("/")


def _user_payload(connection, data: dict):
    if "user_id" not in data:
        return None
    row = repo.users.by_id_active(connection.session, data["user_id"])
    if not row:
        return None
    ws_id = _app.current_ws(connection, sess=data)
    ws = repo.workspaces.summary(connection.session, ws_id)
    role_keys = repo.rbac.roles_for_user(connection.session, row[0]) or [row[2]]
    perms = sorted(f"{area}:{verb}" for area, verb in
                   repo.rbac.permissions_for_roles(connection.session, role_keys))
    return {
        "id": row[0], "name": row[1], "role": row[2],
        "roles": role_keys, "perms": perms,
        "workspace": ({"id": ws[0], "name": ws[1], "market": ws[2],
                       "onboarding_step": ws[3],
                       "slug": ws[4] or f"w{ws[0]}"} if ws else None),
        "features": features.resolve(connection.session, ws_id) if ws else {},
    }


@router.get("/csrf")
def csrf(request: Request, response: Response):
    return {"token": ensure_csrf(request, response)}


@router.post("/auth/login")
def auth_login(request: Request, response: Response,
               body: dict | None = Body(default=None)):
    require_csrf(request)
    body = body or {}
    connection = _app.db_operator()
    username = (body.get("username") or "").strip()
    row = repo.users.auth_row(connection.session, username)
    if not row or not check_password_hash(row[1], body.get("password") or ""):
        connection.close()
        _app.audit(actor=None, tenant_id=None, action="auth.login_failed",
                   target=username or "(blank)")
        return JSONResponse({"error": "Incorrect username or password."},
                            status_code=401)
    data = establish_session(request, response, connection, user_id=row[0],
                             username=username, role=row[2], workspace_id=row[3])
    user = _user_payload(connection, data)
    connection.close()
    return {"user": user}


@router.post("/auth/logout")
def auth_logout(request: Request, response: Response):
    require_csrf(request)
    clear_session(request, response)
    return {"ok": True}


@router.get("/auth/me")
def auth_me(request: Request):
    from .deps import load_session
    data = load_session(request)
    connection = _app.db_operator()
    user = _user_payload(connection, data)
    connection.close()
    return {"user": user}


@router.get("/auth/oauth/google/start")
async def oauth_google_start(request: Request):
    if google_oauth.is_mock():
        return RedirectResponse(
            google_oauth.mock_callback_url(request.query_params.get("as")),
            status_code=302)
    return await google_oauth.start_asgi(request)


@router.get("/auth/oauth/google/callback")
async def oauth_google_callback(request: Request):
    try:
        info = await google_oauth.finish_asgi(request)
    except google_oauth.OAuthError as exc:
        return RedirectResponse(f"{APP_BASE_URL}/?auth_error={quote(str(exc), safe='')}",
                                status_code=302)
    connection = _app.db_operator()
    try:
        user_row = google_oauth.resolve(
            connection.session, subject=info["subject"], email=info["email"],
            now=_app.now())
        connection.commit()
    except google_oauth.OAuthLoginError as exc:
        connection.close()
        return RedirectResponse(f"{APP_BASE_URL}/?auth_error={quote(str(exc), safe='')}",
                                status_code=302)
    redirect = RedirectResponse(f"{APP_BASE_URL}/?auth=ok", status_code=302)
    establish_session(request, redirect, connection, user_id=user_row[0],
                      username=user_row[1], role=user_row[2], workspace_id=user_row[3])
    connection.close()
    return redirect
