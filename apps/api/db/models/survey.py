"""``survey`` / ``survey_response`` — the P4.7 CSAT / NPS / CES module."""
from datetime import datetime

from sqlalchemy import (Boolean, DateTime, ForeignKey, Index, Integer, Text,
                        func)
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class Survey(Base):
    __tablename__ = "survey"
    __table_args__ = (Index("ix_survey_ws_active", "workspace_id", "active"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False, server_default="csat")
    scale_min: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    scale_max: Mapped[int] = mapped_column(Integer, nullable=False, server_default="5")
    question: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="How satisfied were you?")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())


class SurveyResponse(Base):
    __tablename__ = "survey_response"
    __table_args__ = (
        Index("ix_survey_response_ws_time", "workspace_id", "issued_at"),
        Index("ix_survey_response_case", "case_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False)
    survey_id: Mapped[int] = mapped_column(
        ForeignKey("survey.id", ondelete="CASCADE"), nullable=False)
    case_id: Mapped[int | None] = mapped_column(
        ForeignKey("case.id", ondelete="SET NULL"))
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customer.id", ondelete="SET NULL"))
    channel: Mapped[str | None] = mapped_column(Text)
    token: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    score: Mapped[int | None] = mapped_column(Integer)
    comment: Mapped[str | None] = mapped_column(Text)
    bucket: Mapped[str | None] = mapped_column(Text)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
