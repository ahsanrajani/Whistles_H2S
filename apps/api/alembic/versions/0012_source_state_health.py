"""source_state — source-health columns

Revision ID: 0012_source_state_health
Revises: 0011_source_state
Create Date: 2026-09-04

P2.3. ``items_last_run`` and ``last_run_id`` on ``source_state`` so the admin
source-health surface and the silence alert can show what each source produced
on its most recent run.

Idempotent (``ADD COLUMN IF NOT EXISTS``).
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0012_source_state_health"
down_revision: Union[str, None] = "0011_source_state"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE source_state ADD COLUMN IF NOT EXISTS "
               "items_last_run INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE source_state ADD COLUMN IF NOT EXISTS last_run_id TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE source_state DROP COLUMN IF EXISTS last_run_id")
    op.execute("ALTER TABLE source_state DROP COLUMN IF EXISTS items_last_run")
