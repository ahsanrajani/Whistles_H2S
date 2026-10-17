"""tenant columns — workspace_id on every scoped child table

Revision ID: 0002_tenant_columns
Revises: 0001_baseline
Create Date: 2026-09-03

P1.3a. The tenant is the workspace. `brand` / `item` / `surface_status` / `run`
/ `api_key` / `user` already carry `workspace_id`; this denormalises it onto the
FK-chained children (`mention`, `sentiment`, `mention_class`, `gold_label`,
`dupe_edge`, `call_log`) so the P1.3b row-level-security policy is a direct
column check rather than a subquery. Nullable — legacy `call_log` rows for the
`score-*` / `classify-*` pseudo-runs have no `run` row to backfill from, and an
RLS `workspace_id = current_setting('app.tenant_id')::int` predicate excludes
NULL naturally.

Every step is idempotent (``IF NOT EXISTS`` / a ``pg_constraint`` guard): the
``0001`` baseline is built from ``Base.metadata``, which already carries these
columns, so on a fresh database this revision is a verified no-op; against a
database created before P1.3a it is a real migration.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0002_tenant_columns"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("mention", "sentiment", "mention_class", "gold_label", "dupe_edge", "call_log")

_BACKFILL = (
    "UPDATE mention m   SET workspace_id = i.workspace_id FROM item i    WHERE i.id  = m.item_id",
    "UPDATE dupe_edge d SET workspace_id = i.workspace_id FROM item i    WHERE i.id  = d.item_id",
    "UPDATE sentiment s     SET workspace_id = m.workspace_id FROM mention m WHERE m.id = s.mention_id",
    "UPDATE mention_class c SET workspace_id = m.workspace_id FROM mention m WHERE m.id = c.mention_id",
    "UPDATE gold_label g    SET workspace_id = m.workspace_id FROM mention m WHERE m.id = g.mention_id",
    "UPDATE call_log c  SET workspace_id = r.workspace_id FROM run r     WHERE r.id  = c.run_id",
)


def upgrade() -> None:
    for tbl in _TABLES:
        op.execute(f'ALTER TABLE "{tbl}" ADD COLUMN IF NOT EXISTS workspace_id INTEGER')
    for stmt in _BACKFILL:
        op.execute(stmt)
    for tbl in _TABLES:
        op.execute(f"""
            DO $$ BEGIN
              IF NOT EXISTS (SELECT 1 FROM pg_constraint
                             WHERE conname = 'fk_{tbl}_workspace_id_workspace') THEN
                ALTER TABLE "{tbl}" ADD CONSTRAINT fk_{tbl}_workspace_id_workspace
                  FOREIGN KEY (workspace_id) REFERENCES workspace (id) ON DELETE CASCADE;
              END IF;
            END $$;
        """)
        op.execute(f'CREATE INDEX IF NOT EXISTS ix_{tbl}_workspace_id ON "{tbl}" (workspace_id)')


def downgrade() -> None:
    for tbl in _TABLES:
        op.drop_index(f"ix_{tbl}_workspace_id", table_name=tbl)
        op.drop_constraint(f"fk_{tbl}_workspace_id_workspace", tbl, type_="foreignkey")
        op.drop_column(tbl, "workspace_id")
