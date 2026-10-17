"""``item`` (one collected record) and ``dupe_edge`` (fold a re-collection onto
its canonical item)."""
from sqlalchemy import (BigInteger, ForeignKey, Index, Integer, Text,
                        UniqueConstraint, text)
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class Item(Base):
    __tablename__ = "item"
    __table_args__ = (
        UniqueConstraint("workspace_id", "source", "external_id",
                         name="workspace_id_source_external_id"),
        Index("idx_item_ws", "workspace_id", "surface", "published_at"),
        Index("idx_item_hash", "workspace_id", "content_hash"),
        Index("ix_item_simhash", "workspace_id", "simhash",
              postgresql_where=text("simhash IS NOT NULL AND simhash <> 0")),
        Index("ix_item_author_id", "author_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False)
    surface: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    source_kind: Mapped[str] = mapped_column(Text, nullable=False)
    external_id: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    outlet: Mapped[str | None] = mapped_column(Text)      # publisher / subreddit / channel
    author: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    lang_guess: Mapped[str | None] = mapped_column(Text)
    rating: Mapped[int | None] = mapped_column(Integer)   # 1..5 for app-store reviews, else NULL
    sampled: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    collection_run_id: Mapped[str | None] = mapped_column(Text)
    raw_json: Mapped[str] = mapped_column(Text, nullable=False)
    collected_at: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    # 63-bit Charikar SimHash of the normalised text (P2.1). NULL for rows
    # written before the column existed; near-dup dedupe skips those.
    simhash: Mapped[int | None] = mapped_column(BigInteger)
    # P2.4 — normalised author identity + provenance
    author_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("item_author.id", ondelete="SET NULL"))
    source_class: Mapped[str | None] = mapped_column(Text)


class DupeEdge(Base):
    __tablename__ = "dupe_edge"
    __table_args__ = (Index("ix_dupe_edge_workspace_id", "workspace_id"),)

    item_id: Mapped[int] = mapped_column(
        ForeignKey("item.id", ondelete="CASCADE"), primary_key=True)
    canonical_id: Mapped[int] = mapped_column(Integer, nullable=False)
    method: Mapped[str] = mapped_column(Text, nullable=False)
    workspace_id: Mapped[int | None] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"))
