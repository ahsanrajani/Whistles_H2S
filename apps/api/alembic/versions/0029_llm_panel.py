"""llm_prompt + llm_panel_response -- Vantage AI-visibility panel

Revision ID: 0029_llm_panel
Revises: 0028_feature_flags
Create Date: 2026-09-10

Phase 5 (Vantage) first surface: a fixed prompt set per workspace, asked of a
roster of LLMs, with the raw answer kept as evidence (§0.4 -- no proportion
without something to point at) and which brands (focus + competitors) the
answer text mentions, via the same core.entity.classify() the listening
pipeline uses.

Idempotent DDL; RLS policy matches 0025/0028; reversible.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0029_llm_panel"
down_revision: Union[str, None] = "0028_feature_flags"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TID = "NULLIF(current_setting('app.tenant_id', true), '')::int"


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS llm_prompt (
            id           BIGSERIAL PRIMARY KEY,
            workspace_id INTEGER NOT NULL REFERENCES workspace (id) ON DELETE CASCADE,
            prompt_text  TEXT    NOT NULL,
            active       BOOLEAN NOT NULL DEFAULT true,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_llm_prompt_ws ON llm_prompt (workspace_id)")
    op.execute("ALTER TABLE llm_prompt ENABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON llm_prompt")
    op.execute(
        f"CREATE POLICY tenant_isolation ON llm_prompt "
        f"USING (workspace_id = {_TID}) WITH CHECK (workspace_id = {_TID})")

    op.execute("""
        CREATE TABLE IF NOT EXISTS llm_panel_response (
            id            BIGSERIAL PRIMARY KEY,
            workspace_id  INTEGER NOT NULL REFERENCES workspace (id) ON DELETE CASCADE,
            prompt_id     BIGINT  NOT NULL REFERENCES llm_prompt (id) ON DELETE CASCADE,
            provider      TEXT    NOT NULL,      -- 'google' | 'openrouter'
            model         TEXT    NOT NULL,      -- e.g. 'gemini-2.0-flash', 'openai/gpt-4o-mini'
            day           DATE    NOT NULL,
            response_text TEXT    NOT NULL DEFAULT '',
            mentions      JSONB   NOT NULL DEFAULT '[]',
            error         TEXT,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_llm_panel_response_ws_day "
               "ON llm_panel_response (workspace_id, day)")
    op.execute("ALTER TABLE llm_panel_response ENABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON llm_panel_response")
    op.execute(
        f"CREATE POLICY tenant_isolation ON llm_panel_response "
        f"USING (workspace_id = {_TID}) WITH CHECK (workspace_id = {_TID})")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON llm_panel_response")
    op.drop_table("llm_panel_response")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON llm_prompt")
    op.drop_table("llm_prompt")
