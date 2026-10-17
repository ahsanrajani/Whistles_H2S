"""seo_suggestion -- LLM-generated SEO recommendations (Vantage's SEO tab)

Revision ID: 0031_seo_suggestion
Revises: 0030_case_message_permalink
Create Date: 2026-09-10

Human-triggered only (real, costed LLM calls -- never scheduled), grounded in
the real crawl/CWV/keyword/backlink/search-visibility facts already on file.
The raw model response is kept alongside the parsed {priority, text} list.

Idempotent DDL; RLS policy matches 0025/0028/0029; reversible.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0031_seo_suggestion"
down_revision: Union[str, None] = "0030_case_message_permalink"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TID = "NULLIF(current_setting('app.tenant_id', true), '')::int"


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS seo_suggestion (
            id SERIAL PRIMARY KEY,
            workspace_id INTEGER NOT NULL REFERENCES workspace(id) ON DELETE CASCADE,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            prompt TEXT NOT NULL,
            raw_text TEXT NOT NULL DEFAULT '',
            suggestions JSONB NOT NULL DEFAULT '[]'::jsonb,
            error TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_seo_suggestion_ws "
        "ON seo_suggestion (workspace_id, created_at)")
    op.execute("ALTER TABLE seo_suggestion ENABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON seo_suggestion")
    op.execute(
        f"CREATE POLICY tenant_isolation ON seo_suggestion "
        f"USING (workspace_id = {_TID}) WITH CHECK (workspace_id = {_TID})")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON seo_suggestion")
    op.execute("DROP TABLE IF EXISTS seo_suggestion")
