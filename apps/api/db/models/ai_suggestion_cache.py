"""``ai_suggestion_cache`` -- the reply suggestion a case's thread already
produced, reused instead of re-asking the model every time an agent opens
(or reopens) the same conversation. Keyed on (case_id, kind) with a cheap
thread fingerprint (message count + last message id); a new inbound/outbound
message changes the fingerprint and the next read regenerates."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class AiSuggestionCache(Base):
    __tablename__ = "ai_suggestion_cache"
    __table_args__ = (Index("ux_ai_suggestion_cache_case_kind", "case_id", "kind", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False)
    case_id: Mapped[int] = mapped_column(
        ForeignKey("case.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    suggestion: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    sources: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    mock: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
