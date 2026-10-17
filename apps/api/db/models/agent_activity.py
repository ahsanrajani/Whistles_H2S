"""``agent_activity`` — append-only care-agent shift events (build plan §6 /
P4.3). ``kind`` is one of login / logout / ready / not_ready / idle / active."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class AgentActivity(Base):
    __tablename__ = "agent_activity"
    __table_args__ = (
        Index("ix_agent_activity_ws_user_at", "workspace_id", "user_id", "at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
