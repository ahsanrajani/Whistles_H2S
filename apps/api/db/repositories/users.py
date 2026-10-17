"""``user`` table access."""
from sqlalchemy import select

from ..models import User


def by_id_active(session, user_id):
    """(id, username, role) for an active user, or None."""
    row = session.execute(
        select(User.id, User.username, User.role)
        .where(User.id == user_id, User.active == 1)).first()
    return tuple(row) if row else None


def auth_row(session, username):
    """(id, password_hash, role, workspace_id) for an active user, or None."""
    row = session.execute(
        select(User.id, User.password_hash, User.role, User.workspace_id)
        .where(User.username == username, User.active == 1)).first()
    return tuple(row) if row else None


def by_email(session, email):
    """(id, username, role, workspace_id) for an active user with this email,
    or None. Used to match a federated (Google) login to an existing account."""
    if not email:
        return None
    row = session.execute(
        select(User.id, User.username, User.role, User.workspace_id)
        .where(User.email == email, User.active == 1)).first()
    return tuple(row) if row else None


def login_row(session, user_id):
    """(id, username, role, workspace_id) for an active user by id, or None."""
    row = session.execute(
        select(User.id, User.username, User.role, User.workspace_id)
        .where(User.id == user_id, User.active == 1)).first()
    return tuple(row) if row else None


def home_workspace_id(session, user_id):
    """The workspace a user is pinned to (0/NULL -> None)."""
    row = session.execute(
        select(User.workspace_id).where(User.id == user_id)).first()
    return row[0] if row and row[0] else None


def exists(session, username):
    return session.execute(
        select(User.id).where(User.username == username)).first() is not None


def list_with_workspace(session):
    """[(id, username, role, active, workspace_name, workspace_id), …]
    ordered by role, username."""
    from ..models import Workspace
    rows = session.execute(
        select(User.id, User.username, User.role, User.active, Workspace.name,
              User.workspace_id)
        .outerjoin(Workspace, Workspace.id == User.workspace_id)
        .order_by(User.role, User.username)).all()
    return [tuple(r) for r in rows]


def get(session, user_id):
    """(id, username, role, active, workspace_id), or None."""
    row = session.execute(
        select(User.id, User.username, User.role, User.active, User.workspace_id)
        .where(User.id == user_id)).first()
    return tuple(row) if row else None


def update_access(session, user_id, *, role, workspace_id):
    """Change a user's role and/or workspace pin (admin "Edit access")."""
    session.execute(
        User.__table__.update().where(User.id == user_id)
        .values(role=role, workspace_id=workspace_id))


def set_active(session, user_id, active: bool):
    session.execute(
        User.__table__.update().where(User.id == user_id).values(active=1 if active else 0))


def set_password_by_id(session, user_id, password_hash):
    session.execute(
        User.__table__.update().where(User.id == user_id)
        .values(password_hash=password_hash))


def has_activity(session, user_id) -> bool:
    """True if this user has done anything real: assigned a case, written a
    note, worked a shift, authored KB/template/content, scheduled a report.
    Checked in Python, not left to the schema -- every FK onto user.id is
    ON DELETE SET NULL/CASCADE (a user can genuinely be removed without
    breaking anything), so a hard delete() would otherwise silently succeed
    for an agent with a real history and null out/cascade away their
    attribution. Deliberately does not look at free-text ``actor`` columns
    (case_event, outbound_action, audit_log — never a real FK, just a
    stringified id/username) -- those are an audit trail, not a delete
    guard, and stay pointing at the id even for a genuinely-gone user."""
    from sqlalchemy import text as _t
    row = session.execute(_t("""
        SELECT EXISTS (
            SELECT 1 FROM "case" WHERE assignee_id = :u
            UNION ALL SELECT 1 FROM case_note WHERE author_id = :u
            UNION ALL SELECT 1 FROM agent_activity WHERE user_id = :u
            UNION ALL SELECT 1 FROM content_item
                WHERE created_by = :u OR assigned_to = :u OR approved_by = :u
            UNION ALL SELECT 1 FROM report_schedule WHERE created_by = :u
            UNION ALL SELECT 1 FROM kb_article WHERE created_by = :u
            UNION ALL SELECT 1 FROM care_template WHERE created_by = :u
        )"""), {"u": user_id}).scalar()
    return bool(row)


def delete(session, user_id):
    """Hard-delete. Caller's job to check has_activity() first (or catch
    IntegrityError, kept as a defensive fallback in case a future migration
    adds a real RESTRICT FK) -- use set_active(False) (Deactivate) for an
    account with real history instead."""
    session.execute(User.__table__.delete().where(User.id == user_id))


def create(session, *, username, password_hash, role, workspace_id=None,
           created_at, email=None):
    """Insert a user; no-op (returns None) if the username already exists.
    Returns the new user's id otherwise."""
    if exists(session, username):
        return None
    user = User(username=username, password_hash=password_hash, role=role,
               workspace_id=workspace_id, created_at=created_at,
               email=(email or None))
    session.add(user)
    session.flush()
    return user.id


def set_password(session, username, password_hash):
    session.execute(
        User.__table__.update().where(User.username == username)
        .values(password_hash=password_hash))


def assign_default_workspace(session, workspace_id):
    """Pin every unpinned viewer to `workspace_id`."""
    session.execute(
        User.__table__.update()
        .where(User.role == "bank_viewer", User.workspace_id.is_(None))
        .values(workspace_id=workspace_id))
