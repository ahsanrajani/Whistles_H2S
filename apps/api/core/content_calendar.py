"""Content calendar + approval workflow (build plan §6 / P4.6).

A ``content_item`` is a planned post. Its lifecycle:

    draft ──submit──▶ in_review ──approve──▶ approved ──schedule──▶ scheduled
      ▲                   │                     │                      │
      └──── revise ───────┴──── reject ─────────┘        publish ──▶ published

``scheduled_for`` is the calendar slot — a drag-drop is just a PATCH of it.
Every transition writes a ``content_event`` row (actor + optional note), which
is the approval trail. Publishing hands off to the P3.1 write layer.
"""
import json
from datetime import datetime, timezone

from sqlalchemy import text

_EDITABLE = {"draft", "rejected", "in_review"}

# state -> {transition: next_state}
_TRANSITIONS = {
    "draft":     {"submit": "in_review"},
    "in_review": {"approve": "approved", "reject": "rejected", "retract": "draft"},
    "rejected":  {"revise": "draft", "resubmit": "in_review"},
    "approved":  {"schedule": "scheduled", "unapprove": "draft"},
    "scheduled": {"publish": "published", "unschedule": "approved"},
    "published": {},
}

_FIELDS = ("title", "body", "channel", "media", "scheduled_for", "assigned_to")


class ContentError(ValueError):
    """Bad transition or an edit to a locked item."""


def _now():
    return datetime.now(timezone.utc)


def _event(session, content_id, kind, actor, *, note=None, **detail):
    session.execute(text(
        "INSERT INTO content_event (content_id, actor, kind, note, detail) "
        "VALUES (:c, :a, :k, :n, CAST(:d AS jsonb))"),
        {"c": content_id, "a": None if actor is None else str(actor),
         "k": kind, "n": note, "d": json.dumps(detail)})


def _row(session, ws, content_id):
    r = session.execute(text(
        "SELECT * FROM content_item WHERE id = :i AND workspace_id = :ws"),
        {"i": content_id, "ws": ws}).mappings().first()
    if not r:
        raise ContentError("content item not found")
    return r


def create(session, workspace_id, actor, *, title, body="", channel=None,
           media=None, scheduled_for=None, assigned_to=None) -> int:
    if not (title or "").strip():
        raise ContentError("title is required")
    cid = session.execute(text("""
        INSERT INTO content_item
            (workspace_id, title, body, channel, media, scheduled_for,
             assigned_to, created_by)
        VALUES (:ws, :t, :b, :ch, CAST(:m AS jsonb), :sf, :asg, :by)
        RETURNING id
    """), {"ws": workspace_id, "t": title.strip(), "b": body or "",
           "ch": channel, "m": json.dumps(media or []),
           "sf": scheduled_for, "asg": assigned_to, "by": actor}).scalar_one()
    _event(session, cid, "created", actor)
    return int(cid)


def record_origin(session, content_id, actor, origin: dict) -> None:
    """Remember which live signal a draft was created from, so the closed loop
    (core/content_impact.py) can later measure whether the post helped."""
    _event(session, content_id, "signal_origin", actor, **origin)


def update(session, workspace_id, content_id, actor, **fields) -> None:
    row = _row(session, workspace_id, content_id)
    if row["state"] not in _EDITABLE:
        raise ContentError(f"cannot edit an item in state {row['state']!r}")
    sets, params = [], {"i": content_id, "ws": workspace_id}
    for key in _FIELDS:
        if key in fields and fields[key] is not None:
            if key == "media":
                sets.append("media = CAST(:media AS jsonb)")
                params["media"] = json.dumps(fields[key])
            else:
                sets.append(f"{key} = :{key}")
                params[key] = fields[key]
    if not sets:
        return
    sets.append("updated_at = now()")
    session.execute(text(
        f"UPDATE content_item SET {', '.join(sets)} "
        f"WHERE id = :i AND workspace_id = :ws"), params)
    _event(session, content_id, "edited", actor,
           fields=[k for k in _FIELDS if k in fields and fields[k] is not None])


def transition(session, workspace_id, content_id, action, actor, *,
               note=None, at=None) -> str:
    row = _row(session, workspace_id, content_id)
    allowed = _TRANSITIONS.get(row["state"], {})
    if action not in allowed:
        raise ContentError(
            f"cannot {action} an item in state {row['state']!r}")
    nxt = allowed[action]

    extra = {}
    if action == "schedule":
        when = at or row["scheduled_for"]
        if when is None:
            raise ContentError("a scheduled_for time is required to schedule")
        extra["scheduled_for"] = when
    if action == "approve":
        extra["approved_by"] = actor
        extra["approved_at"] = _now()
    if action in ("unapprove", "revise"):
        extra["approved_by"] = None
        extra["approved_at"] = None
    if action == "publish":
        extra["published_at"] = at or _now()

    sets = ["state = :state", "updated_at = now()"]
    params = {"i": content_id, "ws": workspace_id, "state": nxt}
    for k, v in extra.items():
        sets.append(f"{k} = :{k}")
        params[k] = v
    session.execute(text(
        f"UPDATE content_item SET {', '.join(sets)} "
        f"WHERE id = :i AND workspace_id = :ws"), params)
    _event(session, content_id, action, actor, note=note,
           from_state=row["state"], to_state=nxt)
    return nxt


def get(session, workspace_id, content_id) -> dict:
    row = _row(session, workspace_id, content_id)
    events = session.execute(text(
        "SELECT actor, kind, note, detail, at FROM content_event "
        "WHERE content_id = :i ORDER BY at, id"), {"i": content_id}).mappings().all()
    return {"item": dict(row), "history": [dict(e) for e in events]}


def calendar(session, workspace_id, start, end, *, state=None) -> dict:
    """Items whose ``scheduled_for`` falls in [start, end], plus any unscheduled
    items still in flight (so nothing planned is invisible)."""
    p = {"ws": workspace_id, "start": start, "end": end}
    clause = ""
    if state:
        clause = " AND state = :state"
        p["state"] = state
    rows = session.execute(text(f"""
        SELECT id, title, channel, state, scheduled_for, assigned_to,
               approved_by, published_at, updated_at
        FROM content_item
        WHERE workspace_id = :ws{clause}
          AND (
            (scheduled_for IS NOT NULL AND scheduled_for >= :start
                                       AND scheduled_for <= :end)
            OR (scheduled_for IS NULL AND state NOT IN ('published'))
          )
        ORDER BY scheduled_for NULLS LAST, updated_at DESC
    """), p).mappings().all()
    return {"window": {"start": start.isoformat(), "end": end.isoformat()},
            "items": [dict(r) for r in rows]}


def delete(session, workspace_id, content_id, actor) -> None:
    row = _row(session, workspace_id, content_id)
    if row["state"] not in ("draft", "rejected"):
        raise ContentError("only a draft or rejected item can be deleted")
    session.execute(text(
        "DELETE FROM content_item WHERE id = :i AND workspace_id = :ws"),
        {"i": content_id, "ws": workspace_id})
