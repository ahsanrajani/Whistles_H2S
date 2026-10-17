"""The downloadable PDF highlights report. FastAPI port of
api/v1/routers/report.py."""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, Response

import app as _app
from core import report

from .deps import Ctx, guard, require_feature

router = APIRouter(prefix="/api/v1", tags=["report"])


@router.get("/report")
def report_pdf(ctx: Ctx = Depends(guard("reporting", "export"))):
    require_feature(ctx, "cap.export")
    if not report.PDF_OK:
        ctx.close()
        return JSONResponse(
            {"error": "PDF rendering unavailable — reportlab is not installed"},
            status_code=501)
    data = report.highlights(ctx.db, ctx.ws_id)
    ctx.close()
    _app.audit(actor=ctx.session.get("user_id"), tenant_id=ctx.ws_id,
               action="data.export", target="report.pdf")
    return Response(
        content=report.build_pdf(data),
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="guru-ears-highlights.pdf"',
            "Cache-Control": "no-store",
        },
    )
