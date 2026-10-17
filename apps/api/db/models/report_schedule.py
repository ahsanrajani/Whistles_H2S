"""``report_schedule`` — a saved report + cron + recipients for the P4.9
scheduled email distribution."""
from datetime import datetime

from sqlalchemy import (Boolean, DateTime, ForeignKey, Index, Integer, Text,
                        func)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class ReportSchedule(Base):
    __tablename__ = "report_schedule"
    __table_args__ = (Index("ix_report_schedule_ws", "workspace_id", "active"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    format: Mapped[str] = mapped_column(Text, nullable=False, server_default="pdf")
    params: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    cron: Mapped[str] = mapped_column(Text, nullable=False)
    recipients: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
