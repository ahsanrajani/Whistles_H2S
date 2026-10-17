"""Shared blueprint and per-request helpers for the versioned JSON API.

Every router module attaches its routes to the single `bp` defined here; the
blueprint name stays `api_v1` so endpoint names (`api_v1.csrf`,
`api_v1.auth_login`, …) referenced in `app.protect_portal` do not move.
"""
from flask import Blueprint, current_app, request, session

from db import repositories as repo

bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")


def _services():
    return current_app.extensions["guru_api"]


# --- RBAC (P1.5b) ----------------------------------------------------------
# Each route declares the permission it needs with @requires(area, verb); the
# single enforcement point is app.protect_portal, which denies any authed
# request whose endpoint is neither whitelisted nor registered here.
_REQUIRED: dict[str, tuple[str, str]] = {}


def requires(area, verb):
    """Declare the (area, verb) permission a view needs. Enforced centrally."""
    def decorator(view):
        _REQUIRED[view.__name__] = (area, verb)
        return view
    return decorator


def required_permission(endpoint):
    """(area, verb) for a Flask endpoint name (e.g. "api_v1.overview"), or None
    when the route declared none."""
    if not endpoint:
        return None
    return _REQUIRED.get(endpoint.rsplit(".", 1)[-1])


def _db_ws():
    """(connection, workspace_id) for a request.

    An admin (all-access) gets a BYPASSRLS operator connection — the admin
    surface legitimately spans tenants. Everyone else gets an RLS-enforced
    connection scoped to their workspace via `SET LOCAL app.tenant_id`, so a
    stray query can only ever see that tenant's rows. Audit rows are written by
    the specific handlers (P1.6), not here.
    """
    service = _services()
    is_admin = session.get("role") == "admin"
    connection = service["db_operator"]() if is_admin else service["db"]()
    ws = service["current_ws"](connection)
    if not is_admin:
        connection.set_tenant(ws)
    return connection, ws


def _payload():
    return request.get_json(silent=True) or {}


def _period(default="90d"):
    from core import insights

    value = request.args.get("period", default)
    value = value if value in insights.PERIODS else default
    return value, insights.PERIODS[value] or 365


def _user(connection):
    if "user_id" not in session:
        return None
    row = repo.users.by_id_active(connection.session, session["user_id"])
    if not row:
        return None
    workspace_id = _services()["current_ws"](connection)
    workspace = repo.workspaces.summary(connection.session, workspace_id)
    return {
        "id": row[0], "name": row[1], "role": row[2],
        "workspace": ({"id": workspace[0], "name": workspace[1], "market": workspace[2],
                       "onboarding_step": workspace[3]} if workspace else None),
    }
