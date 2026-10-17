"""project entity — one workspace has many projects

Revision ID: 0025_project
Revises: 0024_rls_phase234
Create Date: 2026-09-04

Frontend Phase F0.1. A ``project`` is the unit the ``/t/{tenant}/p/{project}/…``
URL addresses: today a workspace's listening surfaces are one ``listening``
project; a Vantage site will be another project in the same workspace with no
schema change. Every existing workspace gets a default ``listening`` project.

Idempotent DDL; RLS policy matches 0003/0024; reversible.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0025_project"
down_revision: Union[str, None] = "0024_rls_phase234"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TID = "NULLIF(current_setting('app.tenant_id', true), '')::int"


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS project (
            id           BIGSERIAL PRIMARY KEY,
            workspace_id INTEGER NOT NULL REFERENCES workspace (id) ON DELETE CASCADE,
            slug         TEXT NOT NULL,
            name         TEXT NOT NULL,
            kind         TEXT NOT NULL DEFAULT 'listening',
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_project_ws_slug UNIQUE (workspace_id, slug)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_project_ws ON project (workspace_id)")

    op.execute("ALTER TABLE project ENABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON project")
    op.execute(
        f"CREATE POLICY tenant_isolation ON project "
        f"USING (workspace_id = {_TID}) WITH CHECK (workspace_id = {_TID})")

    # backfill a default listening project for every existing workspace
    op.execute("""
        INSERT INTO project (workspace_id, slug, name, kind)
        SELECT w.id, 'listening', 'Listening', 'listening'
        FROM workspace w
        WHERE NOT EXISTS (
            SELECT 1 FROM project p WHERE p.workspace_id = w.id AND p.slug = 'listening')
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON project")
    op.drop_table("project")
