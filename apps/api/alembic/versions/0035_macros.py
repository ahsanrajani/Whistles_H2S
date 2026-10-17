"""macros -- reply + actions, quick macros, auto (rule-based) macros

Revision ID: 0035_macros
Revises: 0034_customer_profile_fields
Create Date: 2026-09-18

A macro is the existing ``care_template`` row grown into "reply text + case
actions": every template already in the table stays valid as a macro with no
actions. New columns carry the shortcut (``/refund``), the quick-macro pin (shown
in the composer's Send dropdown, ordered by ``quick_order``) and the action list.

``care_macro_rule`` is an *auto macro*: one or more triggers (any-of) plus
filters (all-of) that run a macro against a case without an agent clicking.
``care_macro_run`` makes every rule fire at most once per case (also the loop
guard). ``case`` gains ``priority`` and ``tags`` so the ``set_priority`` /
``add_tags`` actions have somewhere to write; both are optional and NULL / empty
for every existing case.
"""
from typing import Sequence, Union

from alembic import op

from db import migration_guards as guards
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0035_macros"
down_revision: Union[str, None] = "0034_customer_profile_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TID = "NULLIF(current_setting('app.tenant_id', true), '')::int"


def upgrade() -> None:
    guards.add_column("care_template", sa.Column("shortcut", sa.Text(), nullable=True))
    guards.add_column("care_template", sa.Column("description", sa.Text(), nullable=True))
    guards.add_column("care_template", sa.Column(
        "is_quick", sa.Boolean(), nullable=False, server_default=sa.false()))
    guards.add_column("care_template", sa.Column(
        "quick_order", sa.Integer(), nullable=False, server_default="0"))
    guards.add_column("care_template", sa.Column(
        "actions", postgresql.JSONB(), nullable=False, server_default="[]"))
    guards.add_column("care_template", sa.Column(
        "active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.execute(
        "CREATE UNIQUE INDEX ux_care_template_shortcut "
        "ON care_template (workspace_id, lower(shortcut)) WHERE shortcut IS NOT NULL")

    guards.add_column("case", sa.Column("priority", sa.Text(), nullable=True))
    guards.add_column("case", sa.Column(
        "tags", postgresql.JSONB(), nullable=False, server_default="[]"))

    guards.create_table(
        "care_macro_rule",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("workspace_id", sa.Integer(),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("macro_id", sa.BigInteger(),
                  sa.ForeignKey("care_template.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("triggers", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("filters", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("reply_mode", sa.Text(), nullable=False, server_default="hold"),
        sa.Column("created_by", sa.Integer(),
                  sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("last_fired_at", sa.DateTime(timezone=True), nullable=True),
    )
    guards.create_index("ix_care_macro_rule_ws", "care_macro_rule", ["workspace_id", "active"])

    guards.create_table(
        "care_macro_run",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("workspace_id", sa.Integer(),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rule_id", sa.BigInteger(),
                  sa.ForeignKey("care_macro_rule.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", sa.BigInteger(),
                  sa.ForeignKey("case.id", ondelete="CASCADE"), nullable=False),
        sa.Column("trigger", sa.Text(), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("fired_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("rule_id", "case_id", name="uq_care_macro_run_rule_case"),
    )
    guards.create_index("ix_care_macro_run_ws", "care_macro_run", ["workspace_id", "fired_at"])

    for table in ("care_macro_rule", "care_macro_run"):
        expr = f"workspace_id = {_TID}"
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'CREATE POLICY tenant_isolation ON "{table}" '
                   f'USING ({expr}) WITH CHECK ({expr})')


def downgrade() -> None:
    for table in ("care_macro_run", "care_macro_rule"):
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
        op.drop_table(table)
    op.drop_column("case", "tags")
    op.drop_column("case", "priority")
    op.execute("DROP INDEX IF EXISTS ux_care_template_shortcut")
    for col in ("active", "actions", "quick_order", "is_quick", "description", "shortcut"):
        op.drop_column("care_template", col)
