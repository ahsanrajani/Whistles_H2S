"""Agent presence for the supervisor roster (build plan §5 / P3.5).

A short-lived Redis key per (workspace, agent). The agent console beats it every
~30s; the roster reads TTL to bucket agents as online / idle / offline. Uses
the one shared Redis client (``websession``); degrades to "unknown" if Redis is
down rather than failing the request.
"""
import time

import websession
from core import realtime

_PREFIX = "guru:presence:"
_TTL = 90          # seconds a heartbeat is valid
_IDLE_AFTER = 45   # seconds without a beat before "idle"


def _client():
    try:
        return websession.store()._client
    except Exception:
        return None


def heartbeat(workspace_id, user_id, *, status="online") -> None:
    c = _client()
    if c is not None:
        try:
            c.set(f"{_PREFIX}{workspace_id}:{user_id}",
                  f"{status}:{int(time.time())}", ex=_TTL)
        except Exception:
            pass
    # F0.4: nudge every open supervisor roster / console in this workspace.
    try:
        realtime.publish(f"presence:{workspace_id}",
                         {"user_id": user_id, "status": status,
                          "at": int(time.time())})
    except Exception:
        pass


def _read(c, workspace_id, user_id):
    try:
        raw = c.get(f"{_PREFIX}{workspace_id}:{user_id}")
    except Exception:
        return None
    if not raw:
        return None
    raw = raw.decode() if isinstance(raw, bytes) else raw
    status, _, ts = raw.partition(":")
    age = time.time() - int(ts or 0)
    if age > _IDLE_AFTER:
        return {"presence": "idle", "seconds_ago": int(age)}
    return {"presence": status or "online", "seconds_ago": int(age)}


def roster(workspace_id, user_ids):
    """``{user_id: {"presence": online|idle|offline|unknown, "seconds_ago": n}}``."""
    c = _client()
    out = {}
    for uid in user_ids:
        if c is None:
            out[uid] = {"presence": "unknown"}
            continue
        got = _read(c, workspace_id, uid)
        out[uid] = got or {"presence": "offline"}
    return out
