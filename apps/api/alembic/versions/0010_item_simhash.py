"""item.simhash — near-duplicate detection column

Revision ID: 0010_item_simhash
Revises: 0009_scheduled_task
Create Date: 2026-09-04

P2.1. A 63-bit Charikar SimHash (fits a signed BIGINT) of the normalised item
text, so ``collection/dedupe.py`` can fold a story re-reported near-verbatim by
a *different* source — the job the old exact-URL pass did wrongly, folding
anything that merely shared a URL.

Idempotent (``ADD COLUMN IF NOT EXISTS``) — the ``0001`` baseline builds the
column from ``Base.metadata`` on a fresh DB.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0010_item_simhash"
down_revision: Union[str, None] = "0009_scheduled_task"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE item ADD COLUMN IF NOT EXISTS simhash BIGINT")
    op.execute("CREATE INDEX IF NOT EXISTS ix_item_simhash "
               "ON item (workspace_id, simhash) "
               "WHERE simhash IS NOT NULL AND simhash <> 0")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_item_simhash")
    op.execute("ALTER TABLE item DROP COLUMN IF EXISTS simhash")
