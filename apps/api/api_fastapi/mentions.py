"""The mentions table: filtered evidence rows, CSV export and hide/show.
FastAPI port of api/v1/routers/mentions.py."""
import csv
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

import app as _app
from core import classify, insights, sources
from db import repositories as repo
from db.analytics import dashboards as dq

from .deps import ApiError, Ctx, guard, require_feature

router = APIRouter(prefix="/api/v1", tags=["mentions"])

SINCE_DAYS = {"7d": 7, "30d": 30, "90d": 90, "all": None}
MENTION_SORTS = {"new", "old", "top", "low", "spread"}
RATING_BANDS = {"high", "mid", "low", "1", "2", "3", "4", "5"}
EVIDENCE_FIELDS = (
    "id", "brand_id", "brand", "surface", "source", "source_kind", "outlet",
    "author", "published_at", "collected_at", "collection_run_id", "url", "text",
    "rule", "needs_review", "sampled", "language", "sentiment", "rating", "type",
    "hidden", "other_brands",
)


def _int_or_none(raw):
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _mention_filters(request: Request):
    args = request.query_params
    since_key = args.get("since", "all")
    since_key = since_key if since_key in SINCE_DAYS else "all"
    category = (args.get("type") or "").strip()
    category = category if category in classify.LABEL_OF else ""
    sort = args.get("sort", "new")
    sort = sort if sort in MENTION_SORTS else "new"
    rating = (args.get("rating") or "").strip()
    rating = rating if rating in RATING_BANDS else ""
    return since_key, {
        "brand_id": _int_or_none(args.get("brand_id")),
        "outlet": (args.get("outlet") or "").strip(),
        "surface": (args.get("surface") or "").strip(),
        "rule": (args.get("rule") or "").strip(),
        "sentiment": (args.get("sentiment") or "").strip(),
        "q": (args.get("q") or "").strip(),
        "category": category, "rating": rating, "sort": sort,
        "since": SINCE_DAYS[since_key],
    }


@router.get("/mentions")
def mentions(request: Request, ctx: Ctx = Depends(guard("listening", "view"))):
    connection, workspace_id = ctx.db, ctx.ws_id
    since_key, filters = _mention_filters(request)
    is_admin = ctx.session.get("role") == "admin"
    rows, total = insights.evidence(
        connection, workspace_id, limit=150, include_hidden=is_admin, **filters)
    brands = [{"id": bid, "name": name}
              for bid, name in repo.brands.active_id_name(connection.session, workspace_id)]
    surfaces = dq.surfaces(connection.session, workspace_id)
    outlets = dq.outlets(connection.session, workspace_id)
    filters["since"] = since_key
    payload = {
        "rows": [dict(zip(EVIDENCE_FIELDS, row)) for row in rows], "total": total,
        "mix": insights.mention_mix(connection, workspace_id, filters["surface"] or None),
        "filters": filters,
        "facets": {"brands": brands, "surfaces": surfaces, "outlets": outlets,
                   "categories": [{"key": key, "label": classify.LABEL_OF[key]}
                                  for key, _hypothesis, _colour in classify.CATEGORIES]},
        "is_admin": is_admin,
        "source_meta": {key: {"label": value["label"], "surface": value["surface"]}
                        for key, value in sources.SOURCES.items()},
    }
    ctx.close()
    return payload


@router.get("/mentions/export.csv")
def mentions_export(request: Request, ctx: Ctx = Depends(guard("reporting", "export"))):
    require_feature(ctx, "cap.export")
    connection, workspace_id = ctx.db, ctx.ws_id
    _since_key, filters = _mention_filters(request)
    rows, _total = insights.evidence(connection, workspace_id, limit=5000, **filters)
    # provenance column (P2.4): item.source_class per row
    ids = [row[0] for row in rows]
    source_class = {}
    if ids:
        for iid, sclass in connection.execute(
                "SELECT id, source_class FROM item WHERE id = ANY(?)", (ids,)).fetchall():
            source_class[iid] = sclass
    ctx.close()
    _app.audit(actor=ctx.session.get("user_id"), tenant_id=workspace_id,
               action="data.export", target="mentions.csv",
               after={"filters": {k: v for k, v in filters.items() if v},
                      "rows": len(rows)})
    header = ["mention_id", "brand", "surface", "source", "source_class",
              "source_kind", "outlet", "author", "published_at", "collected_at",
              "url", "text", "rule", "sentiment", "rating", "type", "also_names"]

    def generate():
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(header)
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)
        for row in rows:
            item = dict(zip(EVIDENCE_FIELDS, row))
            writer.writerow([
                item["id"], item["brand"], item["surface"], item["source"],
                source_class.get(item["id"]) or "",
                item["source_kind"], item["outlet"], item["author"], item["published_at"],
                item["collected_at"], item["url"],
                (item["text"] or "").replace("\r", " ").replace("\n", " "),
                item["rule"], item["sentiment"] or "", item["rating"] or "",
                item["type"] or "", item["other_brands"] or "",
            ])
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate(0)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    tag = filters["surface"] or "all"
    return StreamingResponse(generate(), media_type="text/csv", headers={
        "Content-Disposition": f'attachment; filename="guru-ears-{tag}-{stamp}.csv"'})


@router.post("/mentions/{mention_id}/{action}")
def mention_visibility(mention_id: int, action: str,
                       ctx: Ctx = Depends(guard("listening", "edit"))):
    if action not in ("hide", "show"):
        raise ApiError(404, "Not found")
    connection, workspace_id = ctx.db, ctx.ws_id
    affected = repo.mentions.set_hidden(
        connection.session, mention_id, workspace_id, action == "hide")
    connection.commit()
    ctx.close()
    if not affected:
        raise ApiError(404, "Mention not found")
    _app.audit(actor=ctx.session.get("user_id"), tenant_id=workspace_id,
               action=f"mention.{action}", target=mention_id)
    return {"ok": True, "id": mention_id, "hidden": action == "hide"}
