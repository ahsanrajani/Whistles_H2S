"""MIS reports (build plan §6 / P4.10).

* ``daily_case_counts`` — opened / closed / reopened per day over a window,
  with totals.
* ``closed_case_report`` — the flat 13-column closed-case export: one row per
  case closed in the window, columns fixed and ordered so it drops straight
  into Excel / CSV.
"""
from datetime import datetime, time, timezone

from sqlalchemy import text

HEADERS = [
    "Case Ref", "Channel", "Customer", "Handle", "Opened At",
    "First Response At", "Closed At", "Assignee", "Closure Category",
    "First Response (s)", "Handle Time (s)", "Inbound Msgs", "Outbound Msgs",
]


def _bounds(start, end):
    return (datetime.combine(start, time.min, tzinfo=timezone.utc),
            datetime.combine(end, time.max, tzinfo=timezone.utc))


def _iso(v):
    return v.isoformat() if v is not None else None


def daily_case_counts(session, workspace_id, start, end) -> dict:
    lo, hi = _bounds(start, end)
    opened = dict(session.execute(text("""
        SELECT opened_at::date AS d, COUNT(*) FROM "case"
        WHERE workspace_id = :ws AND opened_at >= :lo AND opened_at <= :hi
        GROUP BY 1
    """), {"ws": workspace_id, "lo": lo, "hi": hi}).all())
    closed = dict(session.execute(text("""
        SELECT closed_at::date AS d, COUNT(*) FROM "case"
        WHERE workspace_id = :ws AND closed_at >= :lo AND closed_at <= :hi
        GROUP BY 1
    """), {"ws": workspace_id, "lo": lo, "hi": hi}).all())
    reopened = dict(session.execute(text("""
        SELECT ce.at::date AS d, COUNT(DISTINCT ce.case_id)
        FROM case_event ce JOIN "case" c ON c.id = ce.case_id
        WHERE c.workspace_id = :ws AND ce.kind = 'state_change'
              AND ce.at >= :lo AND ce.at <= :hi
              AND EXISTS (SELECT 1 FROM case_event p
                          WHERE p.case_id = ce.case_id AND p.kind = 'closed'
                                AND p.at < ce.at)
        GROUP BY 1
    """), {"ws": workspace_id, "lo": lo, "hi": hi}).all())

    days = sorted(set(opened) | set(closed) | set(reopened))
    rows = [{"day": d.isoformat(),
             "opened": int(opened.get(d, 0)),
             "closed": int(closed.get(d, 0)),
             "reopened": int(reopened.get(d, 0))} for d in days]
    return {
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "daily": rows,
        "totals": {"opened": sum(r["opened"] for r in rows),
                   "closed": sum(r["closed"] for r in rows),
                   "reopened": sum(r["reopened"] for r in rows)},
    }


def closed_case_report(session, workspace_id, start, end) -> dict:
    lo, hi = _bounds(start, end)
    rows = session.execute(text("""
        SELECT c.id, c.channel, cu.display_name, cu.handle,
               c.opened_at, c.first_response_at, c.closed_at,
               u.username AS assignee, c.closure_category,
               EXTRACT(EPOCH FROM (c.first_response_at - c.opened_at)) AS frt_s,
               EXTRACT(EPOCH FROM (c.closed_at - c.opened_at)) AS handle_s,
               (SELECT COUNT(*) FROM case_message m
                WHERE m.case_id = c.id AND m.direction = 'inbound')  AS inbound,
               (SELECT COUNT(*) FROM case_message m
                WHERE m.case_id = c.id AND m.direction = 'outbound') AS outbound
        FROM "case" c
        JOIN customer cu ON cu.id = c.customer_id
        LEFT JOIN "user" u ON u.id = c.assignee_id
        WHERE c.workspace_id = :ws AND c.closed_at >= :lo AND c.closed_at <= :hi
        ORDER BY c.closed_at
    """), {"ws": workspace_id, "lo": lo, "hi": hi}).mappings().all()

    def _row(r):
        return {
            HEADERS[0]: f"C-{r['id']}",
            HEADERS[1]: r["channel"],
            HEADERS[2]: r["display_name"],
            HEADERS[3]: r["handle"],
            HEADERS[4]: _iso(r["opened_at"]),
            HEADERS[5]: _iso(r["first_response_at"]),
            HEADERS[6]: _iso(r["closed_at"]),
            HEADERS[7]: r["assignee"],
            HEADERS[8]: r["closure_category"],
            HEADERS[9]: round(r["frt_s"]) if r["frt_s"] is not None else None,
            HEADERS[10]: round(r["handle_s"]) if r["handle_s"] is not None else None,
            HEADERS[11]: int(r["inbound"]),
            HEADERS[12]: int(r["outbound"]),
        }

    return {
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "headers": HEADERS,
        "count": len(rows),
        "rows": [_row(r) for r in rows],
    }
