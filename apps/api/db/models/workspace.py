"""``workspace`` (one focus brand + its competitor set) and ``brand`` (the
match rules, editable from /admin without a deploy)."""
from sqlalchemy import ForeignKey, Integer, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class Workspace(Base):
    __tablename__ = "workspace"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    slug: Mapped[str | None] = mapped_column(Text)
    market: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'PK'"))
    volume_scenario: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'high'"))
    sentiment_langs: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'en'"))
    # 0 = set up, > 0 = wizard step
    onboarding_step: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[str] = mapped_column(Text, nullable=False)


class Brand(Base):
    __tablename__ = "brand"
    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="workspace_id_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    is_focus: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    safe_patterns: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'[]'"))
    gated_patterns: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'{}'"))
    context_patterns: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'[]'"))
    exclude_patterns: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'[]'"))
    active: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
