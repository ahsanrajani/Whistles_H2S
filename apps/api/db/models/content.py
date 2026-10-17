"""``content_item`` / ``content_event`` — the P4.6 content calendar. A planned
post moves draft → in_review → approved → scheduled → published (or rejected);
``content_event`` is the append-only approval trail."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class ContentItem(Base):
    __tablename__ = "content_item"
    __table_args__ = (
        Index("ix_content_item_ws_when", "workspace_id", "scheduled_for"),
        Index("ix_content_item_ws_state", "workspace_id", "state"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    channel: Mapped[str | None] = mapped_column(Text)
    media: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    state: Mapped[str] = mapped_column(Text, nullable=False, server_default="draft")
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"))
    assigned_to: Mapped[int | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"))
    approved_by: Mapped[int | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outbound_action_id: Mapped[int | None] = mapped_column(
        ForeignKey("outbound_action.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())


class ContentEvent(Base):
    __tablename__ = "content_event"
    __table_args__ = (
        Index("ix_content_event_item", "content_id", "at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    content_id: Mapped[int] = mapped_column(
        ForeignKey("content_item.id", ondelete="CASCADE"), nullable=False)
    actor: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
