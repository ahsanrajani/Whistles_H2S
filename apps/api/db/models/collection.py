"""Operational tables: ``api_key`` (credential store), ``call_log`` (measured
spend), ``surface_status`` (per-run coverage ledger) and ``run`` (a collection)."""
from sqlalchemy import (Float, ForeignKey, Index, Integer, Text, UniqueConstraint,
                        text)
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class ApiKey(Base):
    __tablename__ = "api_key"
    __table_args__ = (
        UniqueConstraint("workspace_id", "env_var", name="workspace_id_env_var"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # 0 = shared / environment-backed
    workspace_id: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    env_var: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[str | None] = mapped_column(Text)
    # missing | present | verified | failed
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'missing'"))
    last_checked: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)


class CallLog(Base):
    __tablename__ = "call_log"
    __table_args__ = (Index("ix_call_log_workspace_id", "workspace_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(Text, nullable=False)
    workspace_id: Mapped[int | None] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(Text, nullable=False)
    calls: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    units: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    unit_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    ok: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    at: Mapped[str] = mapped_column(Text, nullable=False)


class SurfaceStatus(Base):
    __tablename__ = "surface_status"

    run_id: Mapped[str] = mapped_column(Text, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    surface: Mapped[str] = mapped_column(Text, primary_key=True)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    n_sources: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    estimable: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    note: Mapped[str | None] = mapped_column(Text)


class Run(Base):
    __tablename__ = "run"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    workspace_id: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[str] = mapped_column(Text, nullable=False)
    finished_at: Mapped[str | None] = mapped_column(Text)
    # running | done | failed
    state: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'running'"))
    progress: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'[]'"))
    new_items: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
