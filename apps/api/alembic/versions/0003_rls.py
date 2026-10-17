"""row-level security — roles + tenant-isolation policies

Revision ID: 0003_rls
Revises: 0002_tenant_columns
Create Date: 2026-09-03

P1.3b. Creates the two runtime roles and locks every tenant-scoped table behind
a policy keyed on ``current_setting('app.tenant_id', true)::int`` — which is
NULL when unset, so a query with no tenant context sees zero rows.

- ``guru_app``      LOGIN, RLS enforced. The app runtime.
- ``guru_operator`` LOGIN, BYPASSRLS. The operator/admin surface.
Roles are cluster-global; the ``IF NOT EXISTS`` guard makes this safe to run
against a second database (``guru_test``). The table owner (``guru``) is not
subject to RLS, so Alembic and the seed are unaffected.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0003_rls"
down_revision: Union[str, None] = "0002_tenant_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# NULLIF(..., '') because once a pooled connection has had a "SET LOCAL
# app.tenant_id" rolled back, Postgres reports the placeholder GUC as '' (empty
# string), not NULL — and ''::int errors instead of yielding "no tenant". NULLIF
# folds that back to NULL, so the policy safely matches zero rows.
_TID = "NULLIF(current_setting('app.tenant_id', true), '')::int"

# table -> the row's tenant expression
_POLICIES = {
    "workspace": "id = " + _TID,
    "brand": "workspace_id = " + _TID,
    "item": "workspace_id = " + _TID,
    "mention": "workspace_id = " + _TID,
    "sentiment": "workspace_id = " + _TID,
    "mention_class": "workspace_id = " + _TID,
    "gold_label": "workspace_id = " + _TID,
    "dupe_edge": "workspace_id = " + _TID,
    "surface_status": "workspace_id = " + _TID,
    "run": "workspace_id = " + _TID,
    "call_log": "workspace_id = " + _TID,
    # shared / environment-backed credentials (workspace 0) stay visible to all
    "api_key": "(workspace_id = " + _TID + " OR workspace_id = 0)",
}

_ROLES = ("guru_app", "guru_operator")


def _role_password() -> str:
    """GURU_ROLE_PASSWORD, else the owner's own password from DATABASE_URL, else 'guru'."""
    import os

    from sqlalchemy.engine import make_url

    from db.session import database_url
    return os.environ.get("GURU_ROLE_PASSWORD") or make_url(database_url()).password or "guru"


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
          IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'guru_app') THEN
            CREATE ROLE guru_app;
          END IF;
          IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'guru_operator') THEN
            CREATE ROLE guru_operator;
          END IF;
        END $$;
    """)
    # Authoritative each run — a role left from an earlier experiment keeps its
    # old password without this, and the ``IF NOT EXISTS`` guard would hide that.
    # The password is the owner's (what db/session.py::_role_url puts in the derived URLs), unless
    # GURU_ROLE_PASSWORD overrides it; with neither it stays 'guru' as in the compose stack.
    pw = _role_password().replace("'", "''")
    # Postgres 16 lets a role change SUPERUSER / BYPASSRLS only if it holds that attribute itself, even to switch it
    # *off*. A managed-Postgres owner (Cloud SQL) has CREATEROLE but neither, so the strict statement raises
    # insufficient_privilege. New roles already default to no superuser and no bypass, so the fallback just sets
    # LOGIN + password. For guru_operator that means it will NOT bypass RLS: point OPERATOR_DATABASE_URL at the
    # table owner, which is exempt from RLS because nothing here uses FORCE ROW LEVEL SECURITY.
    op.get_bind().exec_driver_sql(f"""
        DO $guru$ BEGIN
          BEGIN
            ALTER ROLE guru_app WITH LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD '{pw}';
          EXCEPTION WHEN insufficient_privilege THEN
            ALTER ROLE guru_app WITH LOGIN PASSWORD '{pw}';
          END;
          BEGIN
            ALTER ROLE guru_operator WITH LOGIN NOSUPERUSER BYPASSRLS PASSWORD '{pw}';
          EXCEPTION WHEN insufficient_privilege THEN
            ALTER ROLE guru_operator WITH LOGIN PASSWORD '{pw}';
            RAISE WARNING 'guru_operator has NO BYPASSRLS (privilege): set OPERATOR_DATABASE_URL to the owner role';
          END;
        END $guru$;
    """)
    roles = ", ".join(_ROLES)
    op.execute(f"GRANT USAGE ON SCHEMA public TO {roles}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {roles}")
    op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {roles}")
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
               f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {roles}")
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
               f"GRANT USAGE, SELECT ON SEQUENCES TO {roles}")

    for table, expr in _POLICIES.items():
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING ({expr}) WITH CHECK ({expr})")


def downgrade() -> None:
    for table in _POLICIES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    # Roles are cluster-global and may own nothing here; drop membership grants
    # but leave the roles (a later DB might still use them). Revoke to be tidy.
    roles = ", ".join(_ROLES)
    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {roles}")
    op.execute(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {roles}")
