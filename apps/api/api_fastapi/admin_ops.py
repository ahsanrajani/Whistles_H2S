"""Admin operational surface — split out of admin.py (which had grown past
the 600-line file limit): source health/retention/precision/
cost, owned-analytics, the one-off backfill buttons (care bridge, DM sync,
web backfill, owned-posts media/comment-link), the job/scheduler console,
and per-source retry/circuit-reset. No behavior change from the move."""
import uuid

from fastapi import APIRouter, Body, Depends
from sqlalchemy import text

import app as _app
from core import (care_bridge, dm_sync, insights, owned_analytics,
                  owned_comment_backfill, owned_media_backfill, precision,
                  routing, source_health, sources)
from db import repositories as repo
from jobs import runner

from .deps import ApiError, Ctx, guard

router = APIRouter(prefix="/api/v1", tags=["admin"])


@router.get("/admin/sources/health")
def admin_source_health(ctx: Ctx = Depends(guard("admin", "view"))):
    """Per-source collection health for this workspace (P2.3)."""
    payload = source_health.summary(ctx.db.session, ctx.ws_id)
    ctx.close()
    return payload


@router.get("/admin/retention")
def admin_retention(ctx: Ctx = Depends(guard("admin", "view"))):
    """Author retention policy per source class (P2.4)."""
    pol = repo.retention.policy(ctx.db.session, ctx.ws_id)
    ws_id = ctx.ws_id
    ctx.close()
    return {"workspace_id": ws_id, "policy": pol,
            "classes": list(repo.retention.CLASSES), "modes": list(repo.retention.MODES)}


@router.put("/admin/retention")
def admin_retention_set(body: dict | None = Body(default=None),
                        ctx: Ctx = Depends(guard("admin", "edit", operator=True))):
    body = body or {}
    source_class = body.get("source_class")
    mode = body.get("retention_mode")
    try:
        repo.retention.set_mode(ctx.db.session, ctx.ws_id, source_class, mode)
    except ValueError as exc:
        ctx.close()
        raise ApiError(400, str(exc))
    ctx.db.commit()
    ws_id, actor = ctx.ws_id, ctx.session.get("user_id")
    ctx.close()
    _app.audit(actor=actor, tenant_id=ws_id, action="retention.policy",
               target=source_class, after={"retention_mode": mode})
    # tightening to 'hashed' -> strip existing PII in the background
    job_id = None
    if mode == "hashed":
        conn = _app.db_operator()
        try:
            job_id = runner.enqueue(conn.session, "rehash_authors",
                                    {"ws": ws_id}, tenant_id=ws_id)
            conn.commit()
        finally:
            conn.close()
    return {"ok": True, "rehash_job": job_id}


@router.get("/admin/precision")
def admin_precision(ctx: Ctx = Depends(guard("admin", "view"))):
    """Match precision per brand × pattern class with Wilson intervals (P2.8)."""
    payload = precision.match_precision(ctx.db, ctx.ws_id)
    ctx.close()
    return payload


@router.get("/admin/cost")
def admin_cost(ctx: Ctx = Depends(guard("admin", "view"))):
    connection, workspace_id = ctx.db, ctx.ws_id
    scenario = repo.workspaces.volume_scenario(connection.session, workspace_id) or "mid"
    measured, model = insights.cost(connection, workspace_id, scenario)
    ctx.close()
    return {"scenario": scenario, "measured": measured, "model": model}


@router.get("/admin/owned-analytics")
def admin_owned_analytics(ctx: Ctx = Depends(guard("admin", "view"))):
    """Per-source owned-analytics ingestion state for this workspace (P4.1)."""
    payload = owned_analytics.status(ctx.db.session, ctx.ws_id)
    ctx.close()
    return payload


@router.post("/admin/owned-analytics/ingest")
def admin_owned_analytics_ingest(body: dict | None = Body(default=None),
                                 ctx: Ctx = Depends(guard("admin", "edit"))):
    """Queue an owned-analytics backfill: ``days`` days ending yesterday (P4.1)."""
    days = max(1, min(int((body or {}).get("days", 1)), 90))
    runner.enqueue(ctx.db.session, "owned_analytics",
                   {"ws": ctx.ws_id, "days": days}, tenant_id=ctx.ws_id)
    ctx.db.commit()
    ctx.close()
    return {"queued": True, "days": days}


@router.post("/admin/backfill/web/run")
def admin_web_backfill_run(ctx: Ctx = Depends(guard("admin", "edit", operator=True))):
    """Historical web backfill (year-qualified brand SERPs, see
    core/sources.py::web_backfill) -- an explicit one-off, never scheduled.
    Runs the same collection job path as a normal pass, scoped to that one
    source."""
    if repo.runs.running_id(ctx.db.session, ctx.ws_id):
        ctx.close()
        raise ApiError(409, "a collection run is already in progress for this workspace")
    job_id = uuid.uuid4().hex[:12]
    repo.runs.create(ctx.db.session, run_id=job_id, workspace_id=ctx.ws_id, started_at=_app.now())
    runner.enqueue(ctx.db.session, "collection",
                   {"ws": ctx.ws_id, "run_id": job_id, "only_sources": ["web_backfill"]},
                   max_attempts=1, tenant_id=ctx.ws_id)
    ctx.db.commit()
    actor, ws = ctx.session.get("user_id"), ctx.ws_id
    ctx.close()
    _app.audit(actor=actor, tenant_id=ws, action="admin.web_backfill", target=job_id)
    return {"queued": True, "job_id": job_id}


@router.post("/admin/care/bridge/run")
def admin_care_bridge_run(ctx: Ctx = Depends(guard("admin", "edit", operator=True))):
    """Pull already-collected, real complaint/question-shaped mentions
    (comments, reviews) into real Care cases with a working reply target.
    Idempotent -- see core/care_bridge.py."""
    actor = ctx.session.get("user_id")
    out = care_bridge.backfill(ctx.db.session, ctx.ws_id, actor=actor)
    ctx.db.commit()
    ws = ctx.ws_id
    ctx.close()
    _app.audit(actor=actor, tenant_id=ws, action="admin.care_bridge", after=out)
    return out


@router.post("/admin/dm/sync/run")
def admin_dm_sync_run(ctx: Ctx = Depends(guard("admin", "edit", operator=True))):
    """Poll Facebook Messenger + Instagram DM conversations and route any
    new message straight into Care. Real, live Graph API calls -- see
    core/dm_sync.py. 400s with a clear reason if Meta credentials aren't
    configured for this workspace."""
    actor = ctx.session.get("user_id")
    try:
        out = dm_sync.sync(ctx.db.session, ctx.ws_id, _app.keys(ctx.ws_id))
    except RuntimeError as exc:
        ctx.close()
        raise ApiError(400, str(exc))
    ctx.db.commit()
    ws = ctx.ws_id
    dm_sync.publish_events(out, ws)
    ctx.close()
    _app.audit(actor=actor, tenant_id=ws, action="admin.dm_sync", after=out)
    return out


@router.post("/admin/owned-posts/media-backfill/run")
def admin_media_backfill_run(ctx: Ctx = Depends(guard("admin", "edit", operator=True))):
    """Backfill real media (pictures/video) onto Facebook/Instagram posts
    collected before media capture shipped -- item is insert-only, so those
    rows can never pick it up from a normal re-collection. See
    core/owned_media_backfill.py. Idempotent; real, live Graph API calls."""
    actor = ctx.session.get("user_id")
    try:
        out = owned_media_backfill.backfill(ctx.db.session, ctx.ws_id, _app.keys(ctx.ws_id))
    except RuntimeError as exc:
        ctx.close()
        raise ApiError(400, str(exc))
    ctx.db.commit()
    ws = ctx.ws_id
    ctx.close()
    _app.audit(actor=actor, tenant_id=ws, action="admin.media_backfill", after=out)
    return out


@router.post("/admin/owned-posts/comment-backfill/run")
def admin_comment_backfill_run(ctx: Ctx = Depends(guard("admin", "edit", operator=True))):
    """Patch parent_id onto Facebook/Instagram comment/reply rows collected
    before nested-reply tracking existed -- item is insert-only, so those
    rows never pick it up from a normal re-collection. See
    core/owned_comment_backfill.py. Idempotent; real, live Graph API calls."""
    actor = ctx.session.get("user_id")
    out = owned_comment_backfill.backfill(ctx.db.session, ctx.ws_id, _app.keys(ctx.ws_id))
    ctx.db.commit()
    ws = ctx.ws_id
    ctx.close()
    _app.audit(actor=actor, tenant_id=ws, action="admin.comment_backfill", after=out)
    return out


@router.get("/admin/runs")
def admin_runs(ctx: Ctx = Depends(guard("admin", "view", operator=True))):
    runs = repo.runs.recent(ctx.db.session, 20, ctx.ws_id)
    ctx.close()
    return {"runs": [
        {"id": row[0], "started_at": row[1], "finished_at": row[2],
         "state": row[3], "new_items": row[4]} for row in runs]}


# --- F6.1: per-source manual retry / circuit reset ------------------
@router.post("/admin/sources/{source_id}/retry")
def admin_source_retry(source_id: str, ctx: Ctx = Depends(guard("admin", "edit"))):
    if source_id not in sources.SOURCES:
        ctx.close()
        raise ApiError(404, "unknown source")
    job_id = uuid.uuid4().hex[:12]
    repo.runs.create(ctx.db.session, run_id=job_id, workspace_id=ctx.ws_id,
                     started_at=_app.now())
    runner.enqueue(ctx.db.session, "collection",
                   {"ws": ctx.ws_id, "run_id": job_id, "only_sources": [source_id]},
                   max_attempts=1, tenant_id=ctx.ws_id)
    ctx.db.commit()
    actor, ws = ctx.session.get("user_id"), ctx.ws_id
    ctx.close()
    _app.audit(actor=actor, tenant_id=ws, action="admin.source_retry", target=source_id)
    return {"queued": True, "job_id": job_id}


@router.post("/admin/sources/{source_id}/reset-circuit")
def admin_source_reset_circuit(source_id: str, ctx: Ctx = Depends(guard("admin", "edit"))):
    if source_id not in sources.SOURCES:
        ctx.close()
        raise ApiError(404, "unknown source")
    repo.source_state.save(ctx.db.session, ctx.ws_id, source_id,
                           circuit_state="closed", consecutive_failures=0, opened_at=None)
    ctx.db.commit()
    actor, ws = ctx.session.get("user_id"), ctx.ws_id
    ctx.close()
    _app.audit(actor=actor, tenant_id=ws, action="admin.circuit_reset", target=source_id)
    return {"ok": True}


# --- F6.5: routing policy editor -----------------------------------
@router.get("/admin/routing-policy")
def admin_routing_policy(ctx: Ctx = Depends(guard("admin", "view"))):
    pol = routing.policy(ctx.db.session, ctx.ws_id)
    categories = [r[0] for r in ctx.db.session.execute(text(
        'SELECT DISTINCT closure_category FROM "case" '
        "WHERE workspace_id = :ws AND closure_category IS NOT NULL "
        "ORDER BY 1"), {"ws": ctx.ws_id}).all()]
    ctx.close()
    return {"policy": pol, "closure_categories_in_use": categories}


@router.put("/admin/routing-policy")
def admin_routing_policy_set(body: dict | None = Body(default=None),
                             ctx: Ctx = Depends(guard("admin", "edit"))):
    b = body or {}
    fields = {k: b.get(k) for k in
             ("first_response_sla", "resolution_sla", "escalation_after", "default_capacity")
             if b.get(k) is not None}
    routing.set_policy(ctx.db.session, ctx.ws_id, **fields)
    ctx.db.commit()
    actor, ws = ctx.session.get("user_id"), ctx.ws_id
    pol = routing.policy(ctx.db.session, ctx.ws_id)
    ctx.close()
    _app.audit(actor=actor, tenant_id=ws, action="admin.routing_policy", after=fields)
    return {"policy": pol}


# --- F6.6: job / scheduler console -----------------------------------
@router.get("/admin/jobs/queue")
def admin_jobs_queue(ctx: Ctx = Depends(guard("admin", "view", operator=True))):
    counts = dict(ctx.db.session.execute(text(
        "SELECT state, count(*) FROM job GROUP BY state")).all())
    dead = ctx.db.session.execute(text("""
        SELECT id, kind, attempts, max_attempts, last_error, updated_at
        FROM job WHERE state = 'dead' ORDER BY updated_at DESC LIMIT 50
    """)).mappings().all()
    ctx.close()
    return {"by_state": {s: counts.get(s, 0) for s in
                         ("queued", "running", "done", "dead")},
            "dead": [dict(r) for r in dead]}


@router.post("/admin/jobs/{job_id}/retry")
def admin_job_retry(job_id: int, ctx: Ctx = Depends(guard("admin", "edit", operator=True))):
    n = ctx.db.session.execute(text("""
        UPDATE job SET state = 'queued', attempts = 0, run_after = now(),
               last_error = NULL, locked_by = NULL, locked_at = NULL, updated_at = now()
        WHERE id = :id AND state = 'dead'
    """), {"id": job_id}).rowcount
    ctx.db.commit()
    actor = ctx.session.get("user_id")
    ctx.close()
    if not n:
        raise ApiError(404, "no dead job with that id")
    _app.audit(actor=actor, tenant_id=None, action="admin.job_retry", target=job_id)
    return {"ok": True}


@router.get("/admin/jobs/scheduled")
def admin_jobs_scheduled(ctx: Ctx = Depends(guard("admin", "view", operator=True))):
    tasks = repo.scheduled_task.all_tasks(ctx.db.session)
    ctx.close()
    return {"scheduled": [dict(t) for t in tasks]}
