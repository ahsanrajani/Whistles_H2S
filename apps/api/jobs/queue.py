"""The ``job`` table operations. Every function takes a SQLAlchemy ``Session``
and leaves the commit to the caller (so a claim + handler + complete can be
reasoned about as separate transactions).

Claiming is a single ``UPDATE … WHERE id = (SELECT … FOR UPDATE SKIP LOCKED)``
so two workers never take the same row, and a ``running`` row whose worker
died (``locked_at`` older than the reclaim window) is taken again.
"""
from sqlalchemy import text

# backoff = BASE * 2**(attempts-1) seconds, capped
BACKOFF_BASE_SECONDS = 5
BACKOFF_CAP_SECONDS = 3600
RECLAIM_AFTER_SECONDS = 300

_TERMINAL = ("done", "dead")


def enqueue(session, kind, payload=None, *, max_attempts=5, delay_seconds=0,
            tenant_id=None):
    """Insert a queued job. Returns its id."""
    row = session.execute(text("""
        INSERT INTO job (kind, payload, max_attempts, run_after, tenant_id)
        VALUES (:kind, CAST(:payload AS jsonb), :max_attempts,
                now() + make_interval(secs => :delay), :tenant_id)
        RETURNING id
    """), {"kind": kind, "payload": _json(payload or {}),
           "max_attempts": max_attempts, "delay": float(delay_seconds),
           "tenant_id": tenant_id}).scalar_one()
    return int(row)


def claim(session, worker_id, *, kinds=None, reclaim_after_seconds=RECLAIM_AFTER_SECONDS):
    """Take one runnable job for ``worker_id`` (a queued job that is due, or a
    stale ``running`` one). Marks it ``running``, bumps ``attempts``. Returns the
    row (mapping) or ``None``. Caller commits."""
    params = {"w": worker_id, "reclaim": float(reclaim_after_seconds)}
    kind_clause = ""
    if kinds:
        params["kinds"] = list(kinds)
        kind_clause = "AND kind = ANY(:kinds)"
    row = session.execute(text(f"""
        UPDATE job SET
            state = 'running',
            locked_by = :w,
            locked_at = now(),
            attempts = attempts + 1,
            updated_at = now()
        WHERE id = (
            SELECT id FROM job
            WHERE (
                (state = 'queued'  AND run_after <= now())
             OR (state = 'running' AND locked_at < now() - make_interval(secs => :reclaim))
            ) {kind_clause}
            ORDER BY run_after
            FOR UPDATE SKIP LOCKED
            LIMIT 1
        )
        RETURNING *
    """), params).mappings().first()
    return row


def complete(session, job_id, result=None):
    session.execute(text("""
        UPDATE job SET state='done', result=CAST(:result AS jsonb),
               locked_by=NULL, locked_at=NULL, last_error=NULL, updated_at=now()
        WHERE id=:id
    """), {"id": job_id, "result": _json(result) if result is not None else None})


def fail(session, job_id, error, *, base_seconds=BACKOFF_BASE_SECONDS):
    """Record a failure: back off and requeue, or move to ``dead`` once
    ``attempts`` has reached ``max_attempts``."""
    session.execute(text(f"""
        UPDATE job SET
            state = CASE WHEN attempts >= max_attempts THEN 'dead' ELSE 'queued' END,
            run_after = now() + make_interval(secs => LEAST(
                :base * power(2, GREATEST(attempts - 1, 0)), {BACKOFF_CAP_SECONDS})),
            locked_by = NULL,
            locked_at = NULL,
            last_error = :err,
            updated_at = now()
        WHERE id = :id
    """), {"id": job_id, "base": float(base_seconds), "err": str(error)[:4000]})


def get(session, job_id):
    return session.execute(
        text("SELECT * FROM job WHERE id=:id"), {"id": job_id}).mappings().first()


def counts(session):
    """``{state: n}`` — for the observability metrics in P1.9."""
    rows = session.execute(text("SELECT state, count(*) FROM job GROUP BY state")).all()
    return {state: n for state, n in rows}


def _json(value):
    import json
    return json.dumps(value)
