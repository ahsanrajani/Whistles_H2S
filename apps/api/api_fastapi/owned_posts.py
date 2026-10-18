"""Recent owned posts (Vantage-adjacent) --
Meta, LinkedIn, YouTube and X in one feed, real permalinks + real engagement
counts where the platform exposes them. Reading (posts, comments) needs
listening:view like the rest of the listening surfaces; replying from here
needs care:edit, same gate as a Care reply, and goes through the identical
write layer (dry_run/GURU_WRITE_LIVE, outbound_action audit trail) -- this
is not tied to a Care case, so it skips cases.post_reply()."""
from fastapi import APIRouter, Body, Depends

import app as _app
from core import owned_posts
from integrations import write

from .deps import ApiError, Ctx, guard

router = APIRouter(prefix="/api/v1", tags=["owned_posts"])

VALID_PLATFORMS = {"facebook", "instagram", "linkedin", "youtube", "x"}


@router.get("/owned-posts")
def list_owned_posts(platform: str = "", limit: int = 25,
                     ctx: Ctx = Depends(guard("listening", "view"))):
    plat = platform if platform in VALID_PLATFORMS else None
    rows = owned_posts.recent(ctx.db.session, ctx.ws_id, platform=plat,
                              limit=min(max(limit, 1), 200))
    ctx.close()
    return {"posts": rows}


@router.get("/owned-posts/comments")
def list_comments(source: str, post_external_id: str,
                  ctx: Ctx = Depends(guard("listening", "view"))):
    rows = owned_posts.comments_for(ctx.db.session, ctx.ws_id, source=source,
                                    post_external_id=post_external_id)
    ctx.close()
    return {"comments": rows}


@router.post("/owned-posts/reply")
def reply_to_comment(body: dict | None = Body(default=None),
                     ctx: Ctx = Depends(guard("care", "edit"))):
    b = body or {}
    platform = b.get("platform")
    text_body = (b.get("text") or "").strip()
    target_ref = b.get("target_ref")
    if not platform or not text_body or not target_ref:
        ctx.close()
        raise ApiError(400, "platform, text and target_ref are required")
    try:
        client = write.client_for(platform, _app.keys(ctx.ws_id))
    except ValueError as exc:
        ctx.close()
        raise ApiError(400, str(exc))
    actor = ctx.session.get("user_id")
    result = client.reply_public(ctx.db.session, ctx.ws_id, target_ref=target_ref,
                                 text=text_body, actor=actor)
    ctx.db.commit()
    ws = ctx.ws_id
    ctx.close()
    _app.audit(actor=actor, tenant_id=ws, action="owned_posts.reply", target=target_ref,
               after={"platform": platform, "state": result.state})
    return {"ok": True, "state": result.state, "action_id": result.action_id}
