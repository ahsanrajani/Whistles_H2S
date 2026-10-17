"""The calibration / review queue. FastAPI port of
api/v1/routers/calibration.py — gated by the `reporting:approve` permission."""
import uuid

from fastapi import APIRouter, Depends, File, UploadFile

import app as _app
from core import branch_complaints, insights
from db import repositories as repo
from jobs import runner

from .deps import ApiError, Ctx, guard

router = APIRouter(prefix="/api/v1", tags=["calibration"])

REVIEW_BATCH_FIELDS = (
    "brand", "surface", "source", "outlet", "published_at", "url", "text", "rule",
    "needs_review", "language", "sampled", "id",
)


@router.get("/review")
def review(ctx: Ctx = Depends(guard("reporting", "approve"))):
    connection, workspace_id = ctx.db, ctx.ws_id
    batch = [dict(zip(REVIEW_BATCH_FIELDS, row))
             for row in insights.review_batch(connection, workspace_id)]
    payload = {
        "calibration": insights.calibration_status(connection, workspace_id),
        "batch": batch,
    }
    ctx.close()
    return payload


@router.post("/review/branch-complaints/upload")
async def upload_branch_complaints(file: UploadFile = File(...),
                                   ctx: Ctx = Depends(guard("reporting", "approve"))):
    """Bulk-import branch complaints from a CSV (Branch Name, Complainant,
    Complaint Date, Complaint Text (paraphrased), Source URL). Inserted rows
    carry no sentiment/category — a scoring job is enqueued right after so
    the normal scanners fill those in, same as any other collected mention."""
    connection, workspace_id = ctx.db, ctx.ws_id
    data = await file.read()
    rows, header_error = branch_complaints.parse_csv(data)
    if header_error:
        ctx.close()
        raise ApiError(400, header_error)
    focus = repo.brands.focus_id_name(connection.session, workspace_id)
    if not focus:
        ctx.close()
        raise ApiError(400, "No active focus brand configured for this workspace")
    result = branch_complaints.import_rows(
        connection.session, workspace_id=workspace_id, brand_id=focus[0], rows=rows)
    connection.commit()
    job_id = None
    if result["inserted"]:
        job_id = "score-" + uuid.uuid4().hex[:10]
        runner.enqueue(connection.session, "scoring",
                       {"ws": workspace_id, "handle": job_id, "reset": False},
                       tenant_id=workspace_id)
        connection.commit()
        jobs, lock = _app._jobs, _app._lock
        with lock:
            jobs[job_id] = {"state": "queued", "lines": ["queued"]}
    ctx.close()
    return {**result, "job_id": job_id}


@router.post("/review/{mention_id}/{verdict}")
def review_label(mention_id: int, verdict: str,
                 ctx: Ctx = Depends(guard("reporting", "approve"))):
    if verdict not in ("yes", "no"):
        raise ApiError(404, "Not found")
    connection, workspace_id = ctx.db, ctx.ws_id
    repo.gold.upsert(connection.session, workspace_id=workspace_id, mention_id=mention_id,
                     correct=1 if verdict == "yes" else 0,
                     labelled_at=_app.now(), labelled_by=ctx.session.get("username"))
    connection.commit()
    ctx.close()
    return {"ok": True, "id": mention_id, "correct": verdict == "yes"}
