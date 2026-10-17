"""Aggregation SQL behind core/insights/reviews.py."""
from ._util import SAFE_SQL, rows


# One eligible item, regardless of how many brands it mentions. Headline store
# ratings are a different population and must never enter these sample queries.
REVIEW_SCOPE = """
    i.workspace_id = ? AND i.surface = 'app_reviews' AND i.rating BETWEEN 1 AND 5
    AND i.source_kind IN """ + SAFE_SQL + """
    AND NOT EXISTS (SELECT 1 FROM dupe_edge d WHERE d.item_id = i.id)
    AND EXISTS (
        SELECT 1 FROM mention m JOIN brand b ON b.id = m.brand_id
        WHERE m.item_id = i.id AND b.workspace_id = i.workspace_id
          AND b.is_focus = 1 AND b.active = 1 AND m.excluded = 0 AND m.hidden = 0
    )
"""


def scorecard_rows(session, ws):
    """(outlet, rating, published_at, text, url, raw_json) for every 1–5★ review, newest first."""
    return rows(session, """
        SELECT i.outlet, i.rating, i.published_at, COALESCE(i.title, i.body), i.url, i.raw_json
        FROM item i WHERE """ + REVIEW_SCOPE + """
        ORDER BY i.published_at DESC, i.id DESC""", ws)


def rating_rows(session, ws):
    """(published_at, rating) for every 1–5★ review."""
    return rows(session, """
        SELECT i.published_at, i.rating FROM item i WHERE """ + REVIEW_SCOPE, ws)
