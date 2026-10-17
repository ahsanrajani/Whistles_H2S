"""``agent_activity`` access (P4.3) — append one shift event, read a window."""
import json

from sqlalchemy import text

KINDS = ("login", "logout", "ready", "not_ready", "idle", "active")


def record(session, *, workspace_id, user_id, kind, at=None, meta=None) -> int:
    if kind not in KINDS:
        raise ValueError(f"unknown agent activity kind: {kind!r}")
    return int(session.execute(text("""
        INSERT INTO agent_activity (workspace_id, user_id, kind, at, meta)
        VALUES (:ws, :uid, :kind, COALESCE(:at, now()), CAST(:meta AS jsonb))
        RETURNING id
    """), {"ws": workspace_id, "uid": user_id, "kind": kind, "at": at,
           "meta": json.dumps(meta or {})}).scalar_one())


def latest(session, workspace_id, user_id):
    """(kind, at, meta) of this user's most recent shift event, or None.
    Powers the header status control's "what am I actually set to right
    now" -- it used to just hardcode a client-side default on every mount,
    showing "Not available" even when the real, persisted state was
    something else (Hamza: "make sure the ... toggle ... works")."""
    row = session.execute(text("""
        SELECT kind, at, meta FROM agent_activity
        WHERE workspace_id = :ws AND user_id = :uid
        ORDER BY at DESC, id DESC LIMIT 1
    """), {"ws": workspace_id, "uid": user_id}).first()
    if not row:
        return None
    kind, at, meta = row
    return kind, at, (json.loads(meta) if isinstance(meta, str) else meta) or {}


def recent(session, workspace_id, user_id, *, limit=15):
    """This user's last `limit` shift events, newest first -- the "all
    times/activity is logged and displayed" half of the status control."""
    rows = session.execute(text("""
        SELECT kind, at, meta FROM agent_activity
        WHERE workspace_id = :ws AND user_id = :uid
        ORDER BY at DESC, id DESC LIMIT :lim
    """), {"ws": workspace_id, "uid": user_id, "lim": limit}).all()
    out = []
    for kind, at, meta in rows:
        meta = (json.loads(meta) if isinstance(meta, str) else meta) or {}
        out.append({"kind": kind, "at": at, "reason": meta.get("reason")})
    return out


def window(session, workspace_id, start, end, *, user_id=None):
    """Ordered (user_id, kind, at) events overlapping [start, end], plus the one
    event immediately before ``start`` per user so an open session is known."""
    p = {"ws": workspace_id, "start": start, "end": end}
    clause = ""
    if user_id is not None:
        clause = " AND user_id = :uid"
        p["uid"] = user_id
    return session.execute(text(f"""
        (SELECT user_id, kind, at FROM agent_activity
         WHERE workspace_id = :ws{clause} AND at >= :start AND at <= :end)
        UNION ALL
        (SELECT DISTINCT ON (user_id) user_id, kind, at FROM agent_activity
         WHERE workspace_id = :ws{clause} AND at < :start
         ORDER BY user_id, at DESC)
        ORDER BY user_id, at
    """), p).mappings().all()
