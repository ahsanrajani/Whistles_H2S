"""``api_key`` table access — the per-workspace / shared credential store."""
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..models import ApiKey


def shared_values(session):
    """{env_var: value} for the shared (workspace 0) rows that have a value."""
    return {var: val for var, val in session.execute(
        select(ApiKey.env_var, ApiKey.value).where(ApiKey.workspace_id == 0)) if val}


def workspace_values(session, workspace_id):
    """{env_var: value} for one workspace's rows that have a value."""
    return {var: val for var, val in session.execute(
        select(ApiKey.env_var, ApiKey.value).where(ApiKey.workspace_id == workspace_id)) if val}


def shared_rows(session):
    """(env_var, label, value, status, note) for every shared row, id order."""
    rows = session.execute(
        select(ApiKey.env_var, ApiKey.label, ApiKey.value, ApiKey.status, ApiKey.note)
        .where(ApiKey.workspace_id == 0).order_by(ApiKey.id)).all()
    return [tuple(r) for r in rows]


def configured_vars(session, workspace_id):
    """env_vars for a workspace that have a non-NULL value."""
    return {r[0] for r in session.execute(
        select(ApiKey.env_var)
        .where(ApiKey.workspace_id == workspace_id, ApiKey.value.is_not(None)))}


def upsert(session, *, workspace_id, env_var, label, value, status, last_checked):
    session.execute(
        pg_insert(ApiKey.__table__)
        .values(workspace_id=workspace_id, env_var=env_var, label=label,
                value=value, status=status, last_checked=last_checked)
        .on_conflict_do_update(
            index_elements=["workspace_id", "env_var"],
            set_=dict(value=value, status=status, last_checked=last_checked)))


def seed_shared(session, *, env_var, label, value, status):
    """First-boot insert of a shared row; no-op if it already exists."""
    session.execute(
        pg_insert(ApiKey.__table__)
        .values(workspace_id=0, env_var=env_var, label=label, value=value, status=status)
        .on_conflict_do_nothing())
