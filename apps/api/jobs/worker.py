"""The polling worker: claim one job, run its handler, mark it done or failed.

Handlers register with ``@handler("kind")`` and take the job's ``payload``
dict; whatever they return is stored on ``job.result``. An exception is caught
and routed through ``queue.fail`` (backoff / dead-letter). Claim, run and the
result write are three separate transactions so a crash between them leaves the
row reclaimable, not lost.
"""
import os
import socket
import threading
import time

from db.session import OperatorSession
from obs.metrics import record_job

from . import queue

_HANDLERS = {}


def handler(kind):
    def register(fn):
        _HANDLERS[kind] = fn
        return fn
    return register


def worker_id():
    return f"{socket.gethostname()}:{os.getpid()}:{threading.get_ident()}"


def run_one(who=None, *, kinds=None, session_factory=OperatorSession, **claim_kw):
    """Claim and run a single job. Returns True if one ran, False if the queue
    was empty."""
    who = who or worker_id()
    session = session_factory()
    try:
        job = queue.claim(session, who, kinds=kinds, **claim_kw)
        session.commit()
    finally:
        session.close()
    if job is None:
        return False

    job_id, kind, payload = job["id"], job["kind"], job["payload"]
    fn = _HANDLERS.get(kind)
    session = session_factory()
    outcome = "failed"
    try:
        if fn is None:
            queue.fail(session, job_id, f"no handler for kind {kind!r}")
        else:
            try:
                result = fn(payload or {})
            except Exception as exc:                       # noqa: BLE001 - queue decides
                queue.fail(session, job_id, repr(exc))
            else:
                queue.complete(session, job_id, result)
                outcome = "done"
        session.commit()
    finally:
        session.close()
    record_job(kind, outcome)
    return True


def loop(stop_event, *, kinds=None, idle_seconds=1.0, session_factory=OperatorSession):
    """Drain the queue until ``stop_event`` is set. One worker per thread."""
    who = worker_id()
    while not stop_event.is_set():
        try:
            ran = run_one(who, kinds=kinds, session_factory=session_factory)
        except Exception:                                  # keep the loop alive
            ran = False
            time.sleep(idle_seconds)
        if not ran:
            stop_event.wait(idle_seconds)
