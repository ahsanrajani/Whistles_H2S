"""job — the Postgres-backed work queue

Revision ID: 0008_job
Revises: 0007_audit_hardening
Create Date: 2026-09-03

P1.7a. A ``job`` table drained by workers that claim rows with
``FOR UPDATE SKIP LOCKED`` (``jobs/queue.py``). Exponential backoff on failure,
``max_attempts`` then the ``dead`` state, and a reclaim window so a job whose
worker died is picked up again.

Idempotent (``CREATE TABLE / INDEX IF NOT EXISTS``) — the ``0001`` baseline
already builds it from ``Base.metadata``.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0008_job"
down_revision: Union[str, None] = "0007_audit_hardening"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS job (
            id           BIGSERIAL PRIMARY KEY,
            kind         TEXT        NOT NULL,
            payload      JSONB       NOT NULL DEFAULT '{}',
            state        TEXT        NOT NULL DEFAULT 'queued',
            attempts     INTEGER     NOT NULL DEFAULT 0,
            max_attempts INTEGER     NOT NULL DEFAULT 5,
            run_after    TIMESTAMPTZ NOT NULL DEFAULT now(),
            locked_by    TEXT,
            locked_at    TIMESTAMPTZ,
            last_error   TEXT,
            result       JSONB,
            tenant_id    INTEGER,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_job_queued ON job (run_after) "
               "WHERE state = 'queued'")
    op.execute("CREATE INDEX IF NOT EXISTS ix_job_running ON job (locked_at) "
               "WHERE state = 'running'")


def downgrade() -> None:
    op.drop_table("job")
