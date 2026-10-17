"""``gold_label`` table access — the human precision labels."""
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..models import GoldLabel


def upsert(session, *, workspace_id, mention_id, correct, labelled_at, labelled_by):
    session.execute(
        pg_insert(GoldLabel.__table__)
        .values(mention_id=mention_id, workspace_id=workspace_id, correct=correct,
                labelled_at=labelled_at, labelled_by=labelled_by)
        .on_conflict_do_update(
            index_elements=["mention_id"],
            set_=dict(correct=correct, labelled_at=labelled_at, labelled_by=labelled_by)))
