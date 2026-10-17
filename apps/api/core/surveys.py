"""CSAT / survey module + complaint analytics (build plan §6 / P4.7).

A workspace has one or more ``survey`` definitions (CSAT / NPS / CES). Closing a
case *issues* a ``survey_response`` (a row with a ``token`` and no score yet);
recording a score buckets it deterministically. The reports Wilson-score every
proportion (CSAT %, response rate, NPS promoter/detractor share).

Complaint analytics run off ``case`` / ``case_event`` — volume, resolution
time, reopen rate, breakdown by closure category and channel — joined to the
CSAT scores for those cases.
"""
import secrets
from datetime import datetime, time, timezone

from sqlalchemy import text

from core import stats

_CSAT_LABELS = ("dissatisfied", "neutral", "satisfied")


def _bounds(start, end):
    return (datetime.combine(start, time.min, tzinfo=timezone.utc),
            datetime.combine(end, time.max, tzinfo=timezone.utc))


# --- definitions --------------------------------------------------
def ensure_default(session, workspace_id) -> int:
    row = session.execute(text(
        "SELECT id FROM survey WHERE workspace_id = :ws AND active ORDER BY id LIMIT 1"),
        {"ws": workspace_id}).first()
    if row:
        return int(row[0])
    return int(session.execute(text("""
        INSERT INTO survey (workspace_id, name, kind, scale_min, scale_max, question)
        VALUES (:ws, 'Post-resolution CSAT', 'csat', 1, 5,
                'How satisfied were you with how we handled this?')
        RETURNING id
    """), {"ws": workspace_id}).scalar_one())


def bucket_for(kind, score, lo, hi) -> str:
    if kind == "nps":
        if score >= 9:
            return "promoter"
        return "passive" if score >= 7 else "detractor"
    frac = (score - lo) / (hi - lo) if hi > lo else 0.0
    if frac >= 0.75:
        return "satisfied"
    return "neutral" if frac >= 0.5 else "dissatisfied"


# --- lifecycle --------------------------------------------------
def issue(session, workspace_id, *, case_id=None, survey_id=None,
          channel=None, customer_id=None) -> dict:
    survey_id = survey_id or ensure_default(session, workspace_id)
    token = secrets.token_urlsafe(18)
    rid = session.execute(text("""
        INSERT INTO survey_response
            (workspace_id, survey_id, case_id, customer_id, channel, token)
        VALUES (:ws, :s, :c, :cu, :ch, :tok)
        RETURNING id
    """), {"ws": workspace_id, "s": survey_id, "c": case_id, "cu": customer_id,
           "ch": channel, "tok": token}).scalar_one()
    return {"id": int(rid), "token": token, "survey_id": survey_id}


def on_case_closed(session, workspace_id, case_id) -> dict | None:
    """Issue the default survey when a case closes — unless one already went out
    for it, or the workspace has surveys turned off."""
    from core import features
    if not features.enabled(session, workspace_id, "cap.surveys"):
        return None
    exists = session.execute(text(
        "SELECT 1 FROM survey_response WHERE case_id = :c"), {"c": case_id}).first()
    if exists:
        return None
    row = session.execute(text(
        'SELECT channel, customer_id FROM "case" WHERE id = :c AND workspace_id = :ws'),
        {"c": case_id, "ws": workspace_id}).first()
    if not row:
        return None
    return issue(session, workspace_id, case_id=case_id, channel=row[0],
                 customer_id=row[1])


class SurveyError(ValueError):
    pass


def record(session, workspace_id, token, score, *, comment=None) -> dict:
    row = session.execute(text("""
        SELECT r.id, r.responded_at, s.kind, s.scale_min, s.scale_max
        FROM survey_response r JOIN survey s ON s.id = r.survey_id
        WHERE r.workspace_id = :ws AND r.token = :tok
    """), {"ws": workspace_id, "tok": token}).mappings().first()
    if not row:
        raise SurveyError("unknown survey token")
    if row["responded_at"] is not None:
        raise SurveyError("this survey has already been answered")
    lo, hi = row["scale_min"], row["scale_max"]
    if not isinstance(score, int) or score < lo or score > hi:
        raise SurveyError(f"score must be an integer in [{lo}, {hi}]")
    bucket = bucket_for(row["kind"], score, lo, hi)
    session.execute(text("""
        UPDATE survey_response
        SET score = :sc, comment = :co, bucket = :bk, responded_at = now()
        WHERE id = :id
    """), {"sc": score, "co": comment, "bk": bucket, "id": row["id"]})
    return {"id": row["id"], "bucket": bucket}


# --- reports --------------------------------------------------
def _wilson(k, n):
    if not n:
        return {"rate": None, "wilson": [None, None], "n": n, "k": k}
    p, lo, hi = stats.wilson(k, n)
    return {"rate": p, "wilson": [lo, hi], "n": n, "k": k}


def csat_report(session, workspace_id, start, end) -> dict:
    lo, hi = _bounds(start, end)
    rows = session.execute(text("""
        SELECT r.channel, r.score, r.bucket, r.comment,
               r.responded_at IS NOT NULL AS answered, s.kind
        FROM survey_response r JOIN survey s ON s.id = r.survey_id
        WHERE r.workspace_id = :ws AND r.issued_at >= :lo AND r.issued_at <= :hi
    """), {"ws": workspace_id, "lo": lo, "hi": hi}).mappings().all()

    issued = len(rows)
    answered = [r for r in rows if r["answered"]]
    scores = [r["score"] for r in answered if r["score"] is not None]
    satisfied = sum(1 for r in answered if r["bucket"] == "satisfied")
    promoters = sum(1 for r in answered if r["bucket"] == "promoter")
    detractors = sum(1 for r in answered if r["bucket"] == "detractor")

    dist: dict[int, int] = {}
    for s in scores:
        dist[s] = dist.get(s, 0) + 1

    by_channel: dict[str, dict] = {}
    for r in answered:
        c = by_channel.setdefault(r["channel"] or "unknown", {"n": 0, "satisfied": 0})
        c["n"] += 1
        c["satisfied"] += 1 if r["bucket"] == "satisfied" else 0

    nps = None
    if answered and any(r["kind"] == "nps" for r in answered):
        nps = round(100 * (promoters - detractors) / len(answered), 1)

    return {
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "issued": issued,
        "responses": len(answered),
        "response_rate": _wilson(len(answered), issued),
        "csat": _wilson(satisfied, len(answered)),
        "nps": nps,
        "avg_score": (sum(scores) / len(scores)) if scores else None,
        "distribution": {str(k): dist[k] for k in sorted(dist)},
        "by_channel": {
            k: _wilson(v["satisfied"], v["n"]) for k, v in sorted(by_channel.items())
        },
        "comments": [
            {"score": r["score"], "bucket": r["bucket"], "comment": r["comment"]}
            for r in answered if (r["comment"] or "").strip()
        ][:100],
    }


def complaint_report(session, workspace_id, start, end) -> dict:
    lo, hi = _bounds(start, end)
    rows = session.execute(text("""
        SELECT c.id, c.channel, c.state, c.closure_category,
               c.opened_at, c.closed_at,
               EXTRACT(EPOCH FROM (c.closed_at - c.opened_at)) AS resolution_s,
               EXISTS (SELECT 1 FROM case_event e
                       WHERE e.case_id = c.id AND e.kind = 'closed') AS was_closed,
               (SELECT AVG(sr.score) FROM survey_response sr WHERE sr.case_id = c.id) AS csat
        FROM "case" c
        WHERE c.workspace_id = :ws AND c.opened_at >= :lo AND c.opened_at <= :hi
    """), {"ws": workspace_id, "lo": lo, "hi": hi}).mappings().all()

    total = len(rows)
    closed = [r for r in rows if r["closed_at"] is not None]
    reopened = sum(1 for r in rows if r["was_closed"] and r["state"] != "closed")
    res_secs = [float(r["resolution_s"]) for r in closed if r["resolution_s"] is not None]
    csat_vals = [float(r["csat"]) for r in rows if r["csat"] is not None]

    def _tally(key):
        out: dict[str, int] = {}
        for r in rows:
            out[r[key] or "unspecified"] = out.get(r[key] or "unspecified", 0) + 1
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))

    daily: dict[str, int] = {}
    for r in rows:
        d = r["opened_at"].date().isoformat()
        daily[d] = daily.get(d, 0) + 1

    return {
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "total": total,
        "closed": len(closed),
        "open": total - len(closed),
        "reopen_rate": _wilson(reopened, total),
        "avg_resolution_seconds": (sum(res_secs) / len(res_secs)) if res_secs else None,
        "avg_csat": (sum(csat_vals) / len(csat_vals)) if csat_vals else None,
        "by_category": _tally("closure_category"),
        "by_channel": _tally("channel"),
        "daily_volume": {k: daily[k] for k in sorted(daily)},
    }
