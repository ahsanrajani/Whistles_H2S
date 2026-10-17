"""``audit_event`` table access — insert + read only; the table is immutable at
the database level (Alembic ``0007`` trigger)."""
from ..models import AuditEvent


def record(session, *, actor, tenant_id, action, target, at,
           before=None, after=None, ip=None):
    """Insert one audit row (``before`` / ``after`` are JSON strings). Caller commits."""
    session.execute(
        AuditEvent.__table__.insert().values(
            actor=None if actor is None else str(actor),
            tenant_id=tenant_id,
            action=action,
            target=None if target is None else str(target),
            before_state=before,
            after_state=after,
            ip=ip,
            at=at))


def for_tenant(session, tenant_id):
    """All rows for a workspace, newest first."""
    return session.execute(
        AuditEvent.__table__.select()
        .where(AuditEvent.tenant_id == tenant_id)
        .order_by(AuditEvent.id.desc())).fetchall()


def by_action(session, action):
    """All rows for an action, newest first — tests / an admin timeline view."""
    return session.execute(
        AuditEvent.__table__.select()
        .where(AuditEvent.action == action)
        .order_by(AuditEvent.id.desc())).fetchall()
