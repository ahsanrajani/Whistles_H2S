"""``item_author`` and ``tenant_retention_policy`` (build plan §4 / P2.4).

``item_author.author_hash`` is a per-workspace salted hash of the platform
identity; it never changes, so repeat-author detection survives a tenant
switching a source class to ``hashed`` (which nulls ``name`` / ``profile_url``).
"""
from datetime import datetime

from sqlalchemy import (BigInteger, DateTime, ForeignKey, Index, Integer, Text,
                        UniqueConstraint, func)
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class ItemAuthor(Base):
    __tablename__ = "item_author"
    __table_args__ = (
        UniqueConstraint("workspace_id", "author_hash", name="uq_item_author_ws_hash"),
        Index("ix_item_author_ws", "workspace_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False)
    platform: Mapped[str] = mapped_column(Text, nullable=False)
    platform_id: Mapped[str | None] = mapped_column(Text)
    author_hash: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str | None] = mapped_column(Text)          # NULL once hashed
    profile_url: Mapped[str | None] = mapped_column(Text)   # NULL once hashed
    source_class: Mapped[str] = mapped_column(Text, nullable=False, server_default="third_party")
    retention_mode: Mapped[str] = mapped_column(Text, nullable=False, server_default="full")
    first_seen: Mapped[str] = mapped_column(Text, nullable=False)
    last_seen: Mapped[str] = mapped_column(Text, nullable=False)


class TenantRetentionPolicy(Base):
    __tablename__ = "tenant_retention_policy"

    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"), primary_key=True)
    source_class: Mapped[str] = mapped_column(Text, primary_key=True)
    retention_mode: Mapped[str] = mapped_column(Text, nullable=False, server_default="full")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
