"""audit hardening — before/after + ip columns, and DB-level immutability

Revision ID: 0007_audit_hardening
Revises: 0006_rbac
Create Date: 2026-09-03

P1.6. Widens ``audit_event`` (``before_state`` / ``after_state`` JSON snapshots,
``ip``) and makes it genuinely append-only: a ``BEFORE UPDATE OR DELETE`` row
trigger raises for *everyone*, including the owner — not just a revoked grant
(P1.3c). ``TRUNCATE`` bypasses row triggers, so the test-fixture reset still
works.

Idempotent: ``ADD COLUMN IF NOT EXISTS``, ``CREATE OR REPLACE FUNCTION``,
``DROP TRIGGER IF EXISTS`` before ``CREATE TRIGGER``.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0007_audit_hardening"
down_revision: Union[str, None] = "0006_rbac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE audit_event ADD COLUMN IF NOT EXISTS before_state TEXT")
    op.execute("ALTER TABLE audit_event ADD COLUMN IF NOT EXISTS after_state TEXT")
    op.execute("ALTER TABLE audit_event ADD COLUMN IF NOT EXISTS ip TEXT")
    op.execute("""
        CREATE OR REPLACE FUNCTION audit_event_append_only() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'audit_event is append-only (% blocked)', TG_OP;
        END $$;
    """)
    op.execute("DROP TRIGGER IF EXISTS audit_event_no_mutate ON audit_event")
    op.execute("""
        CREATE TRIGGER audit_event_no_mutate
        BEFORE UPDATE OR DELETE ON audit_event
        FOR EACH ROW EXECUTE FUNCTION audit_event_append_only()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_event_no_mutate ON audit_event")
    op.execute("DROP FUNCTION IF EXISTS audit_event_append_only()")
    op.drop_column("audit_event", "ip")
    op.drop_column("audit_event", "after_state")
    op.drop_column("audit_event", "before_state")
