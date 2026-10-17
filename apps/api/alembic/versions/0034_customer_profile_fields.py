"""customer profile fields -- the rest of the BRD's 25-field panel

Revision ID: 0034_customer_profile_fields
Revises: 0033_care_console_scoping
Create Date: 2026-09-11

Hamza, 2026-09-11 (Customer panel screenshot): "these details should be
editable." Most of the panel's fields were always-null UI placeholders
with no backing column (console-view.tsx::ProfilePane's own comment:
"Fields with no data source yet render 'unknown'"). This adds real columns
for every one of those that's a genuine manually-entered fact, not a
computed one -- lifetime/open case counts, relationship-since, first
contact, last activity, avg CSAT and sentiment trend all stay derived at
read time (core/owned_posts.py-style: computed fresh, never stored) and
are not part of this revision.

platform/handle are deliberately NOT added here (they already exist) --
core/cases.py::resolve_customer() dedupes new inbound messages against
(workspace_id, platform, handle), so those two stay off the editable set;
everything below is safe to change without breaking that matching.
"""
from typing import Sequence, Union

from alembic import op

from db import migration_guards as guards
import sqlalchemy as sa

revision: str = "0034_customer_profile_fields"
down_revision: Union[str, None] = "0033_care_console_scoping"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TEXT_COLUMNS = (
    "preferred_name", "other_handles", "location", "country", "language",
    "timezone", "segment", "account_status", "preferred_channel", "tags", "notes",
)
_BOOL_COLUMNS = ("vip", "blocked")


def upgrade() -> None:
    for col in _TEXT_COLUMNS:
        guards.add_column("customer", sa.Column(col, sa.Text(), nullable=True))
    for col in _BOOL_COLUMNS:
        guards.add_column("customer", sa.Column(col, sa.Boolean(), nullable=True))


def downgrade() -> None:
    for col in (*_TEXT_COLUMNS, *_BOOL_COLUMNS):
        op.drop_column("customer", col)
