"""feature_flag — per-workspace feature toggles

Revision ID: 0028_feature_flags
Revises: 0027_source_state_enabled
Create Date: 2026-09-09

One row per (workspace, feature_key) that has been turned **off**. Absence of a
row means the feature is on — everything is on by default. Keys are the flat
namespace in ``core/features.py``: ``surface.<slug>`` (a listening surface),
``module.<name>`` (listening / care / reporting / content), ``cap.<name>``
(ai_assist / surveys / alerts_dispatch / export / report_email).

Idempotent DDL; RLS policy matches 0025; reversible.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0028_feature_flags"
down_revision: Union[str, None] = "0027_source_state_enabled"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TID = "NULLIF(current_setting('app.tenant_id', true), '')::int"


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS feature_flag (
            workspace_id INTEGER NOT NULL REFERENCES workspace (id) ON DELETE CASCADE,
            feature_key  TEXT    NOT NULL,
            enabled      BOOLEAN NOT NULL DEFAULT true,
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT pk_feature_flag PRIMARY KEY (workspace_id, feature_key)
        )
    """)
    op.execute("ALTER TABLE feature_flag ENABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON feature_flag")
    op.execute(
        f"CREATE POLICY tenant_isolation ON feature_flag "
        f"USING (workspace_id = {_TID}) WITH CHECK (workspace_id = {_TID})")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON feature_flag")
    op.drop_table("feature_flag")
