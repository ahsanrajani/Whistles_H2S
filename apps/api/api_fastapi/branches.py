"""Branch & ATM performance rollup and the full-network map layer.
FastAPI port of api/v1/routers/branches.py — same paths, same payloads."""
from fastapi import APIRouter, Depends

from core import branch_geo, branch_items, branch_perf, insights
from db.analytics import dashboards as dq

from .deps import Ctx, guard, resolve_period

router = APIRouter(prefix="/api/v1", tags=["branches"])


@router.get("/branches")
def branch_performance(period: str | None = None,
                       ctx: Ctx = Depends(guard("listening", "view"))):
    resolved, _days = resolve_period(period, "all")
    payload = branch_perf.scan(ctx.db, ctx.ws_id, days=insights.PERIODS[resolved])
    ctx.close()
    payload["period"] = resolved
    payload["period_label"] = insights.PERIOD_LABELS[resolved]
    return payload


@router.get("/branches/{key}/items")
def branch_item_list(key: str, period: str | None = None, issue: str | None = None,
                     offset: int = 0, limit: int = 25,
                     ctx: Ctx = Depends(guard("listening", "view"))):
    resolved, _days = resolve_period(period, "all")
    payload = branch_items.items(ctx.db, ctx.ws_id, key, days=insights.PERIODS[resolved],
                                 issue=issue or None, offset=offset, limit=limit)
    ctx.close()
    payload["period"] = resolved
    return payload


@router.get("/branches/map")
def branch_map(ctx: Ctx = Depends(guard("listening", "view"))):
    """Real branch geodata (data/branches.csv) merged with the branch_perf
    rollup — the full ~1,186-branch catalogue, not just those with signal."""
    branches = branch_geo.with_performance(ctx.db, ctx.ws_id)
    focus_name = dq.focus_brand_name(ctx.db.session, ctx.ws_id)
    ctx.close()
    flagged = sum(1 for b in branches if b["band"] in ("high", "elevated"))
    return {
        "focus_brand": focus_name,
        "branches": branches,
        "summary": {"total": len(branches), "flagged": flagged},
    }
