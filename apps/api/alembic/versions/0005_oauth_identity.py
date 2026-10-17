"""oauth identity — user.email + the identity link table

Revision ID: 0005_oauth_identity
Revises: 0004_audit_event
Create Date: 2026-09-03

P1.4b. Native username/password login stays; this adds "Sign in with Google".

- ``user.email`` — nullable, unique where set. An admin records it when creating
  a user; a Google login is matched to an existing account by this address.
- ``identity`` — one row per linked external login: ``(provider, subject)`` from
  the IdP, pointing at a ``user``. ``subject`` is the stable Google ``sub``.

Auth-layer tables (like ``user``) are reached through the operator connection
before a tenant is resolved, so ``identity`` stays out of the RLS policy set.

Idempotent — ``0001`` builds from ``Base.metadata`` which now carries both, so
on a fresh database this revision is a near no-op.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0005_oauth_identity"
down_revision: Union[str, None] = "0004_audit_event"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS email TEXT')
    op.execute('CREATE UNIQUE INDEX IF NOT EXISTS uq_user_email '
               'ON "user" (email) WHERE email IS NOT NULL')
    op.execute("""
        CREATE TABLE IF NOT EXISTS identity (
            id            SERIAL,
            provider      TEXT    NOT NULL,
            subject       TEXT    NOT NULL,
            user_id       INTEGER NOT NULL,
            email         TEXT,
            created_at    TEXT    NOT NULL,
            last_login_at TEXT,
            CONSTRAINT pk_identity PRIMARY KEY (id),
            CONSTRAINT fk_identity_user_id_user
                FOREIGN KEY (user_id) REFERENCES "user" (id) ON DELETE CASCADE,
            CONSTRAINT uq_identity_provider_subject UNIQUE (provider, subject)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_identity_user_id ON identity (user_id)")


def downgrade() -> None:
    op.drop_index("ix_identity_user_id", table_name="identity")
    op.drop_table("identity")
    op.execute("DROP INDEX IF EXISTS uq_user_email")
    op.drop_column("user", "email")
