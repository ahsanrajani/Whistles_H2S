"""``workspace`` table access."""
from sqlalchemy import func, select

from ..models import Workspace


def exists(session, workspace_id):
    return session.execute(
        select(Workspace.id).where(Workspace.id == workspace_id)).first() is not None


def first_id(session):
    row = session.execute(
        select(Workspace.id).order_by(Workspace.id).limit(1)).first()
    return row[0] if row else None


def id_by_name(session, name):
    row = session.execute(select(Workspace.id).where(Workspace.name == name)).first()
    return row[0] if row else None


def name(session, workspace_id):
    row = session.execute(
        select(Workspace.name).where(Workspace.id == workspace_id)).first()
    return row[0] if row else None


def volume_scenario(session, workspace_id):
    row = session.execute(
        select(Workspace.volume_scenario).where(Workspace.id == workspace_id)).first()
    return row[0] if row else None


def any_exists(session):
    return session.execute(select(Workspace.id).limit(1)).first() is not None


def slug_taken(session, slug):
    return session.execute(
        select(Workspace.id).where(Workspace.slug == slug)).first() is not None


def summary(session, workspace_id):
    """(id, name, market, onboarding_step, slug) or None."""
    row = session.execute(
        select(Workspace.id, Workspace.name, Workspace.market,
               Workspace.onboarding_step, Workspace.slug)
        .where(Workspace.id == workspace_id)).first()
    return tuple(row) if row else None


def list_summaries(session):
    rows = session.execute(
        select(Workspace.id, Workspace.name, Workspace.market,
               Workspace.onboarding_step, Workspace.slug)
        .order_by(Workspace.name)).all()
    return [tuple(r) for r in rows]


def list_admin(session):
    """(id, name, market, volume_scenario) for every workspace, id order."""
    rows = session.execute(
        select(Workspace.id, Workspace.name, Workspace.market, Workspace.volume_scenario)
        .order_by(Workspace.id)).all()
    return [tuple(r) for r in rows]


def wizard_row(session, workspace_id):
    """(id, name, market, volume_scenario, sentiment_langs, onboarding_step) or None."""
    row = session.execute(
        select(Workspace.id, Workspace.name, Workspace.market, Workspace.volume_scenario,
               Workspace.sentiment_langs, Workspace.onboarding_step)
        .where(Workspace.id == workspace_id)).first()
    return tuple(row) if row else None


def create(session, *, name, slug=None, market="PK", volume_scenario="mid",
           sentiment_langs="en", onboarding_step=0, created_at):
    """Insert a workspace (no-op on name conflict) and return its id."""
    existing = id_by_name(session, name)
    if existing is not None:
        return existing
    ws = Workspace(name=name, slug=slug, market=market, volume_scenario=volume_scenario,
                   sentiment_langs=sentiment_langs, onboarding_step=onboarding_step,
                   created_at=created_at)
    session.add(ws)
    session.flush()
    return ws.id


def update_settings(session, workspace_id, *, market, volume_scenario, sentiment_langs):
    session.execute(
        Workspace.__table__.update().where(Workspace.id == workspace_id)
        .values(market=market, volume_scenario=volume_scenario,
                sentiment_langs=sentiment_langs))


def bump_onboarding_step(session, workspace_id, step):
    """Raise onboarding_step to at least `step` (never lower it)."""
    session.execute(
        Workspace.__table__.update().where(Workspace.id == workspace_id)
        .values(onboarding_step=func.greatest(Workspace.onboarding_step, step)))


def set_onboarding_step(session, workspace_id, step):
    session.execute(
        Workspace.__table__.update().where(Workspace.id == workspace_id)
        .values(onboarding_step=step))
