"""``mention`` and its per-mention annotations: ``sentiment`` (model score),
``mention_class`` (zero-shot type) and ``gold_label`` (human precision label)."""
from sqlalchemy import (Float, ForeignKey, Index, Integer, Text, UniqueConstraint,
                        text)
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class Mention(Base):
    __tablename__ = "mention"
    __table_args__ = (
        UniqueConstraint("item_id", "brand_id", name="item_id_brand_id"),
        Index("ix_mention_workspace_id", "workspace_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("item.id", ondelete="CASCADE"), nullable=False)
    brand_id: Mapped[int] = mapped_column(
        ForeignKey("brand.id", ondelete="CASCADE"), nullable=False)
    workspace_id: Mapped[int | None] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"))
    rule: Mapped[str] = mapped_column(Text, nullable=False)
    needs_review: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    excluded: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    exclude_reason: Mapped[str | None] = mapped_column(Text)
    # admin soft-hide from the client view (reversible)
    hidden: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))


class Sentiment(Base):
    __tablename__ = "sentiment"
    __table_args__ = (Index("ix_sentiment_workspace_id", "workspace_id"),)

    mention_id: Mapped[int] = mapped_column(
        ForeignKey("mention.id", ondelete="CASCADE"), primary_key=True)
    workspace_id: Mapped[int | None] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"))
    label: Mapped[str] = mapped_column(Text, nullable=False)   # pos | neu | neg | not_scored
    model_id: Mapped[str] = mapped_column(Text, nullable=False)
    scored_lang: Mapped[str] = mapped_column(Text, nullable=False)
    scored_at: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)            # reason when not_scored


class MentionClass(Base):
    __tablename__ = "mention_class"
    __table_args__ = (Index("ix_mention_class_workspace_id", "workspace_id"),)

    mention_id: Mapped[int] = mapped_column(
        ForeignKey("mention.id", ondelete="CASCADE"), primary_key=True)
    workspace_id: Mapped[int | None] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"))
    category: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    model_id: Mapped[str] = mapped_column(Text, nullable=False)
    classified_at: Mapped[str] = mapped_column(Text, nullable=False)


class GoldLabel(Base):
    __tablename__ = "gold_label"
    __table_args__ = (Index("ix_gold_label_workspace_id", "workspace_id"),)

    mention_id: Mapped[int] = mapped_column(
        ForeignKey("mention.id", ondelete="CASCADE"), primary_key=True)
    workspace_id: Mapped[int | None] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"))
    correct: Mapped[int] = mapped_column(Integer, nullable=False)
    labelled_at: Mapped[str] = mapped_column(Text, nullable=False)
    labelled_by: Mapped[str | None] = mapped_column(Text)
