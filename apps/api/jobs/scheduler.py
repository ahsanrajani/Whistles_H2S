"""The scheduler (build plan §1, P1.8).

Once a minute it enqueues a job for every ``scheduled_task`` row that is due,
then advances that row's ``next_run`` off its cron expression. It **only
enqueues** — handler code runs in ``jobs/worker.py`` like any other job.

Every tick opens a transaction and takes a Postgres *transaction-level*
advisory lock (``pg_try_advisory_xact_lock``). Run the scheduler in as many
processes as you like: only the one that wins the lock does that tick, the
others no-op. The lock releases when the tick's transaction ends, so a
scheduler that dies mid-tick never wedges the rest.
"""
from datetime import datetime, timezone

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB

from db import repositories as repo
from db.session import OperatorSession

from . import cron, runner

# Arbitrary fixed key: b"guru" as a big-endian int. Every scheduler in every
# process contends on this one number.
LOCK_KEY = 0x67757275
TICK_SECONDS = 60


def _pending(session, kind, payload, tenant_id) -> bool:
    """True when an identical job (kind, tenant, payload) is still queued or
    running -- a fast cron (``dm_sync`` is every minute) must not stack a new
    copy behind one that hasn't finished, or a slow/failing handler floods the
    single worker and starves every other job."""
    return session.execute(text("""
        SELECT 1 FROM job
         WHERE kind = :k AND state IN ('queued', 'running')
           AND tenant_id IS NOT DISTINCT FROM :t AND payload = :p
         LIMIT 1
    """).bindparams(bindparam("p", type_=JSONB)),
        {"k": kind, "t": tenant_id, "p": payload}).first() is not None


def tick(session, *, now=None):
    """Run one scheduler pass inside ``session``'s transaction. Returns a list
    of ``(task_name, job_id)`` for what was enqueued (``job_id`` is ``None``
    when an identical job was still pending, so none was added), or ``None`` when another
    process holds the advisory lock (this tick is a no-op). Caller commits."""
    got = session.execute(
        text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": LOCK_KEY}).scalar_one()
    if not got:
        return None
    now = now or datetime.now(timezone.utc)
    enqueued = []
    for task in repo.scheduled_task.due(session, now):
        payload = task["payload"] or {}
        if _pending(session, task["kind"], payload, task["tenant_id"]):
            job_id = None                  # still advance next_run below
        else:
            job_id = runner.enqueue(session, task["kind"], payload,
                                    tenant_id=task["tenant_id"])
        if task.get("once"):
            repo.scheduled_task.mark_ran(session, task["id"], last_run=now,
                                         next_run=now, disable=True)
        else:
            repo.scheduled_task.mark_ran(session, task["id"], last_run=now,
                                         next_run=cron.next_after(task["cron"], now))
        enqueued.append((task["name"], job_id))
    return enqueued


def run_pending(*, session_factory=OperatorSession, now=None):
    """Open a transaction, :func:`tick`, commit. Returns what ``tick`` returned."""
    session = session_factory()
    try:
        result = tick(session, now=now)
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def loop(stop_event, *, interval_seconds=TICK_SECONDS, session_factory=OperatorSession):
    """Tick every ``interval_seconds`` until ``stop_event`` is set."""
    while not stop_event.is_set():
        try:
            run_pending(session_factory=session_factory)
        except Exception:                                  # keep ticking
            pass
        stop_event.wait(interval_seconds)


if __name__ == "__main__":                                 # python -m jobs.scheduler
    import threading

    _stop = threading.Event()
    try:
        loop(_stop)
    except KeyboardInterrupt:
        _stop.set()
