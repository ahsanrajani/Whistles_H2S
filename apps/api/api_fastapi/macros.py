"""Macros API: library CRUD, apply-to-case, and auto-macro rules.

Thin by design (project rules §0.3): each route resolves the tenant, calls one
``core.macros`` / ``core.macro_rules`` function and returns its result. Authoring
needs ``templates:create|edit|delete`` (admin / team lead / supervisor); every
role that can open a case can list, preview and apply.
"""
from fastapi import APIRouter, Body, Depends

from core import care_audit, macro_rules, macros, realtime

from .deps import ApiError, Ctx, assert_case_access, guard

router = APIRouter(prefix="/api/v1", tags=["macros"])


def _fail(ctx: Ctx, exc: Exception):
    """Close the request handle and turn a domain error into an HTTP error."""
    ctx.close()
    if isinstance(exc, macros.MacroConflict):
        raise ApiError(409, str(exc))
    if isinstance(exc, LookupError):
        raise ApiError(404, str(exc).strip("'\""))
    raise ApiError(400, str(exc))


# --- library ---------------------------------------------------------------
@router.get("/macros")
def list_macros(category: str = "", include_inactive: bool = False, quick: bool = False,
                ctx: Ctx = Depends(guard("templates", "view"))):
    can_author = "templates:edit" in set(ctx.session.get("perms") or ())
    rows = macros.list_macros(ctx.db.session, ctx.ws_id, category=category,
                              active_only=not (include_inactive and can_author),
                              quick_only=quick)
    ctx.close()
    return {"macros": rows}


@router.post("/macros")
def create_macro(body: dict | None = Body(default=None),
                 ctx: Ctx = Depends(guard("templates", "create"))):
    actor, ws = ctx.session.get("user_id"), ctx.ws_id
    try:
        mid = macros.save_macro(ctx.db.session, ws, body, actor=actor)
        ctx.db.commit()
    except (macros.MacroError, LookupError) as exc:
        _fail(ctx, exc)
    ctx.close()
    care_audit.emit("care.template_change", actor=actor, ws=ws, target=mid,
                    after={"entity": "macro", "op": "create", "name": (body or {}).get("name")})
    return {"ok": True, "id": mid}


@router.put("/macros/{macro_id}")
def update_macro(macro_id: int, body: dict | None = Body(default=None),
                 ctx: Ctx = Depends(guard("templates", "edit"))):
    actor, ws = ctx.session.get("user_id"), ctx.ws_id
    try:
        macros.save_macro(ctx.db.session, ws, body, macro_id=macro_id, actor=actor)
        ctx.db.commit()
    except (macros.MacroError, LookupError) as exc:
        _fail(ctx, exc)
    ctx.close()
    care_audit.emit("care.template_change", actor=actor, ws=ws, target=macro_id,
                    after={"entity": "macro", "op": "update"})
    return {"ok": True}


@router.delete("/macros/{macro_id}")
def delete_macro(macro_id: int, ctx: Ctx = Depends(guard("templates", "delete"))):
    actor, ws = ctx.session.get("user_id"), ctx.ws_id
    gone = macros.delete_macro(ctx.db.session, ws, macro_id)
    ctx.db.commit()
    ctx.close()
    if not gone:
        raise ApiError(404, "macro not found")
    care_audit.emit("care.template_change", actor=actor, ws=ws, target=macro_id,
                    after={"entity": "macro", "op": "delete"})
    return {"ok": True}


# --- apply to a case -------------------------------------------------------
def _macro_or_404(ctx: Ctx, macro_id: int) -> dict:
    macro = macros.get_macro(ctx.db.session, ctx.ws_id, macro_id)
    if not macro or not macro["active"]:
        ctx.close()
        raise ApiError(404, "macro not found")
    return macro


@router.post("/care/cases/{case_id}/macros/{macro_id}/preview")
def preview_macro(case_id: int, macro_id: int, ctx: Ctx = Depends(guard("care", "view"))):
    assert_case_access(ctx, case_id)
    macro = _macro_or_404(ctx, macro_id)
    try:
        out = macros.preview(ctx.db.session, ctx.ws_id, case_id, macro,
                             agent_id=ctx.session.get("user_id"))
    except LookupError as exc:
        _fail(ctx, exc)
    ctx.close()
    return out


@router.post("/care/cases/{case_id}/macros/{macro_id}/apply")
def apply_macro(case_id: int, macro_id: int, body: dict | None = Body(default=None),
                ctx: Ctx = Depends(guard("care", "edit"))):
    """Run the macro's *actions* (the reply text goes through the normal reply
    box so an agent always reviews / sends it). ``indexes`` limits which actions
    run — the composer's un-ticked chips."""
    assert_case_access(ctx, case_id)
    macro = _macro_or_404(ctx, macro_id)
    actor, ws = ctx.session.get("user_id"), ctx.ws_id
    indexes = (body or {}).get("indexes")
    try:
        results = macros.apply_actions(
            ctx.db.session, ws, case_id, macro, actor=actor,
            indexes=None if indexes is None else {int(i) for i in indexes})
        ctx.db.commit()
    except (macros.MacroError, LookupError, TypeError, ValueError) as exc:
        _fail(ctx, exc)
    ctx.close()
    care_audit.emit("care.macro_applied", actor=actor, ws=ws, target=case_id,
                    after={"macro_id": macro_id, "macro": macro["name"],
                           "results": [{"type": r["type"], "ok": r["ok"]} for r in results]})
    realtime.publish(f"queue:{ws}", {"kind": "macro", "case_id": case_id})
    realtime.publish(f"case:{case_id}", {"kind": "macro"})
    return {"ok": all(r["ok"] for r in results), "results": results}


# --- auto macros -----------------------------------------------------------
@router.get("/macro-rules")
def list_rules(ctx: Ctx = Depends(guard("templates", "edit"))):
    rows = macro_rules.list_rules(ctx.db.session, ctx.ws_id)
    ctx.close()
    return {"rules": rows, "trigger_types": list(macro_rules.TRIGGER_TYPES),
            "reply_modes": list(macro_rules.REPLY_MODES)}


@router.post("/macro-rules")
def create_rule(body: dict | None = Body(default=None),
                ctx: Ctx = Depends(guard("templates", "create"))):
    actor, ws = ctx.session.get("user_id"), ctx.ws_id
    try:
        rid = macro_rules.save_rule(ctx.db.session, ws, body, actor=actor)
        ctx.db.commit()
    except (macros.MacroError, LookupError) as exc:
        _fail(ctx, exc)
    ctx.close()
    care_audit.emit("care.template_change", actor=actor, ws=ws, target=rid,
                    after={"entity": "macro_rule", "op": "create"})
    return {"ok": True, "id": rid}


@router.put("/macro-rules/{rule_id}")
def update_rule(rule_id: int, body: dict | None = Body(default=None),
                ctx: Ctx = Depends(guard("templates", "edit"))):
    actor, ws = ctx.session.get("user_id"), ctx.ws_id
    try:
        macro_rules.save_rule(ctx.db.session, ws, body, rule_id=rule_id, actor=actor)
        ctx.db.commit()
    except (macros.MacroError, LookupError) as exc:
        _fail(ctx, exc)
    ctx.close()
    care_audit.emit("care.template_change", actor=actor, ws=ws, target=rule_id,
                    after={"entity": "macro_rule", "op": "update"})
    return {"ok": True}


@router.delete("/macro-rules/{rule_id}")
def delete_rule(rule_id: int, ctx: Ctx = Depends(guard("templates", "delete"))):
    actor, ws = ctx.session.get("user_id"), ctx.ws_id
    gone = macro_rules.delete_rule(ctx.db.session, ws, rule_id)
    ctx.db.commit()
    ctx.close()
    if not gone:
        raise ApiError(404, "rule not found")
    care_audit.emit("care.template_change", actor=actor, ws=ws, target=rule_id,
                    after={"entity": "macro_rule", "op": "delete"})
    return {"ok": True}
