"""``metric_fact`` — the source-agnostic daily metric warehouse (build plan
§6 / P4.1). Owned social analytics land here; so do non-social measures (rank
tracking, crawl results, LLM prompt panels) in Phase 5, without a schema
change. ``numerator`` / ``denominator`` carry the raw counts behind a
proportion so P4.2 can attach a Wilson interval."""
from datetime import date, datetime

from sqlalchemy import (Date, DateTime, Float, ForeignKey, Index, Integer, Text,
                        func)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class MetricFact(Base):
    __tablename__ = "metric_fact"
    __table_args__ = (
        Index("uq_metric_fact_grain", "workspace_id", "source", "entity_type",
              "entity_ref", "metric", "day", "dim_hash", unique=True),
        Index("ix_metric_fact_lookup", "workspace_id", "source", "metric", "day"),
        Index("ix_metric_fact_entity", "workspace_id", "entity_type",
              "entity_ref", "day"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_ref: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    metric: Mapped[str] = mapped_column(Text, nullable=False)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    value: Mapped[float | None] = mapped_column(Float)
    numerator: Mapped[float | None] = mapped_column(Float)
    denominator: Mapped[float | None] = mapped_column(Float)
    dims: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    dim_hash: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
