"""knowledge base + templates — kb_article, kb_attachment, care_template

Revision ID: 0017_knowledge
Revises: 0016_routing
Create Date: 2026-09-04

P3.6. Article CRUD with full-text search and attachment metadata, and a
role-restricted template library.

Idempotent DDL.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0017_knowledge"
down_revision: Union[str, None] = "0016_routing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS kb_article (
            id           BIGSERIAL PRIMARY KEY,
            workspace_id INTEGER NOT NULL REFERENCES workspace (id) ON DELETE CASCADE,
            title        TEXT NOT NULL,
            body         TEXT NOT NULL DEFAULT '',
            tags         TEXT NOT NULL DEFAULT '',
            created_by   INTEGER REFERENCES "user" (id) ON DELETE SET NULL,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_kb_article_fts ON kb_article
        USING GIN (to_tsvector('english', title || ' ' || body || ' ' || tags))
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS kb_attachment (
            id         BIGSERIAL PRIMARY KEY,
            article_id BIGINT NOT NULL REFERENCES kb_article (id) ON DELETE CASCADE,
            filename   TEXT NOT NULL,
            url        TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_kb_attachment_article "
               "ON kb_attachment (article_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS care_template (
            id           BIGSERIAL PRIMARY KEY,
            workspace_id INTEGER NOT NULL REFERENCES workspace (id) ON DELETE CASCADE,
            name         TEXT NOT NULL,
            category     TEXT NOT NULL DEFAULT 'general',
            body         TEXT NOT NULL,
            created_by   INTEGER REFERENCES "user" (id) ON DELETE SET NULL,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_care_template_ws "
               "ON care_template (workspace_id, category)")


def downgrade() -> None:
    op.drop_table("care_template")
    op.drop_table("kb_attachment")
    op.drop_table("kb_article")
