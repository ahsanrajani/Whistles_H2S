"""source_state — per (workspace, source) cursor + circuit-breaker state

Revision ID: 0011_source_state
Revises: 0010_item_simhash
Create Date: 2026-09-04

P2.2. One row per (workspace, source): the incremental cursor and the circuit
breaker's persisted state, so a breaker that opened stays open across a
restart. P2.3 grows this table with the source-health columns (items last run,
last run id) and the admin surface + silence alert.

Idempotent (``CREATE TABLE / INDEX IF NOT EXISTS``) — the ``0001`` baseline
builds it from ``Base.metadata`` on a fresh DB.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0011_source_state"
down_revision: Union[str, None] = "0010_item_simhash"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS source_state (
            workspace_id         INTEGER NOT NULL
                REFERENCES workspace (id) ON DELETE CASCADE,
            source               TEXT    NOT NULL,
            cursor_kind          TEXT    NOT NULL DEFAULT 'none',
            cursor_value         TEXT,
            circuit_state        TEXT    NOT NULL DEFAULT 'closed',
            consecutive_failures INTEGER NOT NULL DEFAULT 0,
            opened_at            TIMESTAMPTZ,
            last_attempt_at      TIMESTAMPTZ,
            last_success_at      TIMESTAMPTZ,
            last_error           TEXT,
            updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT pk_source_state PRIMARY KEY (workspace_id, source)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_source_state_open "
               "ON source_state (opened_at) WHERE circuit_state = 'open'")


def downgrade() -> None:
    op.drop_table("source_state")
