"""``scheduled_task`` — recurring schedules the scheduler drains (build plan §1).

``jobs/scheduler.py`` ticks once a minute: for every enabled row whose
``next_run`` has passed it enqueues ``kind`` onto ``job`` and advances
``next_run`` off ``cron``. The scheduler only enqueues; the work runs in
``jobs/worker.py``.
"""
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class ScheduledTask(Base):
    __tablename__ = "scheduled_task"
    __table_args__ = (
        Index("uq_scheduled_task_name", "name", unique=True),
        Index("ix_scheduled_task_due", "next_run",
              postgresql_where=text("enabled = 1")),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    cron: Mapped[str] = mapped_column(Text, nullable=False)
    tenant_id: Mapped[int | None] = mapped_column(Integer)
    # 1 = enabled, 0 = paused (Integer flag, matching user.active / workspace.active)
    enabled: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    # 1 = one-shot: the scheduler disables it after it fires (P3.3 SLA timers)
    once: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_run: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_run: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
