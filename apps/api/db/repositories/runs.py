"""``run`` table access — one collection run."""
from sqlalchemy import select

from ..models import Run


def latest_done_id(session, workspace_id):
    row = session.execute(
        select(Run.id).where(Run.workspace_id == workspace_id, Run.state == "done")
        .order_by(Run.started_at.desc()).limit(1)).first()
    return row[0] if row else None


def running_id(session, workspace_id=None):
    """The id of a currently-running run, or ``None``. Scoped to
    ``workspace_id`` when given — collection in one workspace must never block
    another's (found via P2.7: Chase's collection tick was starved every cycle
    by Bank Alfalah's run grabbing this as a global lock)."""
    q = select(Run.id).where(Run.state == "running")
    if workspace_id is not None:
        q = q.where(Run.workspace_id == workspace_id)
    row = session.execute(q).first()
    return row[0] if row else None


def state_progress(session, run_id):
    """(state, progress) or None."""
    row = session.execute(
        select(Run.state, Run.progress).where(Run.id == run_id)).first()
    return tuple(row) if row else None


def recent(session, limit=20, workspace_id=None):
    """(id, started_at, finished_at, state, new_items) newest first, scoped to
    ``workspace_id`` when given."""
    q = select(Run.id, Run.started_at, Run.finished_at, Run.state, Run.new_items)
    if workspace_id is not None:
        q = q.where(Run.workspace_id == workspace_id)
    rows = session.execute(q.order_by(Run.started_at.desc()).limit(limit)).all()
    return [tuple(r) for r in rows]


def create(session, *, run_id, workspace_id, started_at):
    session.add(Run(id=run_id, workspace_id=workspace_id, started_at=started_at,
                    state="running"))
    session.flush()


def set_progress(session, run_id, progress_json):
    session.execute(Run.__table__.update().where(Run.id == run_id)
                    .values(progress=progress_json))


def mark_done(session, run_id, *, finished_at, new_items):
    session.execute(Run.__table__.update().where(Run.id == run_id)
                    .values(state="done", finished_at=finished_at, new_items=new_items))


def mark_failed(session, run_id, *, finished_at):
    session.execute(Run.__table__.update().where(Run.id == run_id)
                    .values(state="failed", finished_at=finished_at))
