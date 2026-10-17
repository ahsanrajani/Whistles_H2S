"""Idle-session timeout, shared by the Flask ``protect_portal`` guard and
FastAPI's ``guard()`` -- both read/write the same Redis-backed session (see
``store.py``'s docstring), so the check has to live once, here, not be
reimplemented per framework.

Hamza, 2026-09-11: "auth needs to be improved (logout after 20 mins of
inactivity)". The store's own TTL (``DEFAULT_TTL`` in store.py, 7 days) only
resets on a session *write* -- a chatty read-only session could otherwise
outlive it indefinitely. This is a second, much shorter clock, ticked on
every authenticated request regardless of whether it writes anything, and
keyed off the session's own ``last_seen`` field rather than the store's TTL.
"""
import time

IDLE_TIMEOUT_SECONDS = 20 * 60
# last_seen only needs to be accurate to within a minute for a 20-minute
# timeout to hold -- throttling the write this way turns "one Redis write
# per authenticated request" into "one every ~60s of actual traffic".
_TOUCH_THROTTLE_SECONDS = 60


def expired(session_data: dict) -> bool:
    """True if this session has gone quiet for longer than the idle timeout.
    A session with no ``last_seen`` yet (freshly logged in, or one that
    predates this feature) is never expired by this alone -- touch() stamps
    it on the very next call."""
    last_seen = session_data.get("last_seen")
    return last_seen is not None and (time.time() - last_seen) > IDLE_TIMEOUT_SECONDS


def touch(session_data: dict) -> bool:
    """Bump last_seen if the throttle window has passed. Mutates
    session_data in place and returns whether it changed (so the caller
    knows a write-back is actually due)."""
    now = time.time()
    last_seen = session_data.get("last_seen")
    if last_seen is None or now - last_seen > _TOUCH_THROTTLE_SECONDS:
        session_data["last_seen"] = now
        return True
    return False
