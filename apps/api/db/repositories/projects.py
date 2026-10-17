"""``project`` table access (frontend F0.1)."""
from sqlalchemy import text


def ensure_default(session, workspace_id) -> int:
    """The workspace's ``listening`` project, created if absent. Caller commits."""
    row = session.execute(text(
        "SELECT id FROM project WHERE workspace_id = :ws AND slug = 'listening'"),
        {"ws": workspace_id}).first()
    if row:
        return int(row[0])
    return int(session.execute(text("""
        INSERT INTO project (workspace_id, slug, name, kind)
        VALUES (:ws, 'listening', 'Listening', 'listening')
        ON CONFLICT (workspace_id, slug) DO UPDATE SET slug = EXCLUDED.slug
        RETURNING id
    """), {"ws": workspace_id}).scalar_one())


def list_for_workspace(session, workspace_id) -> list[dict]:
    rows = session.execute(text(
        "SELECT id, slug, name, kind FROM project "
        "WHERE workspace_id = :ws ORDER BY (slug <> 'listening'), name"),
        {"ws": workspace_id}).mappings().all()
    return [dict(r) for r in rows]


def get_by_slug(session, workspace_id, slug):
    return session.execute(text(
        "SELECT id, slug, name, kind FROM project "
        "WHERE workspace_id = :ws AND slug = :slug"),
        {"ws": workspace_id, "slug": slug}).mappings().first()
