"""ai_suggestion_cache -- reuse a case's reply suggestion instead of
re-asking the model every time the conversation is (re)opened

Revision ID: 0032_ai_suggestion_cache
Revises: 0031_seo_suggestion
Create Date: 2026-09-10

Keyed on (case_id, kind), invalidated by a cheap thread fingerprint (message
count + last message id) -- a new message changes the fingerprint and the
next read regenerates. Idempotent DDL; RLS policy matches 0025/0028/0029/
0031; reversible.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0032_ai_suggestion_cache"
down_revision: Union[str, None] = "0031_seo_suggestion"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TID = "NULLIF(current_setting('app.tenant_id', true), '')::int"


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS ai_suggestion_cache (
            id SERIAL PRIMARY KEY,
            workspace_id INTEGER NOT NULL REFERENCES workspace(id) ON DELETE CASCADE,
            case_id INTEGER NOT NULL REFERENCES "case"(id) ON DELETE CASCADE,
            kind TEXT NOT NULL,
            fingerprint TEXT NOT NULL,
            suggestion TEXT NOT NULL DEFAULT '',
            sources JSONB NOT NULL DEFAULT '[]'::jsonb,
            mock BOOLEAN NOT NULL DEFAULT false,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_ai_suggestion_cache_case_kind "
        "ON ai_suggestion_cache (case_id, kind)")
    op.execute("ALTER TABLE ai_suggestion_cache ENABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON ai_suggestion_cache")
    op.execute(
        f"CREATE POLICY tenant_isolation ON ai_suggestion_cache "
        f"USING (workspace_id = {_TID}) WITH CHECK (workspace_id = {_TID})")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON ai_suggestion_cache")
    op.execute("DROP TABLE IF EXISTS ai_suggestion_cache")
