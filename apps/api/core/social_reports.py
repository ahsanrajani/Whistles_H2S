"""Social reports (build plan §6 / P4.5).

Views over the owned-analytics warehouse (P4.1) for one source:

* **account summary** — the page/account/org headline metrics for the window,
  each with a period-over-period delta; proportions Wilson-scored.
* **post scorecard** — per-post impressions / engagements / reactions and a
  Wilson-scored engagement rate, highest reach first.
* **video / Reels** — the same scorecard filtered to those media types.
* **engagement by media type** — engagement rate grouped by ``media_type``,
  each group Wilson-scored, so image-vs-video-vs-Reel is a fair comparison.
"""
from datetime import timedelta

from core import metrics
from db.analytics import metrics as q

_VIDEO = ("video",)
_REELS = ("reel", "reels")


def _post_row(r) -> dict:
    return {
        "post": r["entity_ref"],
        "media_type": r["media_type"],
        "first_day": r["first_day"].isoformat() if r["first_day"] else None,
        "last_day": r["last_day"].isoformat() if r["last_day"] else None,
        "impressions": float(r["impressions"]) if r["impressions"] is not None else None,
        "engagements": float(r["engagements"]) if r["engagements"] is not None else None,
        "reactions": float(r["reactions"]) if r["reactions"] is not None else None,
        "engagement_rate": metrics.measure(numerator=r["er_num"],
                                           denominator=r["er_den"]),
    }


def _scorecard(session, ws, source, start, end, media_types=None, limit=50):
    return [_post_row(r) for r in q.post_rows(
        session, ws, source=source, start=start, end=end,
        media_types=media_types, limit=limit)]


def _acct_measure(row) -> dict:
    return metrics.measure(value=row["sum_value"], numerator=row["sum_num"],
                           denominator=row["sum_den"], present=row["rows"] != 0)


def account_summary(session, ws, source, start, end):
    """Headline page/account/org metrics for the window, each with a delta
    against the immediately preceding equal-length window. Scoped to the
    non-post grains so post reach does not inflate the account totals."""
    length = (end - start).days + 1
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=length - 1)

    cur = {r["metric"]: r for r in q.account_rows(
        session, ws, source=source, start=start, end=end)}
    prev = {r["metric"]: r for r in q.account_rows(
        session, ws, source=source, start=prev_start, end=prev_end)}

    out = {}
    for metric in sorted(cur):
        m = _acct_measure(cur[metric])
        pm = (_acct_measure(prev[metric]) if metric in prev
              else {"kind": m["kind"], "value": None})
        delta = None
        if m["value"] is not None and pm["value"] is not None:
            delta = {"previous": pm["value"], "absolute": m["value"] - pm["value"],
                     "pct": ((m["value"] - pm["value"]) / pm["value"]
                             if pm["value"] else None)}
        elif pm["value"] is not None:
            delta = {"previous": pm["value"], "absolute": None, "pct": None}
        out[metric] = {"measure": m, "comparison": delta}
    return out


def report(session, ws, *, source, start, end, limit=50) -> dict:
    return {
        "source": source,
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "account": account_summary(session, ws, source, start, end),
        "posts": _scorecard(session, ws, source, start, end, limit=limit),
        "video": _scorecard(session, ws, source, start, end,
                            media_types=_VIDEO, limit=limit),
        "reels": _scorecard(session, ws, source, start, end,
                            media_types=_REELS, limit=limit),
        "engagement_by_media_type": [
            {"media_type": g["key"], **{k: v for k, v in g.items() if k != "key"}}
            for g in metrics.report(
                session, ws, source=source, metric="engagement_rate",
                start=start, end=end, entity_type="post",
                group_by="media_type", compare=False)["groups"]
        ],
    }
