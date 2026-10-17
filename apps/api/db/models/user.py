"""The ``user`` table — login identities.

Note: ``user`` is a reserved word in Postgres; SQLAlchemy quotes it. Raw SQL in
the repository layer (P1.2) must write ``FROM "user"``.
"""
from sqlalchemy import (ForeignKey, Index, Integer, Text, UniqueConstraint,
                        text)
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class User(Base):
    __tablename__ = "user"
    __table_args__ = (
        # `role` is the primary role (display + operator-connection check); the
        # full set is in `user_role`. No CHECK — the RBAC catalogue (`role`
        # table, Alembic 0006) is the source of truth.
        Index("uq_user_email", "email", unique=True,
              postgresql_where=text("email IS NOT NULL")),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    # NULL = all workspaces (admin / operator)
    workspace_id: Mapped[int | None] = mapped_column(Integer)
    active: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str | None] = mapped_column(Text)  # for OAuth account matching


class Identity(Base):
    """An external login (Google, …) linked to a :class:`User`. Native
    username/password auth does not use this table."""
    __tablename__ = "identity"
    __table_args__ = (
        UniqueConstraint("provider", "subject", name="uq_identity_provider_subject"),
        Index("ix_identity_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    email: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    last_login_at: Mapped[str | None] = mapped_column(Text)
