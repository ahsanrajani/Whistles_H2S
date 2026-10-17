"""outbound_action — every write to an external platform

Revision ID: 0014_outbound_action
Revises: 0013_item_author
Create Date: 2026-09-04

P3.1. One row per call the write-integration layer makes to a platform: the
request payload, the platform's response, an external id for anything it
created, and a state. A Google review reply can be rejected *after* submission,
so ``rejected`` is a real terminal state that surfaces a rework.

Idempotent (``CREATE TABLE / INDEX IF NOT EXISTS``).
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0014_outbound_action"
down_revision: Union[str, None] = "0013_item_author"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS outbound_action (
            id           BIGSERIAL PRIMARY KEY,
            workspace_id INTEGER NOT NULL REFERENCES workspace (id) ON DELETE CASCADE,
            platform     TEXT    NOT NULL,   -- meta | x | linkedin | google_reviews | youtube
            action       TEXT    NOT NULL,   -- reply_public | reply_dm | publish | schedule
                                             -- | block | unblock | delete_reply
            target_ref   TEXT,              -- the thing acted on (post/comment/thread id)
            request      JSONB   NOT NULL DEFAULT '{}',
            response     JSONB,
            external_id  TEXT,              -- platform id of anything created
            state        TEXT    NOT NULL DEFAULT 'pending',
                                             -- pending|sent|failed|rejected|reworked
            error        TEXT,
            actor        TEXT,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_outbound_action_ws "
               "ON outbound_action (workspace_id, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_outbound_action_rework "
               "ON outbound_action (workspace_id) WHERE state = 'rejected'")


def downgrade() -> None:
    op.drop_table("outbound_action")
