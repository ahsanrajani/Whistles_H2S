"""Content-calendar intelligence (compliance check, signal nudges, engagement
insights, closed-loop impact). Thin: each route resolves the tenant and calls one
service function in ``core/``. Mounted under ``/content/ai/`` so it can never
collide with ``/content/{content_id}``.
"""
from datetime import date, timedelta

from fastapi import APIRouter, Body, Depends

import app as _app
from core import (content_compliance, content_impact, content_insights,
                  content_signals)

from .deps import ApiError, Ctx, guard

router = APIRouter(prefix="/api/v1/content/ai", tags=["content-ai"])


def _date(raw: str, default: date) -> date:
    try:
        return date.fromisoformat(raw) if raw else default
    except ValueError:
        raise ApiError(400, "expected an ISO date")


@router.post("/compliance")
def check_compliance(body: dict | None = Body(default=None),
                     ctx: Ctx = Depends(guard("templates", "view"))):
    """Rule-based pre-approval check of a draft; optional Gemini rewrite."""
    b = body or {}
    out = content_compliance.review(ctx.db, ctx.ws_id, b.get("text") or "",
                                    want_rewrite=bool(b.get("rewrite")),
                                    keys=_app.keys(ctx.ws_id))
    ctx.close()
    return out


@router.get("/risk")
def calendar_risk(start: str = "", end: str = "",
                  ctx: Ctx = Depends(guard("templates", "view"))):
    """{content id: compliance severity} for the calendar window's drafts."""
    d1 = _date(end, date.today() + timedelta(days=30))
    d0 = _date(start, d1 - timedelta(days=60))
    out = content_compliance.risk_map(ctx.db.session, ctx.ws_id, d0, d1)
    ctx.close()
    return out


@router.get("/signals")
def signals(ctx: Ctx = Depends(guard("templates", "view"))):
    out = content_signals.nudges(ctx.db, ctx.ws_id)
    ctx.close()
    return out


@router.post("/signals/draft")
def draft_from_signal(body: dict | None = Body(default=None),
                      ctx: Ctx = Depends(guard("templates", "create"))):
    b = body or {}
    actor = ctx.session.get("user_id")
    try:
        out = content_signals.create_draft(
            ctx.db, ctx.ws_id, actor, b.get("key") or "",
            channel=b.get("channel") or content_signals.DEFAULT_CHANNEL,
            keys=_app.keys(ctx.ws_id))
    except content_signals.SignalError as exc:
        ctx.close()
        raise ApiError(404, str(exc))
    ctx.db.commit()
    ws = ctx.ws_id
    ctx.close()
    _app.audit(actor=actor, tenant_id=ws, action="content.create", target=out["id"],
               after={"from_signal": b.get("key")})
    return out


@router.get("/insights")
def insights(ctx: Ctx = Depends(guard("templates", "view"))):
    out = content_insights.performance(ctx.db, ctx.ws_id)
    ctx.close()
    return out


@router.get("/impact")
def impact(ctx: Ctx = Depends(guard("templates", "view"))):
    out = content_impact.impact(ctx.db, ctx.ws_id)
    ctx.close()
    return out
