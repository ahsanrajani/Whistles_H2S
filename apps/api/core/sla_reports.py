"""SLA reports (build plan §6 / P4.4).

Compliance %, first-response time, assignment wait and missed count for the
cases opened in a date window. Reconciled against ``case_event`` timestamps
(the ``assigned`` event for wait, the ``sla_breach`` event for misses) and the
workspace ``routing_policy`` targets. Every compliance figure is a proportion
of counts, so it carries a Wilson interval (§0.4).
"""
from datetime import datetime, time, timezone

from sqlalchemy import text

from core import routing, stats


def _bounds(start, end):
    return (datetime.combine(start, time.min, tzinfo=timezone.utc),
            datetime.combine(end, time.max, tzinfo=timezone.utc))


def _pct(values, q):
    if not values:
        return None
    s = sorted(values)
    if len(s) == 1:
        return float(s[0])
    idx = q * (len(s) - 1)
    lo = int(idx)
    frac = idx - lo
    hi = min(lo + 1, len(s) - 1)
    return float(s[lo] + (s[hi] - s[lo]) * frac)


def _distribution(values):
    return {"n": len(values),
            "avg": (sum(values) / len(values)) if values else None,
            "p50": _pct(values, 0.50),
            "p90": _pct(values, 0.90),
            "max": float(max(values)) if values else None}


def _compliance(met, total):
    p, lo, hi = stats.wilson(met, total) if total else (None, None, None)
    return {"met": met, "eligible": total, "rate": p, "wilson": [lo, hi]}


def sla_report(session, workspace_id, start, end, *, now=None) -> dict:
    lo, hi = _bounds(start, end)
    now = now or datetime.now(timezone.utc)
    p = routing.policy(session, workspace_id)
    frt_sla = int(p["first_response_sla"])
    res_sla = int(p["resolution_sla"])

    cases = session.execute(text("""
        SELECT id, opened_at, first_response_at, closed_at, state
        FROM "case"
        WHERE workspace_id = :ws AND opened_at >= :lo AND opened_at <= :hi
    """), {"ws": workspace_id, "lo": lo, "hi": hi}).mappings().all()

    assigned_at = dict(session.execute(text("""
        SELECT ce.case_id, MIN(ce.at)
        FROM case_event ce JOIN "case" c ON c.id = ce.case_id
        WHERE c.workspace_id = :ws AND ce.kind = 'assigned'
              AND c.opened_at >= :lo AND c.opened_at <= :hi
        GROUP BY ce.case_id
    """), {"ws": workspace_id, "lo": lo, "hi": hi}).all())

    breaches = session.execute(text("""
        SELECT COALESCE(ce.detail ->> 'check', 'unknown') AS check, COUNT(*) AS n
        FROM case_event ce JOIN "case" c ON c.id = ce.case_id
        WHERE c.workspace_id = :ws AND ce.kind = 'sla_breach'
              AND ce.at >= :lo AND ce.at <= :hi
        GROUP BY 1 ORDER BY 1
    """), {"ws": workspace_id, "lo": lo, "hi": hi}).mappings().all()

    frt_secs: list[float] = []
    frt_met = frt_eligible = 0
    res_met = res_eligible = 0
    wait_secs: list[float] = []

    for c in cases:
        opened = c["opened_at"]
        # first response
        if c["first_response_at"] is not None:
            d = (c["first_response_at"] - opened).total_seconds()
            frt_secs.append(d)
            frt_eligible += 1
            if d <= frt_sla:
                frt_met += 1
        elif (now - opened).total_seconds() > frt_sla:
            frt_eligible += 1                      # past due, never answered
        # resolution
        if c["closed_at"] is not None:
            res_eligible += 1
            if (c["closed_at"] - opened).total_seconds() <= res_sla:
                res_met += 1
        elif (now - opened).total_seconds() > res_sla:
            res_eligible += 1
        # assignment wait
        a = assigned_at.get(c["id"])
        if a is not None:
            wait_secs.append((a - opened).total_seconds())

    return {
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "policy": {"first_response_sla": frt_sla, "resolution_sla": res_sla},
        "cases": len(cases),
        "first_response": {
            "compliance": _compliance(frt_met, frt_eligible),
            "seconds": _distribution(frt_secs),
        },
        "resolution": {"compliance": _compliance(res_met, res_eligible)},
        "assignment_wait": {"seconds": _distribution(wait_secs)},
        "missed": {
            "total": sum(b["n"] for b in breaches),
            "by_check": {b["check"]: b["n"] for b in breaches},
        },
    }
