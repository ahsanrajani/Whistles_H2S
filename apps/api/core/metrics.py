"""The metric layer (build plan §6 / P4.2).

A thin, honest read API over the P4.1 ``metric_fact`` warehouse:

* **measures** — a count metric rolls up as ``SUM(value)``; a proportion metric
  (one that stored numerator/denominator) rolls up as ``SUM(num)/SUM(den)`` and
  never renders without its Wilson interval (§0.4).
* **dimensions** — group a window by ``entity_ref`` / ``entity_type`` or a
  ``dims`` key (``media_type``, ``country``).
* **period comparison** — the immediately preceding window of equal length;
  proportion deltas are flagged ``significant`` only when the Wilson intervals
  do not overlap.

No value is fabricated: an empty window yields ``value: null``, not ``0``.
"""
from datetime import date, timedelta

from core import stats
from db.analytics import metrics as q

GROUPABLE = tuple(q.GROUPABLE)


class MetricError(ValueError):
    """Bad query — unknown group_by, malformed dates."""


def measure(*, value=None, numerator=None, denominator=None, present=True) -> dict:
    """Shape a measure dict: a proportion (with a Wilson interval) when a
    denominator is given, else a count. ``present=False`` marks an empty
    window — ``value: null``, never a fabricated 0."""
    if denominator is not None and denominator > 0:
        num = float(numerator or 0.0)
        den = float(denominator)
        p, lo, hi = stats.wilson(num, den)
        return {"kind": "proportion", "value": p, "numerator": num,
                "denominator": den, "wilson": [lo, hi]}
    if not present:
        return {"kind": "count", "value": None}
    return {"kind": "count", "value": float(value or 0.0)}


def _measure(row) -> dict:
    """Shape one aggregate row (sum_value / sum_num / sum_den / rows)."""
    return measure(value=row["sum_value"], numerator=row["sum_num"],
                   denominator=row["sum_den"], present=row["rows"] != 0)


def _delta(cur: dict, prev: dict) -> dict:
    out: dict = {"previous": prev["value"]}
    if cur["value"] is None or prev["value"] is None:
        out["absolute"] = out["pct"] = None
    else:
        out["absolute"] = cur["value"] - prev["value"]
        out["pct"] = ((cur["value"] - prev["value"]) / prev["value"]
                      if prev["value"] else None)
    if cur.get("kind") == "proportion" and prev.get("kind") == "proportion":
        out["significant"] = stats.delta_is_real(
            cur["numerator"], cur["denominator"],
            prev["numerator"], prev["denominator"])
    return out


def _as_date(v, field):
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v))
    except ValueError:
        raise MetricError(f"{field} must be an ISO date (YYYY-MM-DD)")


def report(session, workspace_id, *, source, metric, start, end,
           entity_type=None, group_by=None, compare=True) -> dict:
    start, end = _as_date(start, "start"), _as_date(end, "end")
    if end < start:
        raise MetricError("end is before start")
    if group_by is not None and group_by not in q.GROUPABLE:
        raise MetricError(f"cannot group by {group_by!r}; "
                          f"one of {sorted(q.GROUPABLE)}")

    kw = dict(source=source, metric=metric, entity_type=entity_type)
    headline = _measure(q.rollup(session, workspace_id, start=start, end=end, **kw))

    series = [
        {"day": r["day"].isoformat(),
         **{k: v for k, v in _measure(r).items() if k != "kind"}}
        for r in q.daily(session, workspace_id, start=start, end=end, **kw)
    ]

    out = {
        "source": source, "metric": metric, "entity_type": entity_type,
        "window": {"start": start.isoformat(), "end": end.isoformat(),
                   "days": (end - start).days + 1},
        "measure": headline,
        "series": series,
    }

    if group_by:
        rows = q.grouped(session, workspace_id, start=start, end=end,
                         group_by=group_by, **kw)
        out["group_by"] = group_by
        out["groups"] = [
            {"key": (r["grp"] if r["grp"] is not None else "unknown"),
             **_measure(r)} for r in rows
        ]

    if compare:
        length = (end - start).days + 1
        prev_end = start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=length - 1)
        prev = _measure(q.rollup(session, workspace_id,
                                 start=prev_start, end=prev_end, **kw))
        out["comparison"] = {
            "window": {"start": prev_start.isoformat(),
                       "end": prev_end.isoformat(), "days": length},
            **_delta(headline, prev),
        }

    return out


def catalog(session, workspace_id) -> dict:
    rows = q.catalog(session, workspace_id)
    return {"metrics": [
        {"source": r["source"], "metric": r["metric"],
         "entity_type": r["entity_type"], "rows": r["rows"],
         "first_day": r["first_day"].isoformat() if r["first_day"] else None,
         "last_day": r["last_day"].isoformat() if r["last_day"] else None,
         "is_proportion": bool(r["is_proportion"]),
         "dims": sorted(d for d in (r["dims"] or []) if d)}
        for r in rows
    ], "groupable": sorted(q.GROUPABLE)}
