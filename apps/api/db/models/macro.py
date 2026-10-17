"""Auto macros (0035): a rule runs a ``care_template`` macro against a case when
any of its triggers fires; ``care_macro_run`` is the once-per-case guard."""
from datetime import datetime

from sqlalchemy import (BigInteger, Boolean, DateTime, ForeignKey, Index, Integer,
                        Text, UniqueConstraint, func, true)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class CareMacroRule(Base):
    __tablename__ = "care_macro_rule"
    __table_args__ = (Index("ix_care_macro_rule_ws", "workspace_id", "active"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False)
    macro_id: Mapped[int] = mapped_column(
        ForeignKey("care_template.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=true())
    triggers: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    filters: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    reply_mode: Mapped[str] = mapped_column(Text, nullable=False, server_default="hold")
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
    last_fired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CareMacroRun(Base):
    __tablename__ = "care_macro_run"
    __table_args__ = (
        UniqueConstraint("rule_id", "case_id", name="uq_care_macro_run_rule_case"),
        Index("ix_care_macro_run_ws", "workspace_id", "fired_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False)
    rule_id: Mapped[int] = mapped_column(
        ForeignKey("care_macro_rule.id", ondelete="CASCADE"), nullable=False)
    case_id: Mapped[int] = mapped_column(
        ForeignKey("case.id", ondelete="CASCADE"), nullable=False)
    trigger: Mapped[str] = mapped_column(Text, nullable=False)
    result: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    fired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
