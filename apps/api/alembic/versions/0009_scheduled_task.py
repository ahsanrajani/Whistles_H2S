"""scheduled_task — recurring schedules for the scheduler

Revision ID: 0009_scheduled_task
Revises: 0008_job
Create Date: 2026-09-03

P1.8. One row per recurring job: a cron expression, the ``kind`` to enqueue,
its payload, an optional tenant, and ``last_run`` / ``next_run`` bookkeeping.
``jobs/scheduler.py`` ticks once a minute under a Postgres advisory lock,
enqueues the due rows onto ``job`` (P1.7), and advances ``next_run``.

Idempotent (``CREATE TABLE / INDEX IF NOT EXISTS``) — the ``0001`` baseline
already builds it from ``Base.metadata``.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0009_scheduled_task"
down_revision: Union[str, None] = "0008_job"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_task (
            id          SERIAL PRIMARY KEY,
            name        TEXT        NOT NULL,
            kind        TEXT        NOT NULL,
            payload     JSONB       NOT NULL DEFAULT '{}',
            cron        TEXT        NOT NULL,
            tenant_id   INTEGER,
            enabled     INTEGER     NOT NULL DEFAULT 1,
            last_run    TIMESTAMPTZ,
            next_run    TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_scheduled_task_name "
               "ON scheduled_task (name)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_scheduled_task_due "
               "ON scheduled_task (next_run) WHERE enabled = 1")


def downgrade() -> None:
    op.drop_table("scheduled_task")
