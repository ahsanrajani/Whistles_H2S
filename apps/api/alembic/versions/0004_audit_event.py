"""audit_event — append-only record of privileged (operator) access

Revision ID: 0004_audit_event
Revises: 0003_rls
Create Date: 2026-09-03

P1.3c. A minimal audit table: an admin request that runs on the ``BYPASSRLS``
operator connection writes one row (``actor``, the ``tenant_id`` it touched,
``action``, an optional ``target``, ``at``). Enough to satisfy the P1.3 exit
criterion — cross-tenant admin access is logged.

Idempotent (``CREATE TABLE / INDEX IF NOT EXISTS``): the ``0001`` baseline
builds from ``Base.metadata``, which now carries ``AuditEvent``, so on a fresh
database this revision only needs to add the REVOKE.

The 0003 blanket grant hands the app roles UPDATE/DELETE on every table; this
revision revokes those two on ``audit_event`` so it is append-only for
``guru_app`` / ``guru_operator`` from the start. The owner (``guru``) is still
unrestricted — P1.6 formalises immutability (a trigger / dedicated writer role)
and adds the before/after, IP and wider wire points, with a test that an UPDATE
fails at the database level.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0004_audit_event"
down_revision: Union[str, None] = "0003_rls"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ROLES = "guru_app, guru_operator"


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS audit_event (
            id       SERIAL,
            actor    TEXT,
            tenant_id INTEGER,
            action   TEXT NOT NULL,
            target   TEXT,
            at       TEXT NOT NULL,
            CONSTRAINT pk_audit_event PRIMARY KEY (id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_event_at ON audit_event (at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_event_tenant_id ON audit_event (tenant_id)")
    # append-only for the app roles (owner keeps full rights)
    op.execute(f"REVOKE UPDATE, DELETE ON audit_event FROM {_ROLES}")


def downgrade() -> None:
    op.drop_index("ix_audit_event_tenant_id", table_name="audit_event")
    op.drop_index("ix_audit_event_at", table_name="audit_event")
    op.drop_table("audit_event")
