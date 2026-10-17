"""``location`` — a workspace's physical points of presence: branches, offices
and ATMs. Per-tenant (the branch catalogue used to be a hard-coded Bank Alfalah
PoC in ``core/branches.py``). ``lat`` / ``lng`` / ``place_id`` are NULL until
known -- never guessed; ``source`` says where the row came from."""
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class Location(Base):
    __tablename__ = "location"
    __table_args__ = (
        Index("uq_location_ws_key", "workspace_id", "key", unique=True),
        Index("ix_location_ws_kind", "workspace_id", "kind"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False)
    key: Mapped[str] = mapped_column(Text, nullable=False)       # stable slug
    kind: Mapped[str] = mapped_column(Text, nullable=False, server_default="branch")  # branch|office|atm
    name: Mapped[str] = mapped_column(Text, nullable=False)
    city: Mapped[str | None] = mapped_column(Text)
    region: Mapped[str | None] = mapped_column(Text)
    address: Mapped[str | None] = mapped_column(Text)
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    place_id: Mapped[str | None] = mapped_column(Text)           # Google Place id
    # How lat/lng was obtained: supplied (client), address (full-address geocode),
    # street, area (coarser -- a neighbourhood pin, not the door). NULL = no coords.
    geo_precision: Mapped[str | None] = mapped_column(Text)
    # The listing's own overall rating + review count (NULL = not captured).
    rating: Mapped[float | None] = mapped_column(Float)
    review_count: Mapped[int | None] = mapped_column(Integer)
    rating_source: Mapped[str | None] = mapped_column(Text)
    rating_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default="manual")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
