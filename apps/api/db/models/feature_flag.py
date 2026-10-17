"""``feature_flag`` — per-workspace feature toggles. One row per (workspace,
feature_key) that is turned off; absence means on. Keys are the flat namespace
in ``core/features.py`` (``surface.*`` / ``module.*`` / ``cap.*``)."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class FeatureFlag(Base):
    __tablename__ = "feature_flag"

    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"), primary_key=True)
    feature_key: Mapped[str] = mapped_column(Text, primary_key=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
