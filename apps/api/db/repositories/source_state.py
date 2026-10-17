"""``source_state`` access — the incremental cursor and persisted circuit
breaker per (workspace, source). See ``integrations/adapters/contract.py``."""
from datetime import datetime, timezone

from sqlalchemy import text


def load(session, workspace_id, source) -> dict | None:
    row = session.execute(text("""
        SELECT cursor_kind, cursor_value, circuit_state, consecutive_failures,
               opened_at, last_attempt_at, last_success_at, last_error,
               items_last_run, last_run_id, enabled
        FROM source_state WHERE workspace_id = :ws AND source = :src
    """), {"ws": workspace_id, "src": source}).mappings().first()
    if not row:
        return None
    out = dict(row)
    # circuit-breaker snapshot shape: opened_at as epoch seconds (its clock)
    oa = out.get("opened_at")
    out["opened_at"] = oa.timestamp() if isinstance(oa, datetime) else None
    return out


def save(session, workspace_id, source, **fields) -> None:
    """Upsert the named columns. ``opened_at`` accepts an epoch float (from the
    breaker snapshot) or ``None``; it is stored as timestamptz."""
    if "opened_at" in fields:
        oa = fields["opened_at"]
        fields["opened_at"] = (datetime.fromtimestamp(oa, timezone.utc)
                               if isinstance(oa, (int, float)) else None)
    cols = list(fields)
    insert_cols = ", ".join(["workspace_id", "source", *cols, "updated_at"])
    insert_vals = ", ".join([":ws", ":src", *[f":{c}" for c in cols], "now()"])
    updates = ", ".join([f"{c} = EXCLUDED.{c}" for c in cols] + ["updated_at = now()"])
    session.execute(text(f"""
        INSERT INTO source_state ({insert_cols}) VALUES ({insert_vals})
        ON CONFLICT (workspace_id, source) DO UPDATE SET {updates}
    """), {"ws": workspace_id, "src": source, **fields})


def all_for_workspace(session, workspace_id):
    return session.execute(text("""
        SELECT source, cursor_kind, cursor_value, circuit_state,
               consecutive_failures, opened_at, last_attempt_at,
               last_success_at, last_error, items_last_run, last_run_id, enabled
        FROM source_state WHERE workspace_id = :ws ORDER BY source
    """), {"ws": workspace_id}).mappings().all()


def set_enabled(session, workspace_id, source, enabled: bool) -> None:
    """Turn a collection source on/off for one workspace. Upserts the row so it
    works before the source has ever run. Caller commits."""
    session.execute(text("""
        INSERT INTO source_state (workspace_id, source, enabled, updated_at)
        VALUES (:ws, :src, :enabled, now())
        ON CONFLICT (workspace_id, source)
        DO UPDATE SET enabled = EXCLUDED.enabled, updated_at = now()
    """), {"ws": workspace_id, "src": source, "enabled": bool(enabled)})
