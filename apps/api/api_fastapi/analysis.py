"""Deterministic analysis surfaces — scam, complaint triage, switch intent,
competitor incidents, product-line share, regulatory watch, impersonation.
FastAPI port of api/v1/routers/analysis.py; each endpoint returns its `core`
scanner's output verbatim (parity-tested)."""
import re

from fastapi import APIRouter, Depends

import app as _app
from core import (impersonation, incidents, insights, product_lines, regulatory,
                  scam, switch_intent, triage)

from .deps import Ctx, guard, resolve_period

router = APIRouter(prefix="/api/v1", tags=["analysis"])


def _stamp(payload: dict, period: str) -> dict:
    payload["period"] = period
    payload["period_label"] = insights.PERIOD_LABELS[period]
    return payload


@router.get("/scam")
def scam_signals(period: str | None = None, channel: str | None = None,
                 ctx: Ctx = Depends(guard("listening", "view"))):
    resolved, _days = resolve_period(period, "all")
    channel = (channel or "all").strip()
    surface = None if channel in ("", "all") else channel
    payload = scam.scan(ctx.db, ctx.ws_id, surface=surface,
                        days=insights.PERIODS[resolved])
    ctx.close()
    _stamp(payload, resolved)
    payload["channel"] = channel
    return payload


@router.get("/triage")
def complaint_triage(period: str | None = None,
                     ctx: Ctx = Depends(guard("listening", "view"))):
    resolved, _days = resolve_period(period, "all")
    payload = triage.scan(ctx.db, ctx.ws_id, days=insights.PERIODS[resolved])
    ctx.close()
    return _stamp(payload, resolved)


@router.get("/switch-intent")
def switch_intent_signals(period: str | None = None,
                          ctx: Ctx = Depends(guard("listening", "view"))):
    resolved, _days = resolve_period(period, "all")
    payload = switch_intent.scan(ctx.db, ctx.ws_id, days=insights.PERIODS[resolved])
    ctx.close()
    return _stamp(payload, resolved)


@router.get("/incidents")
def competitor_incidents(ctx: Ctx = Depends(guard("listening", "view"))):
    payload = incidents.scan(ctx.db, ctx.ws_id)
    ctx.close()
    return payload


@router.get("/product-lines")
def product_line_share(period: str | None = None,
                       ctx: Ctx = Depends(guard("listening", "view"))):
    resolved, _days = resolve_period(period, "all")
    payload = product_lines.scan(ctx.db, ctx.ws_id, days=insights.PERIODS[resolved])
    ctx.close()
    return _stamp(payload, resolved)


@router.get("/regulatory")
def regulatory_watch(ctx: Ctx = Depends(guard("listening", "view"))):
    payload = regulatory.summarize(ctx.db, ctx.ws_id)
    ctx.close()
    return payload


@router.get("/impersonation")
def impersonation_watch(ctx: Ctx = Depends(guard("admin", "view"))):
    """Admin-only. Live best-effort probe (DNS + crt.sh) — not a DB read."""
    ws_id = ctx.ws_id
    ctx.close()
    raw = _app.keys(ws_id).get("BRAND_DOMAINS") or ""
    domains = [part for part in re.split(r"[\s,]+", raw) if part]
    return impersonation.scan(domains)
