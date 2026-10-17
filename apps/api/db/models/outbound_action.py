"""``outbound_action`` — every write to an external platform (build plan §5 / P3.1)."""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class OutboundAction(Base):
    __tablename__ = "outbound_action"
    __table_args__ = (
        Index("ix_outbound_action_ws", "workspace_id", "created_at"),
        Index("ix_outbound_action_rework", "workspace_id",
              postgresql_where=text("state = 'rejected'")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False)
    platform: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    target_ref: Mapped[str | None] = mapped_column(Text)
    request: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    response: Mapped[dict | None] = mapped_column(JSONB)
    external_id: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    error: Mapped[str | None] = mapped_column(Text)
    actor: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
