"""scheduled report distribution — report_schedule

Revision ID: 0023_report_schedule
Revises: 0022_survey
Create Date: 2026-09-04

P4.9. A ``report_schedule`` binds a report kind + format + params to a cron and
a recipient list. Registering one creates a ``scheduled_task`` (``report:<id>``,
kind ``report_email``); the worker renders via the P4.8 export engine and mails
it through ``integrations/email``.

Idempotent DDL; reversible.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0023_report_schedule"
down_revision: Union[str, None] = "0022_survey"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS report_schedule (
            id           BIGSERIAL PRIMARY KEY,
            workspace_id INTEGER NOT NULL REFERENCES workspace (id) ON DELETE CASCADE,
            name         TEXT NOT NULL,
            kind         TEXT NOT NULL,
            format       TEXT NOT NULL DEFAULT 'pdf',
            params       JSONB NOT NULL DEFAULT '{}'::jsonb,
            cron         TEXT NOT NULL,
            recipients   JSONB NOT NULL DEFAULT '[]'::jsonb,
            active       BOOLEAN NOT NULL DEFAULT true,
            last_run_at  TIMESTAMPTZ,
            last_status  TEXT,
            created_by   INTEGER REFERENCES "user" (id) ON DELETE SET NULL,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_report_schedule_ws "
               "ON report_schedule (workspace_id, active)")


def downgrade() -> None:
    op.drop_table("report_schedule")
