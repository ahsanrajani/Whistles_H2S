"""``audit_event`` — append-only record of privileged / security-relevant acts.

One row per: login (and failed login), permission grant, tenant switch, data
export, mention hide/show, brand-rule edit, and every mutation on the operator
connection. ``before_state`` / ``after_state`` hold JSON snapshots where they
apply. A ``BEFORE UPDATE OR DELETE`` trigger (Alembic ``0007``) makes the table
immutable for everyone, owner included.
"""
from sqlalchemy import Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class AuditEvent(Base):
    __tablename__ = "audit_event"
    __table_args__ = (
        Index("ix_audit_event_at", "at"),
        Index("ix_audit_event_tenant_id", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor: Mapped[str | None] = mapped_column(Text)       # user id / username; NULL = system
    tenant_id: Mapped[int | None] = mapped_column(Integer)  # workspace acted on
    action: Mapped[str] = mapped_column(Text, nullable=False)
    target: Mapped[str | None] = mapped_column(Text)
    before_state: Mapped[str | None] = mapped_column(Text)  # JSON snapshot, pre-change
    after_state: Mapped[str | None] = mapped_column(Text)   # JSON snapshot, post-change
    ip: Mapped[str | None] = mapped_column(Text)
    at: Mapped[str] = mapped_column(Text, nullable=False)  # ISO 8601
