"""The client dashboard surfaces: overview, sentiment, competitors, reviews,
themes, plus the sidebar `stats` ticker. FastAPI port of
api/v1/routers/dashboards.py — every number comes straight from
`core.insights` / `core.report`, no recomputation."""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

import app as _app
from core import insights, report
from core.review_store import refresh as refresh_store_stats, review_context
from db.analytics import dashboards as dq

from .deps import Ctx, guard, resolve_period

router = APIRouter(prefix="/api/v1", tags=["dashboards"])

FEED_FIELDS = (
    "brand", "surface", "source", "outlet", "published_at", "url", "text", "rule",
    "needs_review", "language", "sampled", "id", "sentiment", "type",
)


@router.get("/stats")
def stats(ctx: Ctx = Depends(guard("listening", "view"))):
    items, mentions, last_run = dq.stats_counts(ctx.db.session, ctx.ws_id)
    ctx.close()
    return {"items": items, "mentions": mentions, "last_run": last_run}


@router.get("/overview")
def overview(period: str | None = None, channel: str | None = None,
             ctx: Ctx = Depends(guard("listening", "view"))):
    connection, workspace_id = ctx.db, ctx.ws_id
    if workspace_id is None:
        ctx.close()
        return JSONResponse({"error": "workspace required"}, status_code=409)
    period = period if period in insights.PERIODS else "30d"
    channel = (channel or "all").strip()
    surface = None if channel in ("", "all") else channel
    days = insights.PERIODS[period] or 365
    run_id = _app.latest_run(connection, workspace_id)
    sov = insights.share_of_voice(connection, workspace_id, surface)
    focus = next((brand for brand in sov if brand["focus"]), None)
    gaps, reached, total_outlets = insights.outlet_gap(
        connection, workspace_id, focus["name"] if focus else "", surface)
    ledger = insights.surface_ledger(connection, workspace_id, run_id) if run_id else []
    languages = insights.language_mix(connection, workspace_id, surface)
    sentiment = insights.sentiment_breakdown(connection, workspace_id, surface)
    reviews = insights.app_reviews(connection, workspace_id)
    deltas = insights.deltas(connection, workspace_id, days, surface)
    role = ctx.session.get("role")
    channels = dq.surfaces(connection.session, workspace_id)
    payload = {
        "period": period, "period_label": insights.PERIOD_LABELS[period],
        "channel": channel, "channels": channels, "focus": focus,
        "kpis": insights.kpis(connection, workspace_id, sov, sentiment, surface, days,
                               insights.PERIOD_LABELS[period], reviews, deltas),
        "deltas": deltas,
        "cards": insights.action_cards(connection, workspace_id, sov, gaps, ledger,
                                         languages, sentiment, role),
        "gauge": insights.gauge(sentiment),
        "priorities": report.priorities(connection, workspace_id),
        "report_ready": report.PDF_OK,
        "topic_volume": insights.press_volume(connection, workspace_id, days=days, surface=surface),
        "mix": insights.mention_mix(connection, workspace_id, surface, days),
        "sov": sov, "pairs": insights.indistinguishable_pairs(sov), "reviews": reviews,
        "themes": insights.themes(connection, workspace_id, focus["id"], surface=surface) if focus else [],
        "feed": [dict(zip(FEED_FIELDS, row)) for row in insights.feed(
            connection, workspace_id, 20, surface=surface)],
        "gaps": gaps[:12], "gap_total": len(gaps), "reached": reached,
        "total_outlets": total_outlets,
        "admin": ({"ledger": ledger, "rules": insights.rule_precision(connection, workspace_id),
                   "exclusions": insights.exclusions(connection, workspace_id)}
                  if role == "admin" else None),
    }
    ctx.close()
    return payload


@router.get("/sentiment")
def sentiment(period: str | None = None,
              ctx: Ctx = Depends(guard("listening", "view"))):
    connection, workspace_id = ctx.db, ctx.ws_id
    resolved, days = resolve_period(period)
    sov = insights.share_of_voice(connection, workspace_id)
    focus = next((brand for brand in sov if brand["focus"]), None)
    breakdown = insights.sentiment_breakdown(connection, workspace_id)
    themes_rows = insights.themes(connection, workspace_id, focus["id"], limit=30) if focus else []
    negative_feed = [row for row in insights.feed(connection, workspace_id, 150)
                     if row[12] == "neg"][:12]
    payload = {
        "period": resolved,
        "period_label": insights.PERIOD_LABELS[resolved],
        "focus": focus,
        "gauge": insights.gauge(breakdown),
        "trend": insights.sentiment_trend(connection, workspace_id),
        "breakdown": breakdown,
        "deltas": insights.deltas(connection, workspace_id, days),
        "neg_themes": [theme for theme in themes_rows if theme["lean"] == "negative"],
        "neg_feed": [dict(zip(FEED_FIELDS, row)) for row in negative_feed],
    }
    ctx.close()
    return payload


@router.get("/competitors")
def competitors(period: str | None = None,
                ctx: Ctx = Depends(guard("listening", "view"))):
    connection, workspace_id = ctx.db, ctx.ws_id
    resolved, days = resolve_period(period)
    sov = insights.share_of_voice(connection, workspace_id)
    focus = next((brand for brand in sov if brand["focus"]), None)
    gaps, reached, total_outlets = insights.outlet_gap(
        connection, workspace_id, focus["name"] if focus else "")
    payload = {
        "period": resolved,
        "period_label": insights.PERIOD_LABELS[resolved],
        "focus": focus,
        "sov": sov,
        "pairs": insights.indistinguishable_pairs(sov),
        "gaps": gaps,
        "gap_total": len(gaps),
        "reached": reached,
        "total_outlets": total_outlets,
        "deltas": insights.deltas(connection, workspace_id, days),
        "trend": insights.press_volume(connection, workspace_id, days=days),
        "outlets": [{"name": name, "n": count}
                    for name, count in insights.top_outlets(connection, workspace_id, limit=12)],
    }
    ctx.close()
    return payload


@router.get("/reviews")
def reviews(period: str | None = None,
            ctx: Ctx = Depends(guard("listening", "view"))):
    connection, workspace_id = ctx.db, ctx.ws_id
    resolved, days = resolve_period(period)
    review_data = insights.app_reviews(connection, workspace_id, recent_limit=50)
    focus = next((brand for brand in insights.share_of_voice(connection, workspace_id)
                  if brand["focus"]), None)
    payload = {
        **review_context(connection.session, workspace_id),
        "period": resolved,
        "period_label": insights.PERIOD_LABELS[resolved],
        "reviews": review_data,
        "deltas": insights.deltas(connection, workspace_id, days),
        "trend": insights.review_trend(connection, workspace_id),
        "timeline": insights.rating_timeline(connection, workspace_id, days=min(days, 180)),
        "themes": (insights.themes(connection, workspace_id, focus["id"],
                                    surface="app_reviews", min_count=2)
                   if focus else []),
    }
    ctx.close()
    return payload


@router.post("/reviews/store-stats/run")
def reviews_store_stats_run(ctx: Ctx = Depends(guard("admin", "edit", operator=True))):
    """Pull real average rating + total rating count for both stores, plus
    the Play Store's real 1-5 star breakdown, right now. Real, costed
    DataForSEO calls (Apple's side is free) -- never scheduled, same posture
    as the Vantage SEO/panel runs (core/review_store.py::refresh)."""
    keys = _app.keys(ctx.ws_id)
    lines: list[str] = []
    out = refresh_store_stats(ctx.db.session, ctx.ws_id, keys, log=lines.append)
    ctx.db.commit()
    actor, ws = ctx.session.get("user_id"), ctx.ws_id
    ctx.close()
    _app.audit(actor=actor, tenant_id=ws, action="reviews.store_stats_run", after=out)
    return {"ok": True, **out, "log": lines[-50:]}


@router.get("/themes")
def themes(ctx: Ctx = Depends(guard("listening", "view"))):
    connection, workspace_id = ctx.db, ctx.ws_id
    focus = next((brand for brand in insights.share_of_voice(connection, workspace_id)
                  if brand["focus"]), None)
    rows = insights.themes(connection, workspace_id, focus["id"], limit=48) if focus else []
    ctx.close()
    return {"focus": focus, "cloud": rows, "table": rows}
