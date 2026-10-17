"""kb_article.published — publish / unpublish a knowledge base article

Revision ID: 0026_kb_published
Revises: 0025_project
Create Date: 2026-09-04

Frontend F3.2. An article can be drafted then published; the composer's KB
attach and the browse list default to published only.

Idempotent (ADD COLUMN IF NOT EXISTS); reversible.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0026_kb_published"
down_revision: Union[str, None] = "0025_project"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE kb_article ADD COLUMN IF NOT EXISTS "
               "published BOOLEAN NOT NULL DEFAULT true")


def downgrade() -> None:
    op.execute("ALTER TABLE kb_article DROP COLUMN IF EXISTS published")
