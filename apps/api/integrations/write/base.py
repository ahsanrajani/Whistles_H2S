"""The write-integration interface (build plan §5 / P3.1, live rollout §D).

One ``WriteClient`` per platform, one small verb set — ``reply_public``,
``reply_dm``, ``publish``, ``schedule``, ``block``, ``unblock``,
``delete_reply``. Every call is recorded in ``outbound_action`` with its
request, the platform response, and a state:

    sent      the platform accepted it (``external_id`` is the created object)
    dry_run   the request was built and logged but **not sent** (the default)
    failed    the call errored
    rejected  the platform rejected an *already-submitted* write (Google review
              replies can be) — surfaces as a rework in
              ``repo.outbound.pending_rework``

Sending is off by default. ``_send`` resolves, in order:

    transport=  a callable            -> tests
    no creds                          -> mock mode (deterministic fake ids)
    GURU_WRITE_LIVE not truthy        -> dry-run: build + log the request, don't send
    GURU_WRITE_LIVE = 1|true|yes|on   -> real HTTP via the platform's ``_live``

``GURU_WRITE_LIVE`` is read from the per-workspace key dict first, then the
process env, so it can be switched on for one workspace at a time. A caller
may also force it per client with ``live=True`` / ``live=False``.
"""
import logging
import os
import uuid
from dataclasses import dataclass

from db import repositories as repo

ACTIONS = ("reply_public", "reply_dm", "publish", "schedule",
           "block", "unblock", "delete_reply")

_LIVE_TRUEISH = {"1", "true", "yes", "on"}

log = logging.getLogger("guru.write")


def live_enabled(explicit, keys) -> bool:
    """Whether real platform writes are on. ``explicit`` (a bool or None) wins;
    then ``GURU_WRITE_LIVE`` from the key dict, then the process env; default off."""
    if explicit is not None:
        return bool(explicit)
    for source in (keys.get("GURU_WRITE_LIVE"), os.environ.get("GURU_WRITE_LIVE")):
        if source is not None and str(source).strip():
            return str(source).strip().lower() in _LIVE_TRUEISH
    return False


class WriteError(Exception):
    """The write could not be sent."""


class WriteRejected(WriteError):
    """The platform rejected a write it had already accepted."""


@dataclass
class WriteResult:
    action_id: int
    state: str
    external_id: str | None = None
    response: dict | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        """A send that reached the platform. A dry run is deliberately not ``ok``."""
        return self.state == "sent"


class WriteClient:
    PLATFORM: str = "base"
    CRED_KEYS: tuple[str, ...] = ()
    SUPPORTED: tuple[str, ...] = ACTIONS

    def __init__(self, keys: dict, *, transport=None, live=None):
        self.k = dict(keys or {})
        self._transport = transport
        self._mock = not self._cred_ok()
        self._live_writes = live_enabled(live, self.k)

    def _cred_ok(self) -> bool:
        """Override for a platform with more than one way to be credentialed
        (e.g. a static token OR an OAuth refresh triple)."""
        return all(self.k.get(key) for key in self.CRED_KEYS)

    def is_mock(self) -> bool:
        return self._mock

    def is_live(self) -> bool:
        """Real writes on (creds present, not mock, GURU_WRITE_LIVE truthy)."""
        return not self._mock and self._live_writes and self._transport is None

    def supports(self, action: str) -> bool:
        return action in self.SUPPORTED

    # --- verbs ----------------------------------------------------------
    def reply_public(self, session, ws, *, target_ref, text, actor=None, **extra):
        return self._do(session, ws, "reply_public", target_ref, {"text": text, **extra}, actor)

    def reply_dm(self, session, ws, *, target_ref, text, actor=None, **extra):
        return self._do(session, ws, "reply_dm", target_ref, {"text": text, **extra}, actor)

    def publish(self, session, ws, *, text, actor=None, **extra):
        return self._do(session, ws, "publish", None, {"text": text, **extra}, actor)

    def schedule(self, session, ws, *, text, at, actor=None, **extra):
        return self._do(session, ws, "schedule", None, {"text": text, "at": at, **extra}, actor)

    def block(self, session, ws, *, target_ref, actor=None, **extra):
        return self._do(session, ws, "block", target_ref, dict(extra), actor)

    def unblock(self, session, ws, *, target_ref, actor=None, **extra):
        return self._do(session, ws, "unblock", target_ref, dict(extra), actor)

    def delete_reply(self, session, ws, *, target_ref, actor=None, **extra):
        return self._do(session, ws, "delete_reply", target_ref, dict(extra), actor)

    # --- engine -------------------------------------------------------
    def _do(self, session, ws, action, target_ref, request, actor) -> WriteResult:
        if action not in self.SUPPORTED:
            raise WriteError(f"{self.PLATFORM} does not support {action}")
        aid = repo.outbound.record(
            session, workspace_id=ws, platform=self.PLATFORM, action=action,
            target_ref=target_ref, request=request, actor=actor)
        return self._attempt(session, aid, action, target_ref, request)

    def _attempt(self, session, action_id, action, target_ref, request) -> WriteResult:
        """Run one send and fold the outcome into ``outbound_action`` + a result.
        Shared by :meth:`_do` and :meth:`deliver`."""
        try:
            out = self._send(action, target_ref, request)
        except WriteRejected as exc:
            repo.outbound.set_state(session, action_id, "rejected", error=str(exc)[:2000])
            return WriteResult(action_id, "rejected", error=str(exc))
        except Exception as exc:                                # noqa: BLE001
            repo.outbound.set_state(session, action_id, "failed", error=str(exc)[:2000])
            return WriteResult(action_id, "failed", error=str(exc))
        state = "dry_run" if (out.get("response") or {}).get("dry_run") else "sent"
        repo.outbound.set_state(session, action_id, state,
                                response=out.get("response"),
                                external_id=out.get("external_id"))
        log.log(logging.INFO if state == "sent" else logging.WARNING,
                "write.%s platform=%s action=%s action_id=%s external_id=%s",
                state, self.PLATFORM, action, action_id, out.get("external_id"))
        return WriteResult(action_id, state, external_id=out.get("external_id"),
                           response=out.get("response"))

    # --- supervisor intervention (P3.5) ------------------------------
    def create_pending(self, session, ws, *, action, target_ref, request, actor=None) -> int:
        """Record the action as ``pending`` without sending it — a supervisor
        reviews (and may edit) it before :meth:`deliver`."""
        if action not in self.SUPPORTED:
            raise WriteError(f"{self.PLATFORM} does not support {action}")
        return repo.outbound.record(
            session, workspace_id=ws, platform=self.PLATFORM, action=action,
            target_ref=target_ref, request=request, actor=actor, state="pending")

    def deliver(self, session, action_id) -> WriteResult:
        """Send a pending action, using whatever ``request`` it now holds (a
        supervisor may have edited it)."""
        row = repo.outbound.get(session, action_id)
        if row is None or row["state"] != "pending":
            raise WriteError(f"outbound_action {action_id} is not pending")
        return self._attempt(session, action_id, row["action"], row["target_ref"],
                             row["request"])

    # --- transport --------------------------------------------------
    def _send(self, action, target_ref, request) -> dict:
        if self._transport is not None:
            return self._transport(action, target_ref, request)
        if self._mock:
            return {"external_id": f"mock:{self.PLATFORM}:{action}:{uuid.uuid4().hex[:8]}",
                    "response": {"mock": True, "action": action, "sent": request}}
        if not self._live_writes:
            return self._dry_run(action, target_ref, request)
        return self._live(action, target_ref, request)

    def _dry_run(self, action, target_ref, request) -> dict:
        """Build + log the call that would have gone out; send nothing."""
        endpoint = self._endpoint(action, target_ref)
        log.warning("write.dry_run platform=%s action=%s target=%s endpoint=%s",
                    self.PLATFORM, action, target_ref, endpoint)
        return {"external_id": None,
                "response": {"dry_run": True, "platform": self.PLATFORM,
                             "action": action, "target_ref": target_ref,
                             "endpoint": endpoint, "would_send": request}}

    def _endpoint(self, action, target_ref):
        """A human-readable description of the call :meth:`_live` would make.
        Overridden per platform so the dry-run log names a real URL."""
        return None

    def _live(self, action, target_ref, request) -> dict:      # pragma: no cover
        raise WriteError(f"{self.PLATFORM} live transport is not wired in this build")
