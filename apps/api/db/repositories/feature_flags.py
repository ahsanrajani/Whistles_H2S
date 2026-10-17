"""``feature_flag`` access — per-workspace feature toggles.

Only rows that turn something **off** are stored; ``core/features.py`` applies
them over the on-by-default. Every function takes a ``Session`` and leaves the
commit to the caller.
"""
from sqlalchemy import text


def all_for_workspace(session, workspace_id) -> dict:
    """``{feature_key: enabled}`` for whatever rows exist (usually just the
    off ones)."""
    return {r[0]: r[1] for r in session.execute(text(
        "SELECT feature_key, enabled FROM feature_flag WHERE workspace_id = :ws"),
        {"ws": workspace_id})}


def set_enabled(session, workspace_id, feature_key, enabled: bool) -> None:
    """Upsert one flag. Caller commits."""
    session.execute(text("""
        INSERT INTO feature_flag (workspace_id, feature_key, enabled, updated_at)
        VALUES (:ws, :key, :enabled, now())
        ON CONFLICT (workspace_id, feature_key)
        DO UPDATE SET enabled = EXCLUDED.enabled, updated_at = now()
    """), {"ws": workspace_id, "key": feature_key, "enabled": bool(enabled)})
