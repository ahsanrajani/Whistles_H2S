"""RBAC read layer — roles, the permission catalogue, and effective checks.

Permissions are ``(area, verb)`` pairs. ``has_permission`` and
``permissions_for_roles`` take a list of role keys (a user's roles) and answer
against the union of their grants.
"""
from sqlalchemy import select

from ..models import Permission, Role, RolePermission, UserRole


def roles_for_user(session, user_id):
    """Sorted list of role keys held by a user (via ``user_role``)."""
    rows = session.execute(
        select(UserRole.role_key).where(UserRole.user_id == user_id)
        .order_by(UserRole.role_key)).scalars().all()
    return list(rows)


def permissions_for_roles(session, role_keys):
    """Set of ``(area, verb)`` granted to *any* of ``role_keys``."""
    if not role_keys:
        return set()
    rows = session.execute(
        select(Permission.area, Permission.verb)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(RolePermission.role_key.in_(list(role_keys)))).all()
    return {(area, verb) for area, verb in rows}


def has_permission(session, role_keys, area, verb):
    """True if any of ``role_keys`` grants ``(area, verb)``."""
    if not role_keys:
        return False
    return session.execute(
        select(RolePermission.role_key)
        .join(Permission, Permission.id == RolePermission.permission_id)
        .where(RolePermission.role_key.in_(list(role_keys)),
               Permission.area == area, Permission.verb == verb)
        .limit(1)).first() is not None


def set_user_roles(session, user_id, role_keys):
    """Replace a user's role set. Caller commits."""
    session.execute(UserRole.__table__.delete().where(UserRole.user_id == user_id))
    for key in dict.fromkeys(role_keys):          # de-dup, keep order
        session.execute(UserRole.__table__.insert().values(
            user_id=user_id, role_key=key))


def catalogue(session):
    """``{"roles": [(key,label,rank)], "matrix": {role_key: [[area,verb], …]}}`` —
    for an admin UI and the P1.5b test matrix."""
    roles = [tuple(r) for r in session.execute(
        select(Role.key, Role.label, Role.rank).order_by(Role.rank)).all()]
    grants = session.execute(
        select(RolePermission.role_key, Permission.area, Permission.verb)
        .join(Permission, Permission.id == RolePermission.permission_id)).all()
    matrix = {}
    for role_key, area, verb in grants:
        matrix.setdefault(role_key, []).append([area, verb])
    return {"roles": roles, "matrix": matrix}
