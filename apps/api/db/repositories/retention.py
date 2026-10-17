"""``tenant_retention_policy`` access (P2.4). Per (workspace, source_class)
retention_mode — ``full`` (keep author name + profile URL) or ``hashed`` (keep
only the salted identity hash)."""
from sqlalchemy import text

CLASSES = ("official", "third_party")
MODES = ("full", "hashed")


def policy(session, workspace_id) -> dict:
    """``{source_class: retention_mode}`` — defaults to ``full`` for any class
    with no explicit row."""
    rows = session.execute(text(
        "SELECT source_class, retention_mode FROM tenant_retention_policy "
        "WHERE workspace_id = :ws"), {"ws": workspace_id}).all()
    out = {cls: "full" for cls in CLASSES}
    out.update({cls: mode for cls, mode in rows})
    return out


def set_mode(session, workspace_id, source_class, mode) -> None:
    if source_class not in CLASSES or mode not in MODES:
        raise ValueError(f"bad retention policy: {source_class}={mode}")
    session.execute(text("""
        INSERT INTO tenant_retention_policy (workspace_id, source_class, retention_mode)
        VALUES (:ws, :cls, :mode)
        ON CONFLICT (workspace_id, source_class)
        DO UPDATE SET retention_mode = EXCLUDED.retention_mode, updated_at = now()
    """), {"ws": workspace_id, "cls": source_class, "mode": mode})
