"""metric warehouse — metric_fact (owned-analytics + non-social measures)

Revision ID: 0019_metric_fact
Revises: 0018_care_search
Create Date: 2026-09-04

P4.1 / P4.2. One wide, source-agnostic daily fact table: a ``(workspace, source,
entity, metric, day, dims)`` grain carrying a measure plus an optional
numerator / denominator so P4.2 can Wilson-score every proportion. Deliberately
not social-only — ``source`` also takes ``rank`` / ``crawl`` / ``llm_panel`` for
Phase 5 (Vantage) without a schema change.

Idempotent DDL; reversible.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0019_metric_fact"
down_revision: Union[str, None] = "0018_care_search"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS metric_fact (
            id            BIGSERIAL PRIMARY KEY,
            workspace_id  INTEGER NOT NULL REFERENCES workspace (id) ON DELETE CASCADE,
            source        TEXT NOT NULL,
            entity_type   TEXT NOT NULL,
            entity_ref    TEXT NOT NULL DEFAULT '',
            metric        TEXT NOT NULL,
            day           DATE NOT NULL,
            value         DOUBLE PRECISION,
            numerator     DOUBLE PRECISION,
            denominator   DOUBLE PRECISION,
            dims          JSONB NOT NULL DEFAULT '{}'::jsonb,
            dim_hash      TEXT NOT NULL DEFAULT '',
            captured_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_metric_fact_grain ON metric_fact
        (workspace_id, source, entity_type, entity_ref, metric, day, dim_hash)
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_metric_fact_lookup "
               "ON metric_fact (workspace_id, source, metric, day)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_metric_fact_entity "
               "ON metric_fact (workspace_id, entity_type, entity_ref, day)")


def downgrade() -> None:
    op.drop_table("metric_fact")
