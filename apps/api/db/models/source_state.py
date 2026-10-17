"""``source_state`` — per (workspace, source) incremental cursor + circuit
breaker state (build plan §4 / P2.2). P2.3 adds the source-health columns."""
from datetime import datetime

from sqlalchemy import (Boolean, DateTime, ForeignKey, Index, Integer, Text, func,
                        text)
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class SourceState(Base):
    __tablename__ = "source_state"
    __table_args__ = (
        Index("ix_source_state_open", "opened_at",
              postgresql_where=text("circuit_state = 'open'")),
    )

    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"), primary_key=True)
    source: Mapped[str] = mapped_column(Text, primary_key=True)
    cursor_kind: Mapped[str] = mapped_column(Text, nullable=False, server_default="none")
    cursor_value: Mapped[str | None] = mapped_column(Text)
    circuit_state: Mapped[str] = mapped_column(Text, nullable=False, server_default="closed")
    # per-workspace opt-out: false = this workspace does not collect this source
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"))
    consecutive_failures: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"))
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    # source health (P2.3)
    items_last_run: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"))
    last_run_id: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
