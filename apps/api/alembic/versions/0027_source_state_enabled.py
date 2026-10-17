"""source_state.enabled — per-workspace source opt-out

Revision ID: 0027_source_state_enabled
Revises: 0026_kb_published
Create Date: 2026-09-09

A workspace can switch a collection source off without touching shared
credentials (e.g. Chase Securities runs YouTube / Bluesky / DataForSEO but not
X or Reddit, while Bank Alfalah keeps them). ``enabled`` defaults to true, so
every existing (workspace, source) row and every source with no row yet keeps
collecting exactly as before. ``run_collection`` and ``schedule.due_sources``
skip a source whose row is explicitly ``enabled = false``.

Adds a column with a default — not destructive, no build-plan §0.6 note.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0027_source_state_enabled"
down_revision: Union[str, None] = "0026_kb_published"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE source_state "
        "ADD COLUMN IF NOT EXISTS enabled BOOLEAN NOT NULL DEFAULT true")


def downgrade() -> None:
    op.execute("ALTER TABLE source_state DROP COLUMN IF EXISTS enabled")
