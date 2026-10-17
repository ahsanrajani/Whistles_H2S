"""``seo_suggestion`` -- LLM-generated SEO recommendations (Vantage's SEO
tab). Human-triggered only, like the AI-visibility panel and the crawl/
keyword runs -- every call costs real money. Grounded only in the real
crawl/CWV/keyword/backlink/search-visibility facts already on file; the raw
model response is kept alongside the parsed list so a reviewer can see
exactly what the model was given and said."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class SeoSuggestion(Base):
    __tablename__ = "seo_suggestion"
    __table_args__ = (Index("ix_seo_suggestion_ws", "workspace_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    suggestions: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
