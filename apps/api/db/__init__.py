"""Database layer — SQLAlchemy 2.0 models, engine/session, Alembic migrations.

From Phase 1 on, all persistence goes through here. No raw SQL string lives
outside this package and ``alembic/``.
"""
from .base import Base
from .session import SessionLocal, engine, get_session

__all__ = ["Base", "engine", "SessionLocal", "get_session"]
