"""The stable ``jobs.runner`` interface (build plan §1).

Four entry points — ``enqueue``, ``schedule``, ``sleep_until``, ``signal`` —
that call sites use so the queue backend (Postgres today, maybe Temporal later)
can be swapped without touching them. ``enqueue`` (P1.7) and ``schedule``
(P1.8) are implemented; the timer primitives arrive in Phase 3.
"""
from datetime import datetime, timezone

from . import queue as _queue


def enqueue(session, kind, payload=None, *, max_attempts=5, delay_seconds=0,
            tenant_id=None):
    """Queue ``kind`` for a worker to run. Returns the job id. Caller commits."""
    return _queue.enqueue(session, kind, payload, max_attempts=max_attempts,
                          delay_seconds=delay_seconds, tenant_id=tenant_id)


def schedule(session, name, cron_expr, kind, payload=None, *, tenant_id=None):
    """Register a recurring schedule: the scheduler (``jobs/scheduler.py``)
    enqueues ``kind`` whenever ``cron_expr`` is next due. Idempotent on
    ``name`` — re-registering updates the cron / payload in place. Returns the
    ``scheduled_task`` id. Caller commits."""
    from db import repositories as repo

    from . import cron as _cron

    first = _cron.parse(cron_expr).next_after(datetime.now(timezone.utc))
    return repo.scheduled_task.register(
        session, name=name, kind=kind, cron=cron_expr, payload=payload,
        tenant_id=tenant_id, next_run=first)


def schedule_once(session, name, at, kind, payload=None, *, tenant_id=None):
    """Register a one-shot task that fires at ``at`` and then disables itself
    (P3.3 SLA timers). ``at`` is a timezone-aware datetime. Caller commits."""
    from db import repositories as repo

    return repo.scheduled_task.register(
        session, name=name, kind=kind, cron="* * * * *", payload=payload,
        tenant_id=tenant_id, next_run=at, once=True)


def sleep_until(*args, **kwargs):  # pragma: no cover - Phase 3
    raise NotImplementedError("durable timers land with care SLA work (Phase 3)")


def signal(*args, **kwargs):  # pragma: no cover - Phase 3
    raise NotImplementedError("signals land with care SLA work (Phase 3)")
