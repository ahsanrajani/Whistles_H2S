"""Content calendar API (build plan §6 / P4.6).

CRUD + the approval workflow for planned posts. Gated by the ``templates``
area: authoring is ``templates:edit`` / ``:create`` / ``:delete``; the
approve / reject decision is ``templates:approve``. Drag-drop on the calendar
is a ``PATCH`` of ``scheduled_for``.
"""
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, File, UploadFile
from sqlalchemy import text

import app as _app
from core import content_assist, content_calendar as cc, content_media
from integrations import write

from .deps import ApiError, Ctx, guard

router = APIRouter(prefix="/api/v1", tags=["content"])

_REVIEW = {"approve", "reject"}


def _iso(v):
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        raise ApiError(400, "expected an ISO-8601 datetime")


@router.get("/content")
def list_content(start: str = "", end: str = "", state: str | None = None,
                 ctx: Ctx = Depends(guard("templates", "view"))):
    d1 = date.fromisoformat(end) if end else date.today() + timedelta(days=30)
    d0 = date.fromisoformat(start) if start else d1 - timedelta(days=60)
    lo = datetime.combine(d0, datetime.min.time(), tzinfo=timezone.utc)
    hi = datetime.combine(d1, datetime.max.time(), tzinfo=timezone.utc)
    out = cc.calendar(ctx.db.session, ctx.ws_id, lo, hi, state=state)
    ctx.close()
    return out


@router.post("/content")
def create_content(body: dict | None = Body(default=None),
                   ctx: Ctx = Depends(guard("templates", "create"))):
    b = body or {}
    actor = ctx.session.get("user_id")
    try:
        cid = cc.create(ctx.db.session, ctx.ws_id, actor, title=b.get("title") or "",
                        body=b.get("body") or "", channel=b.get("channel"),
                        media=b.get("media"), scheduled_for=_iso(b.get("scheduled_for")),
                        assigned_to=b.get("assigned_to"))
    except cc.ContentError as exc:
        ctx.close()
        raise ApiError(400, str(exc))
    ctx.db.commit()
    ws = ctx.ws_id
    ctx.close()
    _app.audit(actor=actor, tenant_id=ws, action="content.create", target=cid)
    return {"ok": True, "id": cid}


@router.get("/content/{content_id}")
def get_content(content_id: int, ctx: Ctx = Depends(guard("templates", "view"))):
    try:
        out = cc.get(ctx.db.session, ctx.ws_id, content_id)
    except cc.ContentError as exc:
        ctx.close()
        raise ApiError(404, str(exc))
    ctx.close()
    return out


@router.patch("/content/{content_id}")
def update_content(content_id: int, body: dict | None = Body(default=None),
                   ctx: Ctx = Depends(guard("templates", "edit"))):
    b = dict(body or {})
    if "scheduled_for" in b:
        b["scheduled_for"] = _iso(b["scheduled_for"])
    actor = ctx.session.get("user_id")
    try:
        cc.update(ctx.db.session, ctx.ws_id, content_id, actor, **b)
    except cc.ContentError as exc:
        ctx.close()
        raise ApiError(400, str(exc))
    ctx.db.commit()
    ws = ctx.ws_id
    ctx.close()
    _app.audit(actor=actor, tenant_id=ws, action="content.edit", target=content_id)
    return {"ok": True}


@router.post("/content/{content_id}/transition")
def transition_content(content_id: int, body: dict | None = Body(default=None),
                       ctx: Ctx = Depends(guard("templates", "edit"))):
    b = body or {}
    action = b.get("action")
    if action in _REVIEW:
        ctx.close()
        raise ApiError(403, "use /content/{id}/review for approve / reject")
    actor = ctx.session.get("user_id")
    new_state, oa_id = _apply(ctx, content_id, action, actor, b)
    return {"ok": True, "state": new_state, "outbound_action_id": oa_id}


@router.post("/content/{content_id}/review")
def review_content(content_id: int, body: dict | None = Body(default=None),
                   ctx: Ctx = Depends(guard("templates", "approve"))):
    b = body or {}
    decision = b.get("decision")
    if decision not in _REVIEW:
        ctx.close()
        raise ApiError(400, "decision must be 'approve' or 'reject'")
    actor = ctx.session.get("user_id")
    new_state, _ = _apply(ctx, content_id, decision, actor, b)
    return {"ok": True, "state": new_state}


def _apply(ctx, content_id, action, actor, b):
    """Run one transition, wiring publish through the write layer. Commits and
    closes ``ctx``; returns (new_state, outbound_action_id|None)."""
    session, ws = ctx.db.session, ctx.ws_id
    oa_id = None
    try:
        if action == "publish":
            item = cc.get(session, ws, content_id)["item"]
            client = write.client_for(item["channel"] or "meta", _app.keys(ws))
            res = client.publish(session, ws, text=item["body"], actor=actor)
            oa_id = res.action_id
        new_state = cc.transition(session, ws, content_id, action, actor,
                                  note=b.get("note"), at=_iso(b.get("at")))
        if oa_id is not None:
            session.execute(text(
                "UPDATE content_item SET outbound_action_id = :o WHERE id = :i"),
                {"o": oa_id, "i": content_id})
    except cc.ContentError as exc:
        ctx.close()
        raise ApiError(400, str(exc))
    except ValueError as exc:
        ctx.close()
        raise ApiError(400, str(exc))
    session.commit()
    ctx.close()
    _app.audit(actor=actor, tenant_id=ws, action=f"content.{action}",
               target=content_id, after={"state": new_state})
    return new_state, oa_id


@router.post("/content/media")
async def upload_content_media(file: UploadFile = File(...),
                               ctx: Ctx = Depends(guard("templates", "edit"))):
    """One real picture/video upload -- see core/content_media.py. Returns
    the URL to add to a content item's `media` list."""
    ws = ctx.ws_id
    ctx.close()
    data = await file.read()
    try:
        out = content_media.save(ws, filename=file.filename or "",
                                 content_type=file.content_type or "", data=data)
    except content_media.UploadError as exc:
        raise ApiError(400, str(exc))
    return out


@router.post("/content/assist")
def suggest_content(body: dict | None = Body(default=None),
                    ctx: Ctx = Depends(guard("templates", "edit"))):
    """AI caption + hashtag suggestions for a draft post -- real, costed
    OpenRouter call, see core/content_assist.py. Never auto-applied; the
    caller pastes what it likes into the title/body fields."""
    b = body or {}
    try:
        out = content_assist.suggest(
            ctx.db.session, ctx.ws_id, topic=b.get("topic") or "",
            draft=b.get("draft") or "", channel=b.get("channel") or "",
            keys=_app.keys(ctx.ws_id))
    except content_assist.ContentAssistError as exc:
        ctx.close()
        raise ApiError(400, str(exc))
    ctx.close()
    return out


@router.delete("/content/{content_id}")
def delete_content(content_id: int, ctx: Ctx = Depends(guard("templates", "delete"))):
    actor = ctx.session.get("user_id")
    try:
        cc.delete(ctx.db.session, ctx.ws_id, content_id, actor)
    except cc.ContentError as exc:
        ctx.close()
        raise ApiError(400, str(exc))
    ctx.db.commit()
    ws = ctx.ws_id
    ctx.close()
    _app.audit(actor=actor, tenant_id=ws, action="content.delete", target=content_id)
    return {"ok": True}
