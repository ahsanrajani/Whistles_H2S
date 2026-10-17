"""Engines and session factories. Postgres only — no SQLite fallback.

Three roles (created by Alembic 0003):

- ``guru``          — table owner. Alembic migrations and the first-boot seed.
- ``guru_app``      — the app runtime. Row-level security **is** enforced; every
                      request sets ``app.tenant_id`` and only sees that tenant.
- ``guru_operator`` — ``BYPASSRLS``. The operator surface (admin endpoints) that
                      legitimately spans tenants.

``DATABASE_URL`` is the owner URL (``…/guru``). ``APP_DATABASE_URL`` /
``OPERATOR_DATABASE_URL`` override the other two; unset, they are derived by
swapping the username.
"""
import os

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

DEFAULT_URL = "postgresql+psycopg://guru:guru@localhost:5432/guru"


def database_url() -> str:
    """The owner URL — Alembic and the seed run as the table owner."""
    url = os.environ.get("DATABASE_URL", DEFAULT_URL)
    if url.startswith("sqlite"):
        raise RuntimeError(
            "SQLite is not supported from Phase 1 on — set DATABASE_URL to a "
            "postgresql+psycopg://… URL (see ops/compose/docker-compose.yml)."
        )
    return url


def _role_url(env_name: str, role: str) -> str:
    """The owner URL with only the username swapped — same host / password / db.
    Alembic 0003 gives ``guru_app`` / ``guru_operator`` the owner's password so
    the compose stack needs one secret. Override per role with ``env_name``."""
    explicit = os.environ.get(env_name)
    if explicit:
        return explicit
    # render_as_string(hide_password=False) — plain str(url) masks it as "***",
    # which then round-trips back in as the literal password.
    return make_url(database_url()).set(username=role).render_as_string(hide_password=False)


def app_url() -> str:
    return _role_url("APP_DATABASE_URL", "guru_app")


def operator_url() -> str:
    return _role_url("OPERATOR_DATABASE_URL", "guru_operator")


# The app runtime — RLS enforced.
engine = create_engine(app_url(), future=True, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, class_=Session, expire_on_commit=False,
                            autoflush=False, future=True)

# The operator surface — BYPASSRLS.
operator_engine = create_engine(operator_url(), future=True, pool_pre_ping=True)
OperatorSession = sessionmaker(bind=operator_engine, class_=Session,
                               expire_on_commit=False, autoflush=False, future=True)


def get_session() -> Session:
    """A new RLS-enforced session. Caller closes it."""
    return SessionLocal()


def get_operator_session() -> Session:
    """A new BYPASSRLS session for the operator surface. Caller closes it."""
    return OperatorSession()
