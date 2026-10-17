"""``care_agent`` and ``routing_policy`` (build plan §5 / P3.3)."""
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Integer, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class CareAgent(Base):
    __tablename__ = "care_agent"

    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), primary_key=True)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("5"))
    available: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RoutingPolicy(Base):
    __tablename__ = "routing_policy"
    __table_args__ = (CheckConstraint(
        "assign_strategy IN ('manual','round_robin','least_busy','longest_idle')",
        name="ck_routing_policy_assign_strategy"),)

    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"), primary_key=True)
    first_response_sla: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("900"))
    resolution_sla: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("86400"))
    escalation_after: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("3600"))
    default_capacity: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("5"))
    # How a new case is handed to an agent (0036): manual | round_robin | least_busy | longest_idle.
    assign_strategy: Mapped[str] = mapped_column(Text, nullable=False, server_default="least_busy")
    # Auto-assignment only hands out cases with an id above this (0037): the backlog at the
    # moment auto-assign was introduced / the rule last changed stays unassigned. NULL = no floor.
    auto_assign_after_case: Mapped[int | None] = mapped_column(BigInteger)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
