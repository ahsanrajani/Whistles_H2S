"""``mention`` table writes — visibility toggle and the rematch reset.

Read-side mention analytics live in ``db/analytics/``.
"""
from sqlalchemy import func, select

from ..models import Brand, Mention


def set_hidden(session, mention_id, workspace_id, hidden):
    """Toggle a mention's admin soft-hide, scoped to the workspace's brands.
    Returns the affected row count (0 = not found / wrong workspace)."""
    result = session.execute(
        Mention.__table__.update()
        .where(Mention.id == mention_id,
               Mention.brand_id.in_(
                   select(Brand.id).where(Brand.workspace_id == workspace_id)))
        .values(hidden=1 if hidden else 0))
    return result.rowcount


def delete_for_workspace(session, workspace_id):
    session.execute(
        Mention.__table__.delete().where(
            Mention.brand_id.in_(
                select(Brand.id).where(Brand.workspace_id == workspace_id))))


def count_for_workspace(session, workspace_id):
    return session.execute(
        select(func.count()).select_from(Mention)
        .join(Brand, Brand.id == Mention.brand_id)
        .where(Brand.workspace_id == workspace_id)).scalar_one()
