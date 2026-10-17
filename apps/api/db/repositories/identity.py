"""``identity`` table access — external logins (Google, …) linked to a user."""
from sqlalchemy import select

from ..models import Identity


def by_provider_subject(session, provider, subject):
    """(id, user_id, email) for a linked identity, or None."""
    row = session.execute(
        select(Identity.id, Identity.user_id, Identity.email)
        .where(Identity.provider == provider, Identity.subject == subject)).first()
    return tuple(row) if row else None


def link(session, *, provider, subject, user_id, email, created_at):
    """Create the provider↔user link. Caller commits."""
    session.add(Identity(provider=provider, subject=subject, user_id=user_id,
                         email=email, created_at=created_at, last_login_at=created_at))
    session.flush()


def touch_login(session, identity_id, at):
    session.execute(
        Identity.__table__.update()
        .where(Identity.id == identity_id).values(last_login_at=at))


def for_user(session, user_id):
    """[(provider, email, last_login_at), …] — the identities linked to a user."""
    return [tuple(r) for r in session.execute(
        select(Identity.provider, Identity.email, Identity.last_login_at)
        .where(Identity.user_id == user_id)
        .order_by(Identity.provider)).all()]
