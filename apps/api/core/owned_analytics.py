"""Owned-analytics ingestion into the metric warehouse (build plan §6 / P4.1).

``ingest`` walks every configured provider for a workspace, pulls one row set
per day over the requested window, and upserts it into ``metric_fact`` — so a
re-run overwrites rather than duplicates. The daily cadence is a per-workspace
``scheduled_task`` (``owned-analytics:<ws>``) registered by
``ensure_workspace_schedule``; ``app.init`` calls it for every workspace and the
``owned_analytics`` worker handler runs it.
"""
from datetime import date, datetime, timedelta, timezone

from db import repositories as repo
from integrations import owned

_INGEST_CRON = "20 3 * * *"          # 03:20 UTC — yesterday's numbers have settled


def ensure_workspace_schedule(session, workspace_id) -> None:
    """Idempotently register the per-workspace daily ingest."""
    repo.scheduled_task.register(
        session, name=f"owned-analytics:{workspace_id}", kind="owned_analytics",
        cron=_INGEST_CRON, payload={"ws": workspace_id}, tenant_id=workspace_id)


def _days(end: date, back: int):
    for i in range(back):
        yield end - timedelta(days=i)


def ingest(session, workspace_id, *, days: int = 1, keys: dict | None = None,
           now: datetime | None = None, platforms=None) -> dict:
    """Pull ``days`` days ending yesterday for each provider and upsert. Returns
    a per-platform count summary. Caller commits."""
    now = now or datetime.now(timezone.utc)
    end = (now - timedelta(days=1)).date()
    keys = keys or {}
    want = set(platforms) if platforms else set(owned.PROVIDERS)

    out: dict = {"window": {"end": end.isoformat(), "days": days}, "platforms": {}}
    total = 0
    for name, cls in owned.PROVIDERS.items():
        if name not in want:
            continue
        provider = cls(keys)
        facts: list[dict] = []
        error = None
        for day in _days(end, days):
            try:
                facts.extend(provider.fetch(workspace_id, day))
            except owned.OwnedAnalyticsError as exc:
                error = str(exc)          # one bad provider must not stop the rest
                break
        written = repo.metric_fact.upsert_many(session, workspace_id, facts)
        total += written
        entry = {"facts": written, "mock": provider.is_mock(),
                 "live": provider.is_live()}
        if error:
            entry["error"] = error
        out["platforms"][name] = entry
    out["facts"] = total
    return out


def status(session, workspace_id) -> dict:
    """Per-source ingestion state for the admin surface."""
    rows = repo.metric_fact.summary(session, workspace_id)
    configured = {
        name: not cls().is_mock() for name, cls in owned.PROVIDERS.items()
    }
    return {
        "sources": [
            {"source": r["source"], "facts": r["facts"],
             "first_day": r["first_day"].isoformat() if r["first_day"] else None,
             "last_day": r["last_day"].isoformat() if r["last_day"] else None,
             "metrics": r["metrics"],
             "last_captured_at": r["last_captured_at"].isoformat()
             if r["last_captured_at"] else None}
            for r in rows
        ],
        "providers": [
            {"platform": name, "live": live} for name, live in configured.items()
        ],
    }
