"""Alert center: evaluate the rules, and (admin-only) push firing alerts to the
configured webhooks. FastAPI port of api/v1/routers/alerts.py."""
from fastapi import APIRouter, Depends

import app as _app
from core import alerts

from .deps import Ctx, guard, require_feature

router = APIRouter(prefix="/api/v1", tags=["alerts"])


@router.get("/alerts")
def alerts_center(ctx: Ctx = Depends(guard("listening", "view"))):
    config = _app.keys(ctx.ws_id).get("ALERT_CONFIG")
    payload = alerts.evaluate(ctx.db, ctx.ws_id, config)
    ctx.close()
    return payload


@router.post("/alerts/dispatch")
def alerts_dispatch(ctx: Ctx = Depends(guard("admin", "create"))):
    """Admin-only. Evaluate now and push firing alerts to the configured webhooks."""
    require_feature(ctx, "cap.alerts_dispatch")
    keys = _app.keys(ctx.ws_id)
    evaluation = alerts.evaluate(ctx.db, ctx.ws_id, keys.get("ALERT_CONFIG"))
    ctx.close()
    return alerts.dispatch(
        evaluation,
        slack_url=(keys.get("ALERT_SLACK_WEBHOOK") or "").strip() or None,
        webhook_url=(keys.get("ALERT_WEBHOOK_URL") or "").strip() or None,
    )
