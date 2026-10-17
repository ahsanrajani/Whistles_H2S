"""``project`` — the unit the ``/t/{tenant}/p/{project}/…`` URL addresses
(frontend F0.1). A workspace's listening surfaces are one ``listening``
project; a Vantage site will be another project in the same workspace."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class Project(Base):
    __tablename__ = "project"
    __table_args__ = (
        UniqueConstraint("workspace_id", "slug", name="uq_project_ws_slug"),
        Index("ix_project_ws", "workspace_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False, server_default="listening")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
