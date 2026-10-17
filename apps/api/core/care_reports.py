"""Care reports (build plan §6 / P4.3).

Agent shift metrics reconstructed from the ``agent_activity`` event stream —
session, ready, not-ready and idle seconds — joined with handling time taken
straight from ``case`` timestamps (``case_event`` is the SLA reconciliation
source in P4.4). One row per agent for a date window.
"""
from datetime import datetime, time, timezone

from sqlalchemy import text

from db import repositories as repo

# how an event sets the "current" ready-state bucket
_STATE = {"login": "ready", "ready": "ready", "active": "ready",
          "not_ready": "not_ready", "idle": "idle"}


def _overlap_seconds(lo, hi, win_lo, win_hi):
    lo = max(lo, win_lo)
    hi = min(hi, win_hi)
    return (hi - lo).total_seconds() if hi > lo else 0.0


def _walk(events, win_lo, win_hi):
    """events: ordered (kind, at) for ONE agent (may include one before win_lo).
    Returns {session, ready, not_ready, idle} seconds and a login count."""
    buckets = {"ready": 0.0, "not_ready": 0.0, "idle": 0.0}
    open_session = False
    state = None
    since = None
    logins = 0

    for kind, at in events:
        if open_session and state and since is not None:
            buckets[state] += _overlap_seconds(since, at, win_lo, win_hi)
        if kind == "logout":
            open_session = False
            state = None
            since = at
            continue
        if kind == "login":
            if at >= win_lo:
                logins += 1
            open_session = True
        else:
            open_session = True          # lenient: a bare ready/idle opens a shift
        state = _STATE.get(kind, state or "ready")
        since = at

    if open_session and state and since is not None:
        buckets[state] += _overlap_seconds(since, win_hi, win_lo, win_hi)

    session_seconds = sum(buckets.values())
    return {"session_seconds": session_seconds,
            "ready_seconds": buckets["ready"],
            "not_ready_seconds": buckets["not_ready"],
            "idle_seconds": buckets["idle"],
            "logins": logins}


def _day_bounds(start, end):
    lo = datetime.combine(start, time.min, tzinfo=timezone.utc)
    hi = datetime.combine(end, time.max, tzinfo=timezone.utc)
    return lo, hi


def agent_report(session, workspace_id, start, end) -> dict:
    """Per-agent session / ready / not-ready / idle seconds + handling time."""
    win_lo, win_hi = _day_bounds(start, end)

    rows = repo.agent_activity.window(session, workspace_id, win_lo, win_hi)
    by_user: dict[int, list] = {}
    for r in rows:
        by_user.setdefault(r["user_id"], []).append((r["kind"], r["at"]))

    handling = {r["assignee_id"]: r for r in session.execute(text("""
        SELECT assignee_id,
               COUNT(*)                                              AS cases_touched,
               COUNT(*) FILTER (WHERE closed_at IS NOT NULL)         AS cases_closed,
               AVG(EXTRACT(EPOCH FROM (first_response_at - opened_at)))
                   FILTER (WHERE first_response_at IS NOT NULL)      AS avg_first_response_s,
               AVG(EXTRACT(EPOCH FROM (closed_at - opened_at)))
                   FILTER (WHERE closed_at IS NOT NULL)              AS avg_handle_s
        FROM "case"
        WHERE workspace_id = :ws AND assignee_id IS NOT NULL
              AND opened_at >= :lo AND opened_at <= :hi
        GROUP BY assignee_id
    """), {"ws": workspace_id, "lo": win_lo, "hi": win_hi}).mappings().all()}

    names = dict(session.execute(text('SELECT id, username FROM "user"')).all())

    user_ids = sorted(set(by_user) | set(handling))
    agents = []
    for uid in user_ids:
        spans = _walk(by_user.get(uid, []), win_lo, win_hi)
        h = handling.get(uid, {})
        occ = float(h.get("avg_handle_s") or 0.0) * int(h.get("cases_closed") or 0)
        agents.append({
            "user_id": uid, "username": names.get(uid),
            **spans,
            "cases_touched": int(h.get("cases_touched") or 0),
            "cases_closed": int(h.get("cases_closed") or 0),
            "avg_first_response_seconds": (
                float(h["avg_first_response_s"]) if h.get("avg_first_response_s") is not None else None),
            "avg_handle_seconds": (
                float(h["avg_handle_s"]) if h.get("avg_handle_s") is not None else None),
            "occupancy": (occ / spans["ready_seconds"]
                          if spans["ready_seconds"] else None),
        })

    return {"window": {"start": start.isoformat(), "end": end.isoformat()},
            "agents": agents}
