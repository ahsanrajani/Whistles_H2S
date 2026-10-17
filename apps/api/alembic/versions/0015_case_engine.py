"""case engine — customer, case, case_message, case_note, case_event

Revision ID: 0015_case_engine
Revises: 0014_outbound_action
Create Date: 2026-09-04

P3.2. A ``customer`` is resolved across channels by identity keys; inbound
messages for one customer within a two-hour window consolidate into a single
``case``; ``case_event`` is the per-case activity log the SLA reports and the
care audit read.

Idempotent DDL.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0015_case_engine"
down_revision: Union[str, None] = "0014_outbound_action"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS customer (
            id           BIGSERIAL PRIMARY KEY,
            workspace_id INTEGER NOT NULL REFERENCES workspace (id) ON DELETE CASCADE,
            display_name TEXT,
            platform     TEXT,
            handle       TEXT,
            email        TEXT,
            phone        TEXT,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_customer_ws_handle "
               "ON customer (workspace_id, platform, handle)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_customer_ws_email "
               "ON customer (workspace_id, email) WHERE email IS NOT NULL")
    op.execute("CREATE INDEX IF NOT EXISTS ix_customer_ws_phone "
               "ON customer (workspace_id, phone) WHERE phone IS NOT NULL")

    op.execute("""
        CREATE TABLE IF NOT EXISTS "case" (
            id                BIGSERIAL PRIMARY KEY,
            workspace_id      INTEGER NOT NULL REFERENCES workspace (id) ON DELETE CASCADE,
            customer_id       BIGINT NOT NULL REFERENCES customer (id) ON DELETE CASCADE,
            channel           TEXT NOT NULL,
            state             TEXT NOT NULL DEFAULT 'open',
            assignee_id       INTEGER REFERENCES "user" (id) ON DELETE SET NULL,
            closure_category  TEXT,
            opened_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            first_response_at TIMESTAMPTZ,
            closed_at         TIMESTAMPTZ,
            last_activity_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute('CREATE INDEX IF NOT EXISTS ix_case_ws_customer '
               'ON "case" (workspace_id, customer_id, state)')
    op.execute('CREATE INDEX IF NOT EXISTS ix_case_open '
               'ON "case" (workspace_id, last_activity_at) WHERE state <> \'closed\'')

    op.execute("""
        CREATE TABLE IF NOT EXISTS case_message (
            id                BIGSERIAL PRIMARY KEY,
            case_id           BIGINT NOT NULL REFERENCES "case" (id) ON DELETE CASCADE,
            workspace_id      INTEGER NOT NULL,
            direction         TEXT NOT NULL,             -- inbound | outbound
            channel           TEXT NOT NULL,
            platform_ref      TEXT,
            author            TEXT,
            body              TEXT NOT NULL,
            sent_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
            outbound_action_id BIGINT REFERENCES outbound_action (id) ON DELETE SET NULL
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_case_message_case "
               "ON case_message (case_id, sent_at)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS case_note (
            id         BIGSERIAL PRIMARY KEY,
            case_id    BIGINT NOT NULL REFERENCES "case" (id) ON DELETE CASCADE,
            author_id  INTEGER REFERENCES "user" (id) ON DELETE SET NULL,
            body       TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_case_note_case ON case_note (case_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS case_event (
            id      BIGSERIAL PRIMARY KEY,
            case_id BIGINT NOT NULL REFERENCES "case" (id) ON DELETE CASCADE,
            actor   TEXT,
            kind    TEXT NOT NULL,
            detail  JSONB NOT NULL DEFAULT '{}',
            at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_case_event_case ON case_event (case_id, at)")


def downgrade() -> None:
    op.drop_table("case_event")
    op.drop_table("case_note")
    op.drop_table("case_message")
    op.execute('DROP TABLE IF EXISTS "case"')
    op.drop_table("customer")
