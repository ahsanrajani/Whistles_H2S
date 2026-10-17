"""baseline — the current schema as SQLAlchemy models

Revision ID: 0001_baseline
Revises:
Create Date: 2026-09-03

Ports schema.sql (13 tables) to Postgres 1:1. As the first revision it builds
the whole schema from ``Base.metadata`` so it cannot drift from the models;
later revisions use explicit ``op`` operations. ``downgrade()`` drops everything.
"""
from typing import Sequence, Union

from alembic import op

from db.models import Base

revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
