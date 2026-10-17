"""Aggregation SQL behind core/insights/sentiment.py."""
from ._util import SAFE_SQL, _sf, rows


def breakdown_rows(session, ws, surface=None):
    sfrag, sp = _sf(surface)
    return rows(session, """
        SELECT b.id, b.name, b.is_focus,
               SUM(CASE WHEN s.label='pos' THEN 1 ELSE 0 END),
               SUM(CASE WHEN s.label='neu' THEN 1 ELSE 0 END),
               SUM(CASE WHEN s.label='neg' THEN 1 ELSE 0 END),
               SUM(CASE WHEN s.label='not_scored' THEN 1 ELSE 0 END),
               SUM(CASE WHEN s.mention_id IS NULL AND i.lang_guess='en' THEN 1 ELSE 0 END)
        FROM brand b
        JOIN mention m ON m.brand_id=b.id
        JOIN item i ON i.id=m.item_id
        LEFT JOIN sentiment s ON s.mention_id=m.id
        WHERE b.workspace_id=? AND b.active=1 AND m.excluded=0 AND m.hidden=0
              AND i.source_kind IN """ + SAFE_SQL + sfrag + """
        GROUP BY b.id ORDER BY b.is_focus DESC, 4+5+6 DESC""", ws, *sp)


def focus_scored_rows(session, ws):
    """(published_at, label) for scored English focus-brand mentions."""
    return rows(session, """
        SELECT i.published_at, s.label FROM mention m JOIN item i ON i.id=m.item_id
        JOIN brand b ON b.id=m.brand_id JOIN sentiment s ON s.mention_id=m.id
        WHERE b.workspace_id=? AND b.is_focus=1 AND m.excluded=0 AND m.hidden=0
              AND s.label IN ('pos','neu','neg') AND i.source_kind IN """ + SAFE_SQL, ws)
