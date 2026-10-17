"""location rating -- the listing's own overall Google rating + review count

Revision ID: 0039_location_rating
Revises: 0038_location
Create Date: 2026-09-25

Additive, nullable: ``rating`` / ``review_count`` are what the public listing
shows (NULL = not captured, never guessed); ``rating_source`` says where and
``rating_at`` when. ``downgrade`` drops the four columns.
"""
from typing import Sequence, Union

from alembic import op

from db import migration_guards as guards
import sqlalchemy as sa

revision: str = "0039_location_rating"
down_revision: Union[str, None] = "0038_location"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    guards.add_column("location", sa.Column("rating", sa.Float()))
    guards.add_column("location", sa.Column("review_count", sa.Integer()))
    guards.add_column("location", sa.Column("rating_source", sa.Text()))
    guards.add_column("location", sa.Column("rating_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    for c in ("rating_at", "rating_source", "review_count", "rating"):
        op.drop_column("location", c)
