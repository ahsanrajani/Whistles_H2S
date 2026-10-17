"""RBAC catalogue: ``role``, ``permission``, ``role_permission``, ``user_role``.

A permission is an ``(area, verb)`` pair — six areas (care, listening,
reporting, templates, queue, admin) × six verbs (view, create, edit, delete,
export, approve) = 36. Roles hold sets of them; users hold sets of roles. The
seeded matrix lives in Alembic ``0006``; the read layer is
``db/repositories/rbac.py``.
"""
from sqlalchemy import ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class Role(Base):
    __tablename__ = "role"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class Permission(Base):
    __tablename__ = "permission"
    __table_args__ = (
        UniqueConstraint("area", "verb", name="uq_permission_area_verb"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    area: Mapped[str] = mapped_column(Text, nullable=False)
    verb: Mapped[str] = mapped_column(Text, nullable=False)


class RolePermission(Base):
    __tablename__ = "role_permission"

    role_key: Mapped[str] = mapped_column(
        ForeignKey("role.key", ondelete="CASCADE"), primary_key=True)
    permission_id: Mapped[int] = mapped_column(
        ForeignKey("permission.id", ondelete="CASCADE"), primary_key=True)


class UserRole(Base):
    __tablename__ = "user_role"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), primary_key=True)
    role_key: Mapped[str] = mapped_column(
        ForeignKey("role.key", ondelete="CASCADE"), primary_key=True)
