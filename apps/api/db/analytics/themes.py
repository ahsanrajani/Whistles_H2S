"""Text corpus behind core/insights/themes.py."""
from ._util import SAFE_SQL, _sf, rows


def brand_text_rows(session, brand_id, surface=None):
    """(text, sentiment_label) for every client-safe mention of one brand."""
    sfrag, sp = _sf(surface)
    return rows(session, """
        SELECT COALESCE(i.title, i.body),
               (SELECT s.label FROM sentiment s WHERE s.mention_id = m.id)
        FROM mention m JOIN item i ON i.id = m.item_id
        WHERE m.brand_id = ? AND m.excluded = 0 AND m.hidden = 0
              AND i.source_kind IN """ + SAFE_SQL + sfrag, brand_id, *sp)
