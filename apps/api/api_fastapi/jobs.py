"""Collection and scoring jobs: enqueue, poll, and the SSE log stream. FastAPI
port of api/v1/routers/jobs.py. The `job` table (P1.7) runs them; `_jobs` + the
`run` table are the live progress surface."""
import json
import time
import uuid

from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse

import app as _app
from db import repositories as repo
from jobs import runner

from .deps import Ctx, guard

router = APIRouter(prefix="/api/v1", tags=["jobs"])


def _running(prefix):
    jobs, lock = _app._jobs, _app._lock
    with lock:
        return next((key for key, value in jobs.items()
                     if key.startswith(prefix) and value.get("state") == "running"), None)


@router.post("/jobs/refresh")
def jobs_refresh(ctx: Ctx = Depends(guard("queue", "create"))):
    connection, workspace_id = ctx.db, ctx.ws_id
    running = repo.runs.running_id(connection.session, workspace_id)
    if running:
        ctx.close()
        return {"job_id": running, "already": True}
    job_id = uuid.uuid4().hex[:12]
    repo.runs.create(connection.session, run_id=job_id, workspace_id=workspace_id,
                     started_at=_app.now())
    runner.enqueue(connection.session, "collection",
                   {"ws": workspace_id, "run_id": job_id},
                   max_attempts=1, tenant_id=workspace_id)
    connection.commit()
    ctx.close()
    jobs, lock = _app._jobs, _app._lock
    with lock:
        jobs[job_id] = {"state": "queued", "lines": ["queued"]}
    return {"job_id": job_id, "already": False}


@router.post("/jobs/score")
def jobs_score(request: Request, body: dict | None = Body(default=None),
               ctx: Ctx = Depends(guard("queue", "create"))):
    connection, workspace_id = ctx.db, ctx.ws_id
    reset = bool((body or {}).get("reset") or request.query_params.get("reset"))
    running = _running("score-")
    if running:
        ctx.close()
        return {"job_id": running, "already": True}
    job_id = "score-" + uuid.uuid4().hex[:10]
    runner.enqueue(connection.session, "scoring",
                   {"ws": workspace_id, "handle": job_id, "reset": reset},
                   tenant_id=workspace_id)
    connection.commit()
    ctx.close()
    jobs, lock = _app._jobs, _app._lock
    with lock:
        jobs[job_id] = {"state": "queued", "lines": ["queued"]}
    return {"job_id": job_id, "already": False, "reset": reset}


def _job_snapshot(job_id):
    jobs, lock = _app._jobs, _app._lock
    with lock:
        job = jobs.get(job_id)
    if job:
        return {"state": job["state"], "lines": job.get("lines", [])}
    connection = _app.db_operator()
    row = repo.runs.state_progress(connection.session, job_id)
    connection.close()
    if not row:
        return None
    return {"state": row[0], "lines": json.loads(row[1] or "[]")[-40:]}


@router.get("/jobs/{job_id}")
def jobs_poll(job_id: str, _ctx: Ctx = Depends(guard("queue", "view"))):
    snapshot = _job_snapshot(job_id)
    if snapshot is None:
        return JSONResponse({"state": "unknown", "lines": []}, status_code=404)
    return snapshot


@router.get("/jobs/{job_id}/stream")
def jobs_stream(job_id: str, _ctx: Ctx = Depends(guard("queue", "view"))):
    """Server-sent events: one `data:` frame per poll until the worker settles."""
    terminal = {"done", "failed", "unknown"}

    def events():
        last = None
        for _ in range(1800):  # ~30 min ceiling, then the client reconnects
            snapshot = _job_snapshot(job_id) or {"state": "unknown", "lines": []}
            frame = json.dumps(snapshot)
            if frame != last:
                yield f"data: {frame}\n\n"
                last = frame
            if snapshot["state"] in terminal:
                return
            time.sleep(1)

    return StreamingResponse(events(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"})
