"""care search — pg_trgm + FTS indexes for customer / case / case_message

Revision ID: 0018_care_search
Revises: 0017_knowledge
Create Date: 2026-09-04

P3.9. Trigram indexes on the customer identity columns (name / handle / email /
phone) and a GIN full-text index on ``case_message.body`` so cross-entity
autocomplete stays sub-300ms at scale.

Idempotent (``CREATE EXTENSION / INDEX IF NOT EXISTS``).
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0018_care_search"
down_revision: Union[str, None] = "0017_knowledge"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    for col in ("display_name", "handle", "email", "phone"):
        op.execute(f"CREATE INDEX IF NOT EXISTS ix_customer_trgm_{col} "
                   f"ON customer USING GIN (lower({col}) gin_trgm_ops)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_case_message_fts "
               "ON case_message USING GIN (to_tsvector('english', body))")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_case_message_fts")
    for col in ("display_name", "handle", "email", "phone"):
        op.execute(f"DROP INDEX IF EXISTS ix_customer_trgm_{col}")
