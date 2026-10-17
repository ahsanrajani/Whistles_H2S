"""Source health (build plan §4 / P2.3).

One row per collector source for a workspace: its last success, last error,
consecutive failures, items on the last run, circuit state — and a computed
``health`` band the admin surface colours and the silence alert reads.

    ok       ran, produced or quietly idle, circuit closed
    stale    no success within 3x its cadence (build plan: "silent beyond 3x")
    failing  1+ consecutive failures but the circuit is still closed
    down     circuit open
    unknown  never attempted (no source_state row yet)

``huggingface_*`` (cadence 0 — inference services, not collectors) are omitted.
"""
from datetime import datetime, timezone

from core import sources
from db.repositories import source_state

_STALE_MULTIPLE = 3
_BAD = ("stale", "failing", "down")


def _band(row: dict, cadence: int, now: datetime) -> str:
    if row is None:
        return "unknown"
    if row["circuit_state"] == "open":
        return "down"
    last_ok = row.get("last_success_at")
    if last_ok is None:
        # attempted but never succeeded
        return "failing" if (row.get("consecutive_failures") or 0) else "stale"
    age = (now - last_ok).total_seconds()
    if cadence and age > _STALE_MULTIPLE * cadence:
        return "stale"
    if (row.get("consecutive_failures") or 0) > 0:
        return "failing"
    return "ok"


def summary(session, workspace_id, *, now=None) -> dict:
    """``{"sources": [...], "unhealthy": [...], "counts": {...}}`` for a workspace."""
    now = now or datetime.now(timezone.utc)
    states = {r["source"]: dict(r)
              for r in source_state.all_for_workspace(session, workspace_id)}

    rows = []
    for sid, meta in sources.SOURCES.items():
        cadence = int(meta.get("cadence", 0))
        if cadence == 0:                       # inference services, not collectors
            continue
        state = states.get(sid)
        band = _band(state, cadence, now)
        last_ok = state.get("last_success_at") if state else None
        rows.append({
            "source": sid,
            "label": meta["label"],
            "surface": meta["surface"],
            "source_class": meta.get("source_class", "third_party"),
            "cadence_seconds": cadence,
            "health": band,
            "circuit_state": (state or {}).get("circuit_state", "closed"),
            "consecutive_failures": (state or {}).get("consecutive_failures", 0),
            "items_last_run": (state or {}).get("items_last_run", 0),
            "last_run_id": (state or {}).get("last_run_id"),
            "last_success_at": last_ok.isoformat() if last_ok else None,
            "last_attempt_at": (state["last_attempt_at"].isoformat()
                                if state and state.get("last_attempt_at") else None),
            "last_error": (state or {}).get("last_error"),
        })

    rows.sort(key=lambda r: (_BAD.index(r["health"]) if r["health"] in _BAD else 9,
                             r["source"]))
    unhealthy = [r for r in rows if r["health"] in _BAD]
    return {
        "sources": rows,
        "unhealthy": unhealthy,
        "counts": {
            "total": len(rows),
            "ok": sum(1 for r in rows if r["health"] == "ok"),
            "unknown": sum(1 for r in rows if r["health"] == "unknown"),
            "down": sum(1 for r in rows if r["health"] == "down"),
            "stale": sum(1 for r in rows if r["health"] == "stale"),
            "failing": sum(1 for r in rows if r["health"] == "failing"),
        },
    }
