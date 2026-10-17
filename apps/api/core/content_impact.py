"""Closed loop: did a published post help?

For each published calendar item, compare the rate of the relevant risk signal
in comments on the brand's own pages in the window *before* it went out with the
window *after*. A post created from a scam signal is judged on the scam-flag
rate; any other post on the complaint-word rate. A change is only reported when
the two Wilson intervals do not overlap (``stats.delta_is_real``); too few
comments, or a window that has not elapsed, says so rather than guessing.

This is association, not proof: other things happen in a week. The payload
carries the counts and windows so a reader can judge that for themselves.
"""
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import text as _sql

from db.analytics import scanners

from . import incidents, scam, stats
from .insights import _day_bucket

WINDOW_DAYS = 7
MIN_COMMENTS = 10                # per window, before a verdict is attempted
MIN_ELAPSED_DAYS = 3             # after-window days that must have passed
_ITEM_LIMIT = 20
_SCAN_LIMIT = 6000

_METRICS = {
    "scam": ("scam_flag_rate", "scam-flagged comments",
             lambda body: scam.score_text(body)[0] >= 1),
    "default": ("complaint_rate", "comments with complaint or incident words",
                lambda body: bool(incidents._keyword_hits(body))),     # noqa: SLF001
}


def _day(raw):
    d = _day_bucket(raw)
    return datetime.strptime(d, "%Y-%m-%d").date() if d else None


def _rate(k: int, n: int) -> dict:
    p, lo, hi = stats.wilson(k, n)
    return {"k": k, "n": n, "rate": round(p, 4) if n else None,
            "ci_low": round(lo, 4) if n else None, "ci_high": round(hi, 4) if n else None}


def judge(k1: int, n1: int, k2: int, n2: int, elapsed_days: int) -> tuple[str, str]:
    """(verdict, reason) for one before/after pair of counts."""
    if elapsed_days < MIN_ELAPSED_DAYS:
        return "too_early", (f"Only {max(elapsed_days, 0)} day(s) since it went out; "
                             f"needs {MIN_ELAPSED_DAYS}.")
    if min(n1, n2) < MIN_COMMENTS:
        return "not_enough_data", (f"{n1} comments before and {n2} after; needs at least "
                                   f"{MIN_COMMENTS} in each window.")
    if not stats.delta_is_real(k1, n1, k2, n2):
        return "no_durable_change", "The before and after intervals overlap."
    return (("improved", "The rate fell and the intervals do not overlap.")
            if k2 / n2 < k1 / n1 else
            ("worse", "The rate rose and the intervals do not overlap."))


def _published(session, ws):
    rows = session.execute(_sql("""
        SELECT c.id, c.title, c.channel, c.published_at,
               (SELECT e.detail FROM content_event e
                 WHERE e.content_id = c.id AND e.kind = 'signal_origin'
                 ORDER BY e.id LIMIT 1) AS origin
        FROM content_item c
        WHERE c.workspace_id = :ws AND c.state = 'published' AND c.published_at IS NOT NULL
        ORDER BY c.published_at DESC LIMIT :n
    """), {"ws": ws, "n": _ITEM_LIMIT}).mappings().all()
    return [dict(r) for r in rows]


def impact(db, ws, *, today=None) -> dict:
    session = db.session
    today = today or datetime.now(timezone.utc).date()
    comments = []
    for (_iid, _surface, _source, _outlet, _author, published_at, _url,
         title, body, raw_json, _brand) in scanners.scam_comment_rows(
            session, ws, list(scam.COMMENT_SOURCES), _SCAN_LIMIT):
        day = _day(published_at)
        if day is None:
            continue
        try:
            raw = json.loads(raw_json) if raw_json else {}
        except (TypeError, ValueError):
            raw = {}
        if not isinstance(raw, dict) or raw.get("kind") != "comment":
            continue
        text = " ".join(part for part in (title, body) if part)
        if text.strip():
            comments.append((day, text))

    out, tally = [], {"improved": 0, "no_durable_change": 0, "worse": 0, "pending": 0}
    for item in _published(session, ws):
        origin = item["origin"] or {}
        kind = "scam" if origin.get("signal_kind") == "scam" else "default"
        metric, label, hit = _METRICS[kind]
        pub = item["published_at"].astimezone(timezone.utc).date()
        before = [t for d, t in comments if pub - timedelta(days=WINDOW_DAYS) <= d < pub]
        after = [t for d, t in comments if pub <= d < pub + timedelta(days=WINDOW_DAYS)]
        k1, k2 = sum(map(hit, before)), sum(map(hit, after))
        elapsed = min((today - pub).days, WINDOW_DAYS)
        verdict, reason = judge(k1, len(before), k2, len(after), elapsed)
        tally["pending" if verdict in ("too_early", "not_enough_data") else verdict] += 1
        out.append({
            "id": item["id"], "title": item["title"], "channel": item["channel"],
            "published_at": item["published_at"].isoformat(),
            "from_signal": origin.get("signal"), "metric": metric, "measures": label,
            "before": _rate(k1, len(before)), "after": _rate(k2, len(after)),
            "verdict": verdict, "reason": reason,
        })
    return {"window_days": WINDOW_DAYS, "min_comments": MIN_COMMENTS,
            "min_elapsed_days": MIN_ELAPSED_DAYS, "items": out, "summary": tally,
            "note": "Association, not proof: other events in the same weeks also move these rates."}
