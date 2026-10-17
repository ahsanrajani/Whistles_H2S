"""content calendar — content_item, content_event

Revision ID: 0021_content_calendar
Revises: 0020_agent_activity
Create Date: 2026-09-04

P4.6. A planned/scheduled post carries a state machine
(draft → in_review → approved → scheduled → published, plus rejected) and an
append-only ``content_event`` trail of every transition. Drag-drop on the
calendar is a ``scheduled_for`` update; publish goes through the P3.1 write
layer.

Idempotent DDL; reversible.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0021_content_calendar"
down_revision: Union[str, None] = "0020_agent_activity"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS content_item (
            id             BIGSERIAL PRIMARY KEY,
            workspace_id   INTEGER NOT NULL REFERENCES workspace (id) ON DELETE CASCADE,
            title          TEXT NOT NULL,
            body           TEXT NOT NULL DEFAULT '',
            channel        TEXT,
            media          JSONB NOT NULL DEFAULT '[]'::jsonb,
            scheduled_for  TIMESTAMPTZ,
            state          TEXT NOT NULL DEFAULT 'draft',
            created_by     INTEGER REFERENCES "user" (id) ON DELETE SET NULL,
            assigned_to    INTEGER REFERENCES "user" (id) ON DELETE SET NULL,
            approved_by    INTEGER REFERENCES "user" (id) ON DELETE SET NULL,
            approved_at    TIMESTAMPTZ,
            published_at   TIMESTAMPTZ,
            outbound_action_id BIGINT REFERENCES outbound_action (id) ON DELETE SET NULL,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_content_item_ws_when "
               "ON content_item (workspace_id, scheduled_for)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_content_item_ws_state "
               "ON content_item (workspace_id, state)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS content_event (
            id         BIGSERIAL PRIMARY KEY,
            content_id BIGINT NOT NULL REFERENCES content_item (id) ON DELETE CASCADE,
            actor      TEXT,
            kind       TEXT NOT NULL,
            note       TEXT,
            detail     JSONB NOT NULL DEFAULT '{}'::jsonb,
            at         TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_content_event_item "
               "ON content_event (content_id, at)")


def downgrade() -> None:
    op.drop_table("content_event")
    op.drop_table("content_item")
