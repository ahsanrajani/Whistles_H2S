"""routing — care_agent, routing_policy; scheduled_task.once for one-shot SLA timers

Revision ID: 0016_routing
Revises: 0015_case_engine
Create Date: 2026-09-04

P3.3. Round-robin assignment with per-agent capacity caps, auto-issue on
closure, reassignment with a logged reason, and SLA timers scheduled as
one-shot ``scheduled_task`` rows (``once = true`` — the scheduler disables the
row after it fires instead of advancing ``next_run``).

Idempotent DDL.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0016_routing"
down_revision: Union[str, None] = "0015_case_engine"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS care_agent (
            workspace_id INTEGER NOT NULL REFERENCES workspace (id) ON DELETE CASCADE,
            user_id      INTEGER NOT NULL REFERENCES "user" (id) ON DELETE CASCADE,
            capacity     INTEGER NOT NULL DEFAULT 5,
            available    INTEGER NOT NULL DEFAULT 1,
            last_seen    TIMESTAMPTZ,
            last_assigned_at TIMESTAMPTZ,
            CONSTRAINT pk_care_agent PRIMARY KEY (workspace_id, user_id)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS routing_policy (
            workspace_id       INTEGER NOT NULL REFERENCES workspace (id) ON DELETE CASCADE,
            first_response_sla INTEGER NOT NULL DEFAULT 900,     -- 15 min
            resolution_sla     INTEGER NOT NULL DEFAULT 86400,   -- 24 h
            escalation_after   INTEGER NOT NULL DEFAULT 3600,    -- 1 h
            default_capacity   INTEGER NOT NULL DEFAULT 5,
            updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT pk_routing_policy PRIMARY KEY (workspace_id)
        )
    """)

    op.execute("ALTER TABLE scheduled_task ADD COLUMN IF NOT EXISTS once INTEGER NOT NULL DEFAULT 0")


def downgrade() -> None:
    op.execute("ALTER TABLE scheduled_task DROP COLUMN IF EXISTS once")
    op.drop_table("routing_policy")
    op.drop_table("care_agent")
