"""Test package init.

Point every test at a dedicated ``guru_test`` database on the same Postgres the
compose stack runs, make sure it exists, and bring it to head with Alembic —
which also creates the ``guru_app`` / ``guru_operator`` roles and the RLS
policies. Runs before anything imports ``db.session`` (which binds its engines
to the derived role URLs at import time).
"""
import os

import sqlalchemy as _sa

# Sessions run on in-process fakeredis and Google sign-in runs in mock mode for
# the suite — set to "" (not popped) so app.py's load_dotenv(override=False)
# can't refill them from a local .env.
os.environ["REDIS_URL"] = ""
os.environ["GOOGLE_OAUTH_CLIENT_ID"] = ""
os.environ["GOOGLE_OAUTH_CLIENT_SECRET"] = ""
# Quiet the per-request JSON access line during the suite; warnings + errors
# still print. test_obs_logging sets its own level where it needs INFO.
os.environ.setdefault("LOG_LEVEL", "WARNING")

_BASE = os.environ.get("DATABASE_URL", "postgresql+psycopg://guru:guru@localhost:5432/guru")
_ADMIN_URL = _BASE.rsplit("/", 1)[0] + "/postgres"
TEST_URL = _BASE.rsplit("/", 1)[0] + "/guru_test"          # owner (guru)

_admin = _sa.create_engine(_ADMIN_URL, isolation_level="AUTOCOMMIT", future=True)
with _admin.connect() as _c:
    if not _c.execute(_sa.text("SELECT 1 FROM pg_database WHERE datname='guru_test'")).scalar():
        _c.execute(_sa.text("CREATE DATABASE guru_test"))
_admin.dispose()

os.environ["DATABASE_URL"] = TEST_URL

# Bring guru_test to head as the owner (this also CREATE ROLEs guru_app /
# guru_operator and installs the RLS policies).
from alembic import command as _command  # noqa: E402
from alembic.config import Config as _Config  # noqa: E402

_HERE = os.path.dirname(os.path.abspath(__file__))
_API_ROOT = os.path.dirname(_HERE)
_cfg = _Config(os.path.join(_API_ROOT, "alembic.ini"))
_cfg.set_main_option("script_location", os.path.join(_API_ROOT, "alembic"))
_cfg.set_main_option("sqlalchemy.url", TEST_URL)
_command.upgrade(_cfg, "head")

# Now safe to import the app's DB layer (engines derive guru_app / guru_operator URLs).
from db.models import Base  # noqa: E402,F401
from db.session import engine, operator_engine  # noqa: E402

# A plain owner engine for fixture teardown (TRUNCATE is an owner privilege).
owner_engine = _sa.create_engine(TEST_URL, future=True)

# The RBAC catalogue (role / permission / role_permission) is version-pinned
# reference data seeded by Alembic 0006, not per-test state — keep it across
# truncations. `user_role` IS per-user and is cleared via the `user` cascade.
_CATALOGUE = {"role", "permission", "role_permission"}
_TABLES = [t.name for t in reversed(Base.metadata.sorted_tables)
           if t.name not in _CATALOGUE]


def truncate_all() -> None:
    with owner_engine.begin() as conn:
        conn.execute(_sa.text("SET LOCAL lock_timeout = '10s'"))
        conn.execute(_sa.text(
            "TRUNCATE " + ", ".join(f'"{t}"' for t in _TABLES) + " RESTART IDENTITY CASCADE"))


# Start every suite run from a clean slate: a run that was interrupted mid-test
# (setUp failure skips tearDown) can leave committed rows that then break the
# first DbTestCase, which relies on rollback isolation and never truncates.
truncate_all()
