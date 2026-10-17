"""``llm_prompt`` / ``llm_panel_response`` -- the Vantage AI-visibility panel
(build plan §7). A fixed prompt set per workspace, asked of a roster of LLMs;
the raw answer is kept as evidence, plus which brands its text mentions."""
from datetime import date, datetime

from sqlalchemy import (Boolean, Date, DateTime, ForeignKey, Index, Text,
                        func, text)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class LlmPrompt(Base):
    __tablename__ = "llm_prompt"
    __table_args__ = (Index("ix_llm_prompt_ws", "workspace_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False)
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())


class LlmPanelResponse(Base):
    __tablename__ = "llm_panel_response"
    __table_args__ = (Index("ix_llm_panel_response_ws_day", "workspace_id", "day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False)
    prompt_id: Mapped[int] = mapped_column(
        ForeignKey("llm_prompt.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    response_text: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    mentions: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
