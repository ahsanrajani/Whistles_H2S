"""routing_policy.auto_assign_after_case -- auto-assignment only touches newer cases

Revision ID: 0037_assign_floor
Revises: 0036_assign_strategy
Create Date: 2026-09-21

Cases already waiting unassigned when auto-assignment is introduced (or when a
supervisor changes the rule) must stay unassigned; only cases that arrive afterwards
are handed out. ``auto_assign_after_case`` is the highest case id at that moment --
ids only grow, so it is immune to a backfilled case carrying an old ``opened_at``.
NULL means "no floor" (a workspace that never had cases).

Existing workspaces get their floor here; a workspace with no policy row gets one so
its current backlog is held back too. Downgrade drops the column and keeps any rows
inserted here (they are all defaults, i.e. identical to having no row).
"""
from typing import Sequence, Union

from alembic import op

from db import migration_guards as guards
import sqlalchemy as sa

revision: str = "0037_assign_floor"
down_revision: Union[str, None] = "0036_assign_strategy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    guards.add_column("routing_policy", sa.Column("auto_assign_after_case", sa.BigInteger(), nullable=True))
    conn = op.get_bind()
    # The sequence, not MAX(id): immune to row-level security hiding cases here.
    seq = conn.execute(sa.text("SELECT pg_get_serial_sequence('\"case\"', 'id')")).scalar()
    last = conn.execute(sa.text(f"SELECT last_value FROM {seq}")).scalar() if seq else 0
    conn.execute(sa.text(
        "INSERT INTO routing_policy (workspace_id) SELECT id FROM workspace "
        "WHERE id NOT IN (SELECT workspace_id FROM routing_policy)"))
    conn.execute(sa.text("UPDATE routing_policy SET auto_assign_after_case = :n"), {"n": int(last or 0)})


def downgrade() -> None:
    op.drop_column("routing_policy", "auto_assign_after_case")
