"""``job`` — the Postgres-backed work queue (build plan §1).

Workers claim rows with ``FOR UPDATE SKIP LOCKED`` (see ``jobs/queue.py``), run
the handler registered for ``kind``, then mark the row ``done`` or, on failure,
back off and requeue — up to ``max_attempts``, after which it goes ``dead``
(the dead-letter state). A ``running`` row whose ``locked_at`` is older than the
reclaim window is treated as abandoned (the worker died) and re-claimed.
"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class Job(Base):
    __tablename__ = "job"
    __table_args__ = (
        # partial indexes matching the two claim predicates
        Index("ix_job_queued", "run_after", postgresql_where=text("state = 'queued'")),
        Index("ix_job_running", "locked_at", postgresql_where=text("state = 'running'")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    # queued | running | done | failed | dead
    state: Mapped[str] = mapped_column(Text, nullable=False, server_default="queued")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="5")
    run_after: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
    locked_by: Mapped[str | None] = mapped_column(Text)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict | None] = mapped_column(JSONB)
    tenant_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
