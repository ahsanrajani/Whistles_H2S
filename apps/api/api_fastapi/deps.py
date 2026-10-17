"""FastAPI dependencies for the ported routers.

``guard(area, verb)`` is the single gate — it does what Flask's
``protect_portal`` + ``api/v1/common._db_ws`` did for a route: authenticate off
the shared server-side session, check the RBAC permission, verify the CSRF
header on writes, then open the tenant-scoped DB connection (BYPASSRLS for an
admin, RLS + ``SET LOCAL app.tenant_id`` for everyone else) and hand back a
``Ctx``. The connection is closed when the request ends.
"""
import secrets
from typing import Iterator

from fastapi import Request

import app as _app
import websession
from core import insights
from db import repositories as repo
from websession import idle

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class ApiError(Exception):
    """Raised by a dependency to abort with a JSON body matching the Flask app
    (handler registered in asgi.py)."""

    def __init__(self, status_code: int, error: str):
        super().__init__(error)
        self.status_code = status_code
        self.error = error


def load_session(request: Request) -> dict:
    sid = request.cookies.get(websession.COOKIE_NAME)
    return websession.store().load(sid) if sid else {}


class Ctx:
    """Auth + tenant context handed to a guarded route: the session dict, a
    tenant-scoped DB handle (``LegacyConn``), and the active workspace id."""

    __slots__ = ("session", "db", "ws_id", "_closed")

    def __init__(self, session: dict, db, ws_id):
        self.session = session
        self.db = db
        self.ws_id = ws_id
        self._closed = False

    def close(self) -> None:
        if not self._closed:
            self.db.close()
            self._closed = True


def guard(area: str, verb: str, *, operator: bool = False):
    """Build the dependency enforcing the ``(area, verb)`` permission.

    ``operator=True`` forces the BYPASSRLS connection for every caller with the
    permission — the equivalent of a Flask route that called
    ``_services()["db_operator"]()`` directly rather than ``_db_ws()`` (the
    cross-tenant admin/onboarding writes). Otherwise the connection is
    role-based: BYPASSRLS for an admin, RLS + ``set_tenant`` for everyone else.
    """

    def dependency(request: Request) -> Iterator[Ctx]:
        session = load_session(request)
        if "user_id" not in session:
            raise ApiError(401, "authentication required")
        sid = request.cookies.get(websession.COOKIE_NAME)
        if idle.expired(session):
            if sid:
                websession.store().delete(sid)
            raise ApiError(401, "session expired — please sign in again")
        if idle.touch(session) and sid:
            websession.store().save(sid, session)
        if f"{area}:{verb}" not in set(session.get("perms") or ()):
            raise ApiError(403, "forbidden")
        if request.method not in _SAFE_METHODS:
            supplied = request.headers.get("X-CSRF-Token")
            if not supplied or not secrets.compare_digest(
                    supplied, session.get("csrf_token") or ""):
                raise ApiError(400, "Invalid CSRF token")

        bypass_rls = operator or session.get("role") == "admin"
        conn = _app.db_operator() if bypass_rls else _app.db()
        try:
            # Every login pins session["ws_id"] (a viewer's home, an admin's
            # switched/first ws). Trust it — resolving it via current_ws() on
            # the not-yet-tenant-scoped RLS connection can't see the workspace
            # row and returns None for a non-pinned agent.
            ws_id = session.get("ws_id")
            if ws_id is None:
                ws_id = _app.current_ws(conn, sess=session)
            if not bypass_rls:
                conn.set_tenant(ws_id)
            ctx = Ctx(session, conn, ws_id)
            yield ctx
        finally:
            conn.close()

    dependency._guru_guard = (area, verb)   # marker for the gating test
    return dependency


def require_feature(ctx: "Ctx", key: str) -> None:
    """403 (and close the ctx) when a per-workspace capability flag is off.
    Call at the top of a guarded route before doing any work."""
    from core import features
    if not features.enabled(ctx.db.session, ctx.ws_id, key):
        ctx.close()
        raise ApiError(403, f"'{key}' is turned off for this workspace")


# Roles that carry Care oversight above a plain front-line Agent -- any of
# these on a user means they keep full Care visibility (their whole team's
# queue, not just their own cases). Anyone without one is "agent-scoped":
# Hamza, 2026-09-11 -- "the agent accounts should be able to access only the
# conversations assigned to them, nothing else."
_CARE_OVERSIGHT_ROLES = frozenset({"senior_agent", "supervisor", "team_lead", "admin"})


def is_agent_scoped(ctx: "Ctx") -> bool:
    """True if this session's role set has no Care-oversight role -- meaning
    Care access must be restricted to cases assigned to this user."""
    roles = set(ctx.session.get("roles") or ())
    if not roles:
        role = ctx.session.get("role")
        roles = {role} if role else set()
    return roles.isdisjoint(_CARE_OVERSIGHT_ROLES)


def care_visibility_clause(ctx: "Ctx") -> tuple[str, dict]:
    """Extra SQL condition (+ its params) to AND into any query over
    ``"case"`` rows so an agent-scoped user only ever sees their own
    assigned cases. Unscoped users get a no-op condition."""
    if not is_agent_scoped(ctx):
        return "1=1", {}
    return "assignee_id = :care_scope_me", {"care_scope_me": ctx.session.get("user_id")}


def assert_case_access(ctx: "Ctx", case_id: int) -> None:
    """For an agent-scoped user, 404 (not 403 -- don't confirm the case
    exists) unless ``case_id`` is assigned to them. No-op for anyone with
    Care oversight. Call before reading or acting on a specific case."""
    if not is_agent_scoped(ctx):
        return
    from sqlalchemy import text
    row = ctx.db.session.execute(text(
        'SELECT assignee_id FROM "case" WHERE id = :c AND workspace_id = :ws'),
        {"c": case_id, "ws": ctx.ws_id}).first()
    if not row or row[0] != ctx.session.get("user_id"):
        ctx.close()
        raise ApiError(404, "case not found")


def update_session(request: Request, **changes) -> None:
    """Merge ``changes`` into the caller's existing server-side session (same
    sid, so no cookie change needed). For a logged-in request the session
    always exists; a no-session request is a no-op."""
    sid = request.cookies.get(websession.COOKIE_NAME)
    if not sid:
        return
    data = websession.store().load(sid)
    data.update(changes)
    websession.store().save(sid, data)


_COOKIE_MAX_AGE = 7 * 24 * 3600


def _set_session_cookie(response, sid: str) -> None:
    response.set_cookie(websession.COOKIE_NAME, sid, max_age=_COOKIE_MAX_AGE,
                        httponly=True, samesite="lax", path="/")


def ensure_csrf(request: Request, response) -> str:
    """The session's CSRF token, minting + persisting one (creating the session
    if there is none) — the FastAPI equivalent of ``app.csrf_token()``."""
    sid = request.cookies.get(websession.COOKIE_NAME)
    data = websession.store().load(sid) if sid else {}
    token = data.get("csrf_token")
    if token:
        return token
    token = secrets.token_urlsafe(24)
    data["csrf_token"] = token
    if not sid:
        sid = websession.new_sid()
        _set_session_cookie(response, sid)
    websession.store().save(sid, data)
    return token


def establish_session(request: Request, response, connection, *, user_id,
                      username, role, workspace_id) -> dict:
    """Replace the caller's session with a freshly-authenticated one (roles,
    perms, pinned workspace, rotated CSRF) and audit the login. Mirrors
    ``api/v1/routers/auth._establish_session``."""
    roles = repo.rbac.roles_for_user(connection.session, user_id) or [role]
    perms = sorted(f"{a}:{v}" for a, v in
                   repo.rbac.permissions_for_roles(connection.session, roles))
    ws_id = workspace_id or repo.workspaces.first_id(connection.session)
    data = {"user_id": user_id, "username": username, "role": role,
            "roles": roles, "perms": perms, "ws_id": ws_id,
            "csrf_token": secrets.token_urlsafe(24)}
    sid = request.cookies.get(websession.COOKIE_NAME)
    if not sid:
        sid = websession.new_sid()
        _set_session_cookie(response, sid)
    websession.store().save(sid, data)
    _app.audit(actor=user_id, tenant_id=ws_id, action="auth.login", target=username)
    return data


def clear_session(request: Request, response) -> None:
    sid = request.cookies.get(websession.COOKIE_NAME)
    if sid:
        websession.store().delete(sid)
    response.delete_cookie(websession.COOKIE_NAME, path="/")


def require_csrf(request: Request) -> None:
    """The CSRF check the Flask `protect_portal` ran for the whitelisted
    write routes (login, logout). Raises ApiError(400) on a mismatch."""
    data = load_session(request)
    supplied = request.headers.get("X-CSRF-Token")
    if not supplied or not secrets.compare_digest(supplied, data.get("csrf_token") or ""):
        raise ApiError(400, "Invalid CSRF token")


def resolve_period(raw, default: str = "90d"):
    """``(period, days)`` — the FastAPI equivalent of ``api/v1/common._period``.
    An unknown value falls back to ``default``; ``days`` is ``None``-safe."""
    value = raw if raw in insights.PERIODS else default
    return value, insights.PERIODS[value] or 365
