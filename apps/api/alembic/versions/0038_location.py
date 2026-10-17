"""location -- per-workspace branches, offices and ATMs

Revision ID: 0038_location
Revises: 0037_assign_floor
Create Date: 2026-09-25

Replaces the hard-coded Bank Alfalah branch list as the place a workspace's
physical locations live. Additive only; ``downgrade`` drops the table (and its
policy) -- rows are re-importable from the seed scripts. Tenant-isolated with the
same ``tenant_isolation`` policy as every other scoped table.
"""
from typing import Sequence, Union

from alembic import op

from db import migration_guards as guards
import sqlalchemy as sa

revision: str = "0038_location"
down_revision: Union[str, None] = "0037_assign_floor"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TID = "NULLIF(current_setting('app.tenant_id', true), '')::int"


def upgrade() -> None:
    guards.create_table(
        "location",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("workspace_id", sa.Integer(),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False, server_default="branch"),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("city", sa.Text()),
        sa.Column("region", sa.Text()),
        sa.Column("address", sa.Text()),
        sa.Column("lat", sa.Float()),
        sa.Column("lng", sa.Float()),
        sa.Column("place_id", sa.Text()),
        sa.Column("geo_precision", sa.Text()),       # supplied|address|street|area; NULL = no coords
        sa.Column("source", sa.Text(), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    guards.create_index("uq_location_ws_key", "location", ["workspace_id", "key"], unique=True)
    guards.create_index("ix_location_ws_kind", "location", ["workspace_id", "kind"])
    op.execute('ALTER TABLE "location" ENABLE ROW LEVEL SECURITY')
    op.execute('DROP POLICY IF EXISTS tenant_isolation ON "location"')
    op.execute(f'CREATE POLICY tenant_isolation ON "location" '
               f'USING (workspace_id = {_TID}) WITH CHECK (workspace_id = {_TID})')


def downgrade() -> None:
    op.execute('DROP POLICY IF EXISTS tenant_isolation ON "location"')
    op.drop_table("location")
