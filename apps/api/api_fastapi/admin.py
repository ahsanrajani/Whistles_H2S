"""Admin config surface. FastAPI port of api/v1/routers/admin.py — every route
gated by an ``admin`` permission; writes call the same helpers so behaviour
cannot drift. Operational endpoints (source health/retention/precision/cost,
backfills, routing policy, job console) split out to ``admin_ops.py`` to stay
under the 600-line file limit — this file keeps workspace/brand/user/
key/source/feature CRUD."""
import json
import os
import re

from fastapi import APIRouter, Body, Depends
from werkzeug.security import generate_password_hash

import app as _app
from core import collector, entity, features, routing, sources
from db import repositories as repo
from db.analytics import dashboards as dq

from .deps import ApiError, Ctx, guard

router = APIRouter(prefix="/api/v1", tags=["admin"])


def _as_patterns(value, default):
    """Accept a parsed list/dict, a JSON string, or newline-separated regex."""
    if value is None or value == "":
        return json.dumps(default)
    if isinstance(value, (list, dict)):
        return json.dumps(value)
    text = str(value).strip()
    try:
        return json.dumps(json.loads(text))
    except json.JSONDecodeError:
        return json.dumps([line.strip() for line in text.splitlines() if line.strip()])


@router.get("/admin/workspaces")
def admin_workspaces(ctx: Ctx = Depends(guard("admin", "view"))):
    rows = repo.workspaces.list_admin(ctx.db.session)
    active_id = ctx.ws_id
    ctx.close()
    return {"active_id": active_id, "list": [
        {"id": row[0], "name": row[1], "market": row[2], "volume_scenario": row[3]}
        for row in rows]}


@router.post("/admin/workspaces")
def admin_workspaces_create(body: dict | None = Body(default=None),
                            ctx: Ctx = Depends(guard("admin", "create", operator=True))):
    body = body or {}
    name = (body.get("name") or "").strip()
    if not name:
        ctx.close()
        raise ApiError(400, "name is required")
    repo.workspaces.create(
        ctx.db.session, name=name,
        market=(body.get("market") or "PK").strip(),
        volume_scenario=(body.get("volume_scenario") or "mid").strip(),
        sentiment_langs=(body.get("sentiment_langs") or "en").strip(),
        created_at=_app.now())
    ctx.db.commit()
    ctx.close()
    return {"ok": True}


@router.get("/admin/brands")
def admin_brands(ctx: Ctx = Depends(guard("admin", "view"))):
    workspace_id = ctx.ws_id
    brands = repo.brands.rows(ctx.db.session, workspace_id)
    ctx.close()
    return {"ws_id": workspace_id, "brands": brands}


@router.post("/admin/brands")
def admin_brands_save(body: dict | None = Body(default=None),
                      ctx: Ctx = Depends(guard("admin", "edit"))):
    body = body or {}
    name = (body.get("name") or "").strip()
    if not name:
        ctx.close()
        raise ApiError(400, "name is required")
    connection = ctx.db
    workspace_id = int(body.get("workspace_id") or ctx.ws_id)
    brand_id = body.get("brand_id")
    before = next((b for b in repo.brands.rows(connection.session, workspace_id)
                   if brand_id and b.get("id") == brand_id), None)
    after = {"name": name, "is_focus": bool(body.get("is_focus")),
             "archived": bool(body.get("archive")),
             "safe": _as_patterns(body.get("safe_patterns"), []),
             "gated": _as_patterns(body.get("gated_patterns"), {}),
             "context": _as_patterns(body.get("context_patterns"), []),
             "exclude": _as_patterns(body.get("exclude_patterns"), [])}
    repo.brands.upsert(
        connection.session,
        brand_id=brand_id, workspace_id=workspace_id, name=name,
        is_focus=1 if body.get("is_focus") else 0,
        safe=after["safe"], gated=after["gated"],
        context=after["context"], exclude=after["exclude"],
        active=0 if body.get("archive") else 1)
    connection.commit()
    brands = repo.brands.rows(connection.session, workspace_id)
    ctx.close()
    _app.audit(actor=ctx.session.get("user_id"), tenant_id=workspace_id,
               action="brand.rule_edit", target=name, before=before, after=after)
    return {"ok": True, "brands": brands}


@router.post("/admin/brands/preview")
def admin_brands_preview(body: dict | None = Body(default=None),
                         ctx: Ctx = Depends(guard("admin", "view"))):
    """Live sample-match: run the edited rules against the existing corpus."""
    body = body or {}
    fields = {
        "safe": json.loads(_as_patterns(body.get("safe_patterns"), [])),
        "gated": json.loads(_as_patterns(body.get("gated_patterns"), {})),
        "context": json.loads(_as_patterns(body.get("context_patterns"), [])),
        "exclude": json.loads(_as_patterns(body.get("exclude_patterns"), [])),
    }
    errors = []
    for group, value in fields.items():
        patterns = (list(value.keys()) if isinstance(value, dict) else
                    [pair[0] if isinstance(pair, (list, tuple)) else pair for pair in value])
        for pattern in patterns:
            try:
                re.compile(pattern)
            except re.error as caught:
                errors.append({"group": group, "pattern": pattern, "error": str(caught)})
    connection, workspace_id = ctx.db, ctx.ws_id
    brand = {"id": 0, "name": (body.get("name") or "candidate"),
             "safe": fields["safe"], "gated": fields["gated"],
             "context": fields["context"], "exclude": fields["exclude"]}
    matched, match_count, excluded_count, sample_size = [], 0, 0, 0
    if not errors:
        rows = dq.preview_items(connection.session, workspace_id, 4000)
        sample_size = len(rows)
        for iid, title, item_body, outlet, surface in rows:
            text = " ".join(filter(None, [title, item_body]))
            hits = entity.classify(text, [brand])
            if not hits:
                continue
            match_count += 1
            _bid, rule, review, exc, reason = hits[0]
            if exc:
                excluded_count += 1
            if len(matched) < 40:
                matched.append({
                    "id": iid, "text": text.strip().replace("\n", " ")[:240],
                    "outlet": outlet, "surface": surface, "rule": rule,
                    "needs_review": bool(review), "excluded": bool(exc), "reason": reason,
                })
    ctx.close()
    return {
        "errors": errors, "sample_size": sample_size, "match_count": match_count,
        "excluded_count": excluded_count, "matched": matched,
    }


@router.post("/admin/rematch")
def admin_rematch(ctx: Ctx = Depends(guard("admin", "edit"))):
    connection, workspace_id = ctx.db, ctx.ws_id
    repo.mentions.delete_for_workspace(connection.session, workspace_id)
    collector.match(connection, workspace_id, entity.load(connection, workspace_id),
                    lambda _m: None)
    connection.commit()
    mentions = repo.mentions.count_for_workspace(connection.session, workspace_id)
    ctx.close()
    return {"ok": True, "mentions": mentions}


@router.get("/admin/roles")
def admin_roles(ctx: Ctx = Depends(guard("admin", "view", operator=True))):
    """The RBAC role catalogue — for the Users "add" form's role picker."""
    roles = repo.rbac.catalogue(ctx.db.session)["roles"]
    ctx.close()
    return {"roles": [{"key": k, "label": label, "rank": rank} for k, label, rank in roles]}


@router.get("/admin/users")
def admin_users(ctx: Ctx = Depends(guard("admin", "view", operator=True))):
    users = repo.users.list_with_workspace(ctx.db.session)
    workspaces = [(w[0], w[1]) for w in repo.workspaces.list_admin(ctx.db.session)]
    ctx.close()
    return {
        "users": [{"id": row[0], "username": row[1], "role": row[2], "active": bool(row[3]),
                   "workspace": row[4], "workspace_id": row[5]} for row in users],
        "workspaces": [{"id": row[0], "name": row[1]} for row in workspaces],
    }


@router.post("/admin/users")
def admin_users_create(body: dict | None = Body(default=None),
                       ctx: Ctx = Depends(guard("admin", "create", operator=True))):
    body = body or {}
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    role = (body.get("role") or "bank_viewer").strip()
    known_roles = {k for k, _label, _rank in repo.rbac.catalogue(ctx.db.session)["roles"]}
    if role not in known_roles:
        ctx.close()
        raise ApiError(400, f"unknown role {role!r}")
    try:
        workspace_id = int(body.get("workspace_id") or 0) or None
    except (TypeError, ValueError):
        workspace_id = None
    # every role except admin is scoped to one workspace (care staff work a
    # single tenant's queue same as a viewer sees a single tenant's reports);
    # admin may be pinned to one too, but doesn't have to be — None = all workspaces.
    if not username or not password:
        ctx.close()
        raise ApiError(400, "username and password are required")
    if role != "admin" and not workspace_id:
        ctx.close()
        raise ApiError(400, f"a workspace is required for role {role!r}")
    connection = ctx.db
    if workspace_id and not repo.workspaces.exists(connection.session, workspace_id):
        ctx.close()
        raise ApiError(404, "Workspace not found")
    user_id = repo.users.create(connection.session, username=username,
                                password_hash=generate_password_hash(password), role=role,
                                workspace_id=workspace_id, created_at=_app.now(),
                                email=(body.get("email") or "").strip().lower() or None)
    if user_id is None:
        connection.commit()
        ctx.close()
        raise ApiError(409, "username already exists")
    repo.rbac.set_user_roles(connection.session, user_id, [role])
    if role in ("agent", "senior_agent", "supervisor", "team_lead"):
        # Care's assignment dropdown (GET /care/roster) only lists users with
        # a care_agent row -- a role grant alone doesn't put them on the
        # roster. Without this an admin creates "Agent Jane" and she's
        # invisible in every "Assign to" picker until someone notices.
        routing.upsert_agent(connection.session, workspace_id, user_id)
    connection.commit()
    ctx.close()
    _app.audit(actor=ctx.session.get("user_id"), tenant_id=workspace_id,
               action="user.create", target=username,
               after={"role": role, "workspace_id": workspace_id})
    return {"ok": True}


def _load_target_user(ctx: Ctx, user_id: int):
    """The user being edited, or a clean 404 (closes ctx either way on miss)."""
    row = repo.users.get(ctx.db.session, user_id)
    if not row:
        ctx.close()
        raise ApiError(404, "user not found")
    return row


@router.put("/admin/users/{user_id}")
def admin_users_update(user_id: int, body: dict | None = Body(default=None),
                       ctx: Ctx = Depends(guard("admin", "edit", operator=True))):
    """Change a user's role and/or workspace (Hamza: "option to edit access
    type/workspace of a user")."""
    before = _load_target_user(ctx, user_id)
    body = body or {}
    role = (body.get("role") or before[2]).strip()
    known_roles = {k for k, _label, _rank in repo.rbac.catalogue(ctx.db.session)["roles"]}
    if role not in known_roles:
        ctx.close()
        raise ApiError(400, f"unknown role {role!r}")
    # key absent -> keep the existing pin; present but empty -> clear it
    # (e.g. promoting someone to admin); present with a value -> re-pin.
    raw_ws = body.get("workspace_id", before[4])
    try:
        workspace_id = int(raw_ws) if raw_ws not in (None, "") else None
    except (TypeError, ValueError):
        ctx.close()
        raise ApiError(400, "invalid workspace_id")
    if role != "admin" and not workspace_id:
        ctx.close()
        raise ApiError(400, f"a workspace is required for role {role!r}")
    connection = ctx.db
    if workspace_id and not repo.workspaces.exists(connection.session, workspace_id):
        ctx.close()
        raise ApiError(404, "Workspace not found")
    repo.users.update_access(connection.session, user_id, role=role, workspace_id=workspace_id)
    repo.rbac.set_user_roles(connection.session, user_id, [role])
    if role in ("agent", "senior_agent", "supervisor", "team_lead"):
        routing.upsert_agent(connection.session, workspace_id, user_id)
    connection.commit()
    ctx.close()
    _app.audit(actor=ctx.session.get("user_id"), tenant_id=workspace_id,
               action="user.update_access", target=before[1],
               before={"role": before[2], "workspace_id": before[4]},
               after={"role": role, "workspace_id": workspace_id})
    return {"ok": True}


@router.post("/admin/users/{user_id}/active")
def admin_users_set_active(user_id: int, body: dict | None = Body(default=None),
                           ctx: Ctx = Depends(guard("admin", "edit", operator=True))):
    """Deactivate/reactivate — a disabled user can no longer log in, but their
    history (notes, replies, audit trail) stays intact, unlike Delete."""
    before = _load_target_user(ctx, user_id)
    if user_id == ctx.session.get("user_id"):
        ctx.close()
        raise ApiError(400, "cannot deactivate your own account")
    active = bool((body or {}).get("active", False))
    repo.users.set_active(ctx.db.session, user_id, active)
    ctx.db.commit()
    ctx.close()
    _app.audit(actor=ctx.session.get("user_id"), tenant_id=before[4],
               action="user.set_active", target=before[1],
               before={"active": bool(before[3])}, after={"active": active})
    return {"ok": True}


@router.post("/admin/users/{user_id}/password")
def admin_users_set_password(user_id: int, body: dict | None = Body(default=None),
                             ctx: Ctx = Depends(guard("admin", "edit", operator=True))):
    """Admin-set password reset — no old-password check (admin:edit is
    already the gate)."""
    before = _load_target_user(ctx, user_id)
    password = (body or {}).get("password") or ""
    if len(password) < 8:
        ctx.close()
        raise ApiError(400, "password must be at least 8 characters")
    repo.users.set_password_by_id(ctx.db.session, user_id, generate_password_hash(password))
    ctx.db.commit()
    ctx.close()
    _app.audit(actor=ctx.session.get("user_id"), tenant_id=before[4],
               action="user.set_password", target=before[1])
    return {"ok": True}


@router.delete("/admin/users/{user_id}")
def admin_users_delete(user_id: int, ctx: Ctx = Depends(guard("admin", "delete", operator=True))):
    """Hard delete — only for an account with no real activity on file yet
    (repo.users.has_activity: no assigned case, note, shift, or authored
    content). Anything else is a clean 409 pointing at Deactivate instead,
    which keeps the account's history intact."""
    from sqlalchemy.exc import IntegrityError

    before = _load_target_user(ctx, user_id)
    if user_id == ctx.session.get("user_id"):
        ctx.close()
        raise ApiError(400, "cannot delete your own account")
    if repo.users.has_activity(ctx.db.session, user_id):
        ctx.close()
        raise ApiError(409, "this user has activity on file (assigned cases, notes, "
                            "shifts, or authored content) and can't be deleted — "
                            "deactivate it instead")
    try:
        repo.users.delete(ctx.db.session, user_id)
        ctx.db.commit()
    except IntegrityError:                                        # defensive, see repo
        ctx.db.rollback()
        ctx.close()
        raise ApiError(409, "this user is still referenced elsewhere and can't be "
                            "deleted — deactivate it instead")
    ctx.close()
    _app.audit(actor=ctx.session.get("user_id"), tenant_id=before[4],
               action="user.delete", target=before[1])
    return {"ok": True}


@router.get("/admin/keys")
def admin_keys(ctx: Ctx = Depends(guard("admin", "view"))):
    connection, workspace_id = ctx.db, ctx.ws_id
    workspace_name = repo.workspaces.name(connection.session, workspace_id)
    ws_values = repo.keys.workspace_values(connection.session, workspace_id)
    shared_rows = repo.keys.shared_rows(connection.session)
    ctx.close()
    shared = [{"env_var": var, "label": label,
               "value": os.environ.get(var) or value, "status": status, "note": note,
               "from_env": bool(os.environ.get(var))}
              for var, label, value, status, note in shared_rows]
    workspace_keys = [{"env_var": var, "label": label, "value": ws_values.get(var)}
                      for var, label in sources.KEYS]
    return {"ws_id": workspace_id, "ws_name": workspace_name,
            "workspace": workspace_keys, "shared": shared}


@router.post("/admin/keys")
def admin_keys_save(body: dict | None = Body(default=None),
                    ctx: Ctx = Depends(guard("admin", "edit"))):
    ctx.close()
    body = body or {}
    var = body.get("env_var")
    value = (body.get("value") or "").strip()
    try:
        target = int(body.get("workspace_id") or 0)
    except (TypeError, ValueError):
        target = 0
    if not var:
        raise ApiError(400, "env_var is required")
    if target == 0:
        _app.persist_env_value(var, value)
    _app.persist_key(target, var, value)
    return {"ok": True}


@router.get("/admin/sources")
def admin_sources(ctx: Ctx = Depends(guard("admin", "view"))):
    state = {r["source"]: r for r in
             repo.source_state.all_for_workspace(ctx.db.session, ctx.ws_id)}
    ctx.close()
    return {"sources": [
        {"id": sid, "label": meta["label"], "surface": meta["surface"],
         "kind": meta["kind"], "unit": meta.get("unit", ""),
         "unit_cost": meta.get("unit_cost", 0), "cost_note": meta.get("cost_note", ""),
         "warn": meta.get("warn"), "client_safe": bool(meta.get("client_safe")),
         "enabled": bool(state.get(sid, {}).get("enabled", True))}
        for sid, meta in sources.SOURCES.items()]}


@router.put("/admin/sources/{source_id}/enabled")
def admin_source_set_enabled(source_id: str, body: dict | None = Body(default=None),
                             ctx: Ctx = Depends(guard("admin", "edit", operator=True))):
    """Turn a collection source on/off for this workspace (the per-workspace
    opt-out from 0027). Shared credentials are untouched."""
    if source_id not in sources.SOURCES:
        ctx.close()
        raise ApiError(404, "unknown source")
    enabled = bool((body or {}).get("enabled", True))
    repo.source_state.set_enabled(ctx.db.session, ctx.ws_id, source_id, enabled)
    ctx.db.commit()
    actor, ws = ctx.session.get("user_id"), ctx.ws_id
    ctx.close()
    _app.audit(actor=actor, tenant_id=ws, action="admin.source_enabled",
               target=source_id, after={"enabled": enabled})
    return {"ok": True, "source_id": source_id, "enabled": enabled}


@router.get("/admin/features")
def admin_features(ctx: Ctx = Depends(guard("admin", "view"))):
    """Every known feature flag with its per-workspace on/off state."""
    resolved = features.resolve(ctx.db.session, ctx.ws_id)
    ctx.close()
    return {"features": [{**item, "enabled": resolved[item["key"]]}
                         for item in features.catalog()]}


@router.put("/admin/features/{feature_key}")
def admin_feature_set(feature_key: str, body: dict | None = Body(default=None),
                      ctx: Ctx = Depends(guard("admin", "edit", operator=True))):
    """Turn one feature on/off for this workspace."""
    if not features.is_valid(feature_key):
        ctx.close()
        raise ApiError(404, "unknown feature")
    enabled = bool((body or {}).get("enabled", True))
    repo.feature_flags.set_enabled(ctx.db.session, ctx.ws_id, feature_key, enabled)
    ctx.db.commit()
    actor, ws = ctx.session.get("user_id"), ctx.ws_id
    ctx.close()
    _app.audit(actor=actor, tenant_id=ws, action="admin.feature_flag",
               target=feature_key, after={"enabled": enabled})
    return {"ok": True, "feature_key": feature_key, "enabled": enabled}
