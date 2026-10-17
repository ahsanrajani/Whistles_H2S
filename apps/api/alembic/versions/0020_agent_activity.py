"""care agent activity log — agent_activity

Revision ID: 0020_agent_activity
Revises: 0019_metric_fact
Create Date: 2026-09-04

P4.3. An append-only stream of agent shift events (login / logout / ready /
not_ready / idle / active) so the care reports can reconstruct session, ready,
not-ready and idle time. Handling time comes from ``case`` timestamps, not from
here.

Idempotent DDL; reversible.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0020_agent_activity"
down_revision: Union[str, None] = "0019_metric_fact"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS agent_activity (
            id           BIGSERIAL PRIMARY KEY,
            workspace_id INTEGER NOT NULL REFERENCES workspace (id) ON DELETE CASCADE,
            user_id      INTEGER NOT NULL REFERENCES "user" (id) ON DELETE CASCADE,
            kind         TEXT NOT NULL,
            at           TIMESTAMPTZ NOT NULL DEFAULT now(),
            meta         JSONB NOT NULL DEFAULT '{}'::jsonb
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_agent_activity_ws_user_at "
               "ON agent_activity (workspace_id, user_id, at)")


def downgrade() -> None:
    op.drop_table("agent_activity")
