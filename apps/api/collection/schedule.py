"""Per-source collection scheduling (build plan §4 / P2.7).

One ``scheduled_task`` per workspace (``collection-tick:<ws>``, every 10 min)
enqueues a ``collection_tick`` job; its handler asks :func:`due_sources` which
source IDs are ready and enqueues a source-scoped ``collection`` run.

Cadence comes from ``core/sources.py`` (P2.2). Bright Data comment sources
decay: hourly while the newest owned post is < 24h old, once a day while it is
24h–7d old, and never once every post is older than 7 days — this is what keeps
the per-record Bright Data spend bounded.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from core import sources
from db.repositories import scheduled_task, source_state

_TICK_CRON = "*/10 * * * *"
_DECAY_SOURCES = {
    "brightdata_facebook_comments": "facebook",
    "brightdata_instagram_comments": "instagram",
}


def ensure_workspace_tick(session, workspace_id) -> None:
    """Idempotently register the per-workspace collection tick."""
    scheduled_task.register(
        session, name=f"collection-tick:{workspace_id}", kind="collection_tick",
        cron=_TICK_CRON, payload={"ws": workspace_id}, tenant_id=workspace_id)


def _parse(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _newest_post(session, workspace_id, surface):
    # raw_json is TEXT, so no JSON path filter — the newest activity on the
    # surface (post or comment) is a fine proxy for "there is a fresh thread".
    row = session.execute(text(
        "SELECT max(published_at) FROM item "
        "WHERE workspace_id = :ws AND surface = :s AND published_at IS NOT NULL"
    ), {"ws": workspace_id, "s": surface}).scalar()
    return _parse(row)


def _last_run_at(states, source):
    row = states.get(source)
    return row["last_attempt_at"] if row else None


def due_sources(session, workspace_id, *, now=None) -> list[str]:
    """The collector source IDs ready to run for this workspace right now."""
    now = now or datetime.now(timezone.utc)
    states = {r["source"]: dict(r)
              for r in source_state.all_for_workspace(session, workspace_id)}
    due = []
    for sid, meta in sources.SOURCES.items():
        cadence = int(meta.get("cadence", 0))
        if cadence == 0:
            continue
        state = states.get(sid)
        if state and not state.get("enabled", True):     # per-workspace opt-out (0027)
            continue
        last = _last_run_at(states, sid)

        if sid in _DECAY_SOURCES:
            newest = _newest_post(session, workspace_id, _DECAY_SOURCES[sid])
            if newest is None:
                continue
            age = now - newest
            if age <= timedelta(hours=24):
                interval = timedelta(seconds=cadence)          # hourly tier
            elif age <= timedelta(days=7):
                interval = timedelta(days=1)                   # daily tier
            else:
                continue                                       # decayed off
        else:
            interval = timedelta(seconds=cadence)

        if last is None or (now - last) >= interval:
            due.append(sid)
    return due
