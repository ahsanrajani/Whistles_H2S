"""Reporting & analytics API (build plan §6). P4.2 lands the metric layer here;
later P4 packets add the care / SLA / social report surfaces alongside it.

Thin: each route resolves the tenant and calls one ``core`` function. All
proportion measures arrive already Wilson-scored from ``core/metrics.py``.
"""
from datetime import date, timedelta

from fastapi import APIRouter, Body, Depends
from fastapi.responses import Response

import app as _app
from core import (care_reports, export_engine, metrics, mis, report_delivery,
                  sla_reports, social_reports, surveys)

from .deps import ApiError, Ctx, guard, require_feature

router = APIRouter(prefix="/api/v1", tags=["reports"])


def _window(start: str, end: str):
    if not end:
        end = date.today().isoformat()
    if not start:
        start = (date.fromisoformat(end) - timedelta(days=29)).isoformat()
    try:
        return date.fromisoformat(start), date.fromisoformat(end)
    except ValueError:
        raise ApiError(400, "start and end must be ISO dates (YYYY-MM-DD)")


@router.get("/reports/metrics/catalog")
def metrics_catalog(ctx: Ctx = Depends(guard("reporting", "view"))):
    """What is queryable for this workspace — (source, metric, entity_type),
    whether each is a proportion, and the dims present."""
    out = metrics.catalog(ctx.db.session, ctx.ws_id)
    ctx.close()
    return out


@router.get("/reports/metrics")
def metrics_query(source: str, metric: str,
                  start: str = "", end: str = "",
                  entity_type: str | None = None,
                  group_by: str | None = None,
                  compare: bool = True,
                  ctx: Ctx = Depends(guard("reporting", "view"))):
    """A measure over a date window: headline (Wilson-scored if a proportion),
    daily series, optional dimension breakdown, and the preceding equal-length
    window for comparison."""
    if not end:
        end = date.today().isoformat()
    if not start:
        start = (date.fromisoformat(end) - timedelta(days=29)).isoformat()
    try:
        out = metrics.report(
            ctx.db.session, ctx.ws_id, source=source, metric=metric,
            start=start, end=end, entity_type=entity_type,
            group_by=group_by, compare=compare)
    except metrics.MetricError as exc:
        ctx.close()
        raise ApiError(400, str(exc))
    ctx.close()
    return out


@router.get("/reports/care/agents")
def care_agent_report(start: str = "", end: str = "",
                      ctx: Ctx = Depends(guard("reporting", "view"))):
    """Per-agent session / ready / not-ready / idle seconds (from
    ``agent_activity``) and handling time (from ``case`` timestamps)."""
    d0, d1 = _window(start, end)
    out = care_reports.agent_report(ctx.db.session, ctx.ws_id, d0, d1)
    ctx.close()
    return out


@router.get("/reports/social")
def social_report(source: str, start: str = "", end: str = "", limit: int = 50,
                  ctx: Ctx = Depends(guard("reporting", "view"))):
    """Owned-social report for one source: account summary (with deltas), post /
    video / Reel scorecards, and engagement rate by media type — all
    Wilson-scored where they are proportions."""
    d0, d1 = _window(start, end)
    out = social_reports.report(ctx.db.session, ctx.ws_id, source=source,
                                start=d0, end=d1, limit=max(1, min(limit, 200)))
    ctx.close()
    return out


@router.get("/reports/sla")
def sla_report(start: str = "", end: str = "",
               ctx: Ctx = Depends(guard("reporting", "view"))):
    """First-response / resolution compliance (Wilson-scored), first-response
    and assignment-wait time distributions, and the missed-SLA count —
    reconciled against ``case_event``."""
    d0, d1 = _window(start, end)
    out = sla_reports.sla_report(ctx.db.session, ctx.ws_id, d0, d1)
    ctx.close()
    return out


@router.get("/reports/mis/daily")
def mis_daily(start: str = "", end: str = "",
              ctx: Ctx = Depends(guard("reporting", "view"))):
    """MIS: opened / closed / reopened case counts per day, with totals."""
    d0, d1 = _window(start, end)
    out = mis.daily_case_counts(ctx.db.session, ctx.ws_id, d0, d1)
    ctx.close()
    return out


@router.get("/reports/mis/closed-cases")
def mis_closed_cases(start: str = "", end: str = "",
                     ctx: Ctx = Depends(guard("reporting", "view"))):
    """MIS: the flat 13-column closed-case report for the window."""
    d0, d1 = _window(start, end)
    out = mis.closed_case_report(ctx.db.session, ctx.ws_id, d0, d1)
    ctx.close()
    return out


@router.get("/reports/export")
def export_report(kind: str, format: str = "pdf",
                  source: str = "", metric: str = "",
                  start: str = "", end: str = "",
                  ctx: Ctx = Depends(guard("reporting", "export"))):
    """Render any P4 report to CSV / Excel / PDF (with charts). ``kind`` is one
    of metrics · sla · csat · complaints · care_agents · social · mis_daily ·
    mis_closed."""
    require_feature(ctx, "cap.export")
    d0, d1 = _window(start, end)
    s, ws = ctx.db.session, ctx.ws_id
    try:
        payload = report_delivery.build_report(
            s, ws, kind, d0, d1, source=source or None, metric=metric or None)
        media, ext, blob = export_engine.render(
            payload, format, title=f"{kind} report {d0}..{d1}")
    except (metrics.MetricError, ValueError) as exc:
        ctx.close()
        raise ApiError(400, str(exc))
    actor = ctx.session.get("user_id")
    ctx.close()
    _app.audit(actor=actor, tenant_id=ws, action="data.export",
               target=f"report.{kind}.{ext}")
    return Response(content=blob, media_type=media, headers={
        "Content-Disposition": f'attachment; filename="{kind}-report.{ext}"',
        "Cache-Control": "no-store"})


@router.get("/reports/csat")
def csat_report(start: str = "", end: str = "",
                ctx: Ctx = Depends(guard("reporting", "view"))):
    """CSAT %, response rate and (for NPS surveys) NPS — every proportion
    Wilson-scored — plus score distribution and per-channel breakdown."""
    d0, d1 = _window(start, end)
    out = surveys.csat_report(ctx.db.session, ctx.ws_id, d0, d1)
    ctx.close()
    return out


@router.get("/reports/complaints")
def complaint_report(start: str = "", end: str = "",
                     ctx: Ctx = Depends(guard("reporting", "view"))):
    """Complaint volume, resolution time, Wilson-scored reopen rate, breakdown
    by closure category and channel, and the CSAT for those cases."""
    d0, d1 = _window(start, end)
    out = surveys.complaint_report(ctx.db.session, ctx.ws_id, d0, d1)
    ctx.close()
    return out


# --- scheduled distribution (P4.9) ---------------------------------
@router.get("/reports/schedules")
def list_report_schedules(ctx: Ctx = Depends(guard("reporting", "view"))):
    out = report_delivery.list_schedules(ctx.db.session, ctx.ws_id)
    ctx.close()
    return {"schedules": out}


def _schedule_body(b: dict):
    return dict(name=b.get("name") or "Report", kind=b.get("kind"),
                cron=b.get("cron") or "0 7 * * 1", fmt=b.get("format", "pdf"),
                params=b.get("params") or {}, recipients=b.get("recipients") or [],
                active=b.get("active", True))


@router.post("/reports/schedules")
def create_report_schedule(body: dict | None = Body(default=None),
                           ctx: Ctx = Depends(guard("reporting", "export"))):
    require_feature(ctx, "cap.report_email")
    actor = ctx.session.get("user_id")
    try:
        sid = report_delivery.upsert(ctx.db.session, ctx.ws_id, actor=actor,
                                     **_schedule_body(body or {}))
    except report_delivery.DeliveryError as exc:
        ctx.close()
        raise ApiError(400, str(exc))
    ctx.db.commit()
    ws = ctx.ws_id
    ctx.close()
    _app.audit(actor=actor, tenant_id=ws, action="report.schedule", target=sid)
    return {"ok": True, "id": sid}


@router.put("/reports/schedules/{schedule_id}")
def update_report_schedule(schedule_id: int, body: dict | None = Body(default=None),
                           ctx: Ctx = Depends(guard("reporting", "export"))):
    try:
        report_delivery.upsert(ctx.db.session, ctx.ws_id, schedule_id=schedule_id,
                               **_schedule_body(body or {}))
    except report_delivery.DeliveryError as exc:
        ctx.close()
        raise ApiError(400, str(exc))
    ctx.db.commit()
    ctx.close()
    return {"ok": True}


@router.delete("/reports/schedules/{schedule_id}")
def delete_report_schedule(schedule_id: int,
                           ctx: Ctx = Depends(guard("reporting", "export"))):
    try:
        report_delivery.delete(ctx.db.session, ctx.ws_id, schedule_id)
    except report_delivery.DeliveryError as exc:
        ctx.close()
        raise ApiError(404, str(exc))
    ctx.db.commit()
    ctx.close()
    return {"ok": True}


@router.post("/reports/schedules/{schedule_id}/run")
def run_report_schedule(schedule_id: int,
                        ctx: Ctx = Depends(guard("reporting", "export"))):
    """Render and send this schedule now (also how a test drives it)."""
    require_feature(ctx, "cap.report_email")
    actor = ctx.session.get("user_id")
    try:
        out = report_delivery.run(ctx.db.session, ctx.ws_id, schedule_id,
                                  keys=_app.keys(ctx.ws_id))
    except (report_delivery.DeliveryError, ValueError) as exc:
        ctx.close()
        raise ApiError(400, str(exc))
    ctx.db.commit()
    ws = ctx.ws_id
    ctx.close()
    _app.audit(actor=actor, tenant_id=ws, action="report.sent",
               target=schedule_id, after={"status": out["status"]})
    return out
