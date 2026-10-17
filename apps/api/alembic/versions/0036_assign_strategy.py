"""routing_policy.assign_strategy -- which rule auto-assigns a new case

Revision ID: 0036_assign_strategy
Revises: 0035_macros
Create Date: 2026-09-21

A supervisor picks how a newly arrived case is handed to an agent: ``manual``
(never automatic), ``round_robin``, ``least_busy`` or ``longest_idle``. The
default is ``least_busy`` -- what ``routing.assign_next`` always did -- so a
workspace that never touches the setting keeps today's behaviour.
"""
from typing import Sequence, Union

from alembic import op

from db import migration_guards as guards
import sqlalchemy as sa

revision: str = "0036_assign_strategy"
down_revision: Union[str, None] = "0035_macros"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    guards.add_column("routing_policy", sa.Column(
        "assign_strategy", sa.Text(), nullable=False, server_default="least_busy"))
    guards.create_check_constraint(
        "ck_routing_policy_assign_strategy", "routing_policy",
        "assign_strategy IN ('manual','round_robin','least_busy','longest_idle')")


def downgrade() -> None:
    op.drop_constraint("ck_routing_policy_assign_strategy", "routing_policy", type_="check")
    op.drop_column("routing_policy", "assign_strategy")
