"""The case engine (build plan §5 / P3.2): ``customer``, ``case``,
``case_message``, ``case_note``, ``case_event``."""
from datetime import datetime

from sqlalchemy import (BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, Text, func)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class Customer(Base):
    __tablename__ = "customer"
    __table_args__ = (
        Index("ix_customer_ws_handle", "workspace_id", "platform", "handle"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False)
    display_name: Mapped[str | None] = mapped_column(Text)
    platform: Mapped[str | None] = mapped_column(Text)
    handle: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    # 0034 -- the rest of the BRD's 25-field customer profile (build plan),
    # editable by an agent/supervisor from the Care console's Customer panel.
    # platform/handle stay off this list deliberately: they're the
    # (workspace_id, platform, handle) match key core/cases.py::
    # resolve_customer() dedupes new inbound messages against, so editing
    # them could silently orphan a real customer's future contacts.
    preferred_name: Mapped[str | None] = mapped_column(Text)
    other_handles: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(Text)
    timezone: Mapped[str | None] = mapped_column(Text)
    segment: Mapped[str | None] = mapped_column(Text)
    account_status: Mapped[str | None] = mapped_column(Text)
    vip: Mapped[bool | None] = mapped_column(Boolean)
    blocked: Mapped[bool | None] = mapped_column(Boolean)
    preferred_channel: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())


class Case(Base):
    __tablename__ = "case"
    __table_args__ = (
        Index("ix_case_ws_customer", "workspace_id", "customer_id", "state"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customer.id", ondelete="CASCADE"), nullable=False)
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False, server_default="open")
    assignee_id: Mapped[int | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"))
    closure_category: Mapped[str | None] = mapped_column(Text)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
    first_response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
    # Set by a macro's set_priority / add_tags action (0035); NULL / [] otherwise.
    priority: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")


class CaseMessage(Base):
    __tablename__ = "case_message"
    __table_args__ = (Index("ix_case_message_case", "case_id", "sent_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    case_id: Mapped[int] = mapped_column(
        ForeignKey("case.id", ondelete="CASCADE"), nullable=False)
    workspace_id: Mapped[int] = mapped_column(Integer, nullable=False)
    direction: Mapped[str] = mapped_column(Text, nullable=False)   # inbound | outbound
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    platform_ref: Mapped[str | None] = mapped_column(Text)
    # the real, public, clickable URL of the source comment/post/review --
    # distinct from platform_ref, which is the API id a reply targets and is
    # not always something a browser can open.
    permalink: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
    outbound_action_id: Mapped[int | None] = mapped_column(
        ForeignKey("outbound_action.id", ondelete="SET NULL"))


class CaseNote(Base):
    __tablename__ = "case_note"
    __table_args__ = (Index("ix_case_note_case", "case_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    case_id: Mapped[int] = mapped_column(
        ForeignKey("case.id", ondelete="CASCADE"), nullable=False)
    author_id: Mapped[int | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())


class CaseEvent(Base):
    __tablename__ = "case_event"
    __table_args__ = (Index("ix_case_event_case", "case_id", "at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    case_id: Mapped[int] = mapped_column(
        ForeignKey("case.id", ondelete="CASCADE"), nullable=False)
    actor: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
