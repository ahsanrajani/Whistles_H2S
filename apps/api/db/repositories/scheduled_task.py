"""``scheduled_task`` table access for the scheduler (``jobs/scheduler.py``).

Every function takes a ``Session`` and leaves the commit to the caller. ``due``
takes ``FOR UPDATE SKIP LOCKED`` rows so that even without the scheduler's
advisory lock two passes could not enqueue the same task twice.
"""
import json

from sqlalchemy import text


def register(session, *, name, kind, cron, payload=None, tenant_id=None,
             next_run=None, once=False):
    """Create the schedule, or update it in place if ``name`` already exists.
    ``once=True`` marks a one-shot (P3.3 SLA timers) — the scheduler disables it
    after it fires. Returns its id. Caller commits."""
    row = session.execute(text("""
        INSERT INTO scheduled_task (name, kind, cron, payload, tenant_id, next_run, once)
        VALUES (:name, :kind, :cron, CAST(:payload AS jsonb), :tenant_id,
                COALESCE(:next_run, now()), :once)
        ON CONFLICT (name) DO UPDATE SET
            kind       = EXCLUDED.kind,
            cron       = EXCLUDED.cron,
            payload    = EXCLUDED.payload,
            tenant_id  = EXCLUDED.tenant_id,
            next_run   = COALESCE(EXCLUDED.next_run, scheduled_task.next_run),
            once       = EXCLUDED.once,
            enabled    = 1,
            updated_at = now()
        RETURNING id
    """), {"name": name, "kind": kind, "cron": cron,
           "payload": json.dumps(payload or {}), "tenant_id": tenant_id,
           "next_run": next_run, "once": 1 if once else 0}).scalar_one()
    return int(row)


def due(session, now):
    """Enabled rows whose ``next_run`` has passed, locked for this transaction."""
    return session.execute(text("""
        SELECT id, name, kind, payload, cron, tenant_id, once
        FROM scheduled_task
        WHERE enabled = 1 AND next_run <= :now
        ORDER BY next_run
        FOR UPDATE SKIP LOCKED
    """), {"now": now}).mappings().all()


def mark_ran(session, task_id, *, last_run, next_run, disable=False):
    session.execute(text("""
        UPDATE scheduled_task
        SET last_run = :last, next_run = :next,
            enabled = CASE WHEN :disable THEN 0 ELSE enabled END,
            updated_at = now()
        WHERE id = :id
    """), {"id": task_id, "last": last_run, "next": next_run, "disable": disable})


def set_enabled(session, name, enabled):
    session.execute(text(
        "UPDATE scheduled_task SET enabled = :e, updated_at = now() WHERE name = :n"),
        {"e": 1 if enabled else 0, "n": name})


def all_tasks(session):
    """Every schedule, by name — an admin timeline / the P1.9 metrics."""
    return session.execute(text("""
        SELECT id, name, kind, cron, tenant_id, enabled, last_run, next_run
        FROM scheduled_task ORDER BY name
    """)).mappings().all()
