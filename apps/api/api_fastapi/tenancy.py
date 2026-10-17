"""Workspace listing and the admin workspace switch. FastAPI port of
api/v1/routers/tenancy.py."""
from fastapi import APIRouter, Body, Depends, Request

import app as _app
from db import repositories as repo

from .deps import ApiError, Ctx, guard, update_session

router = APIRouter(prefix="/api/v1", tags=["tenancy"])


@router.get("/workspaces")
def workspaces(ctx: Ctx = Depends(guard("listening", "view"))):
    connection, active_id = ctx.db, ctx.ws_id
    home_ws = repo.users.home_workspace_id(connection.session, ctx.session["user_id"])
    can_switch = ctx.session.get("role") == "admin" and home_ws is None
    active = repo.workspaces.summary(connection.session, active_id)
    rows = repo.workspaces.list_summaries(connection.session) if can_switch else []
    ctx.close()

    def pack(row):
        return ({"id": row[0], "name": row[1], "market": row[2],
                 "onboarding_step": row[3],
                 "slug": row[4] or f"w{row[0]}"} if row else None)

    return {"active": pack(active), "can_switch": bool(can_switch),
            "list": [pack(row) for row in rows]}


@router.get("/projects")
def projects(ctx: Ctx = Depends(guard("listening", "view"))):
    """Projects for the active workspace (frontend F0.1). Always at least the
    default ``listening`` project."""
    repo.projects.ensure_default(ctx.db.session, ctx.ws_id)
    rows = repo.projects.list_for_workspace(ctx.db.session, ctx.ws_id)
    ctx.db.commit()
    ctx.close()
    return {"projects": rows, "active": "listening"}


@router.post("/workspace/switch")
def workspace_switch(request: Request,
                     body: dict | None = Body(default=None),
                     ctx: Ctx = Depends(guard("admin", "edit", operator=True))):
    try:
        workspace_id = int((body or {}).get("ws_id") or 0)
    except (TypeError, ValueError):
        raise ApiError(400, "Invalid workspace")
    found = repo.workspaces.exists(ctx.db.session, workspace_id)
    ctx.close()
    if not found:
        raise ApiError(404, "Workspace not found")
    _app.audit(actor=ctx.session.get("user_id"), tenant_id=workspace_id,
               action="tenant.switch", target=workspace_id,
               before={"ws_id": ctx.session.get("ws_id")},
               after={"ws_id": workspace_id})
    update_session(request, ws_id=workspace_id)
    return {"ok": True, "workspace_id": workspace_id}
