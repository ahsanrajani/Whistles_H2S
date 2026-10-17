"""Aggregation SQL behind core/insights/competitors.py."""
from ._util import SAFE_SQL, _sf, rows


def share_of_voice_rows(session, ws, surface=None):
    sfrag, sp = _sf(surface)
    return rows(session, """
        SELECT b.id, b.name, b.is_focus,
               SUM(CASE WHEN m.excluded=0 AND m.hidden=0 AND i.source_kind IN """ + SAFE_SQL + sfrag + """ THEN 1 ELSE 0 END) AS n,
               SUM(CASE WHEN m.excluded=0 AND m.hidden=0 AND m.needs_review=1 AND i.source_kind IN """ + SAFE_SQL + sfrag + """ THEN 1 ELSE 0 END),
               SUM(CASE WHEN m.excluded=1 AND i.source_kind IN """ + SAFE_SQL + sfrag + """ THEN 1 ELSE 0 END)
        FROM brand b LEFT JOIN mention m ON m.brand_id=b.id
        LEFT JOIN item i ON i.id=m.item_id
        WHERE b.workspace_id=? AND b.active=1
        GROUP BY b.id ORDER BY 4 DESC""", *sp, *sp, *sp, ws)


def outlet_gap_rows(session, ws, surface=None):
    sfrag, sp = _sf(surface)
    return rows(session, """
        SELECT i.outlet, b.name, b.is_focus, COUNT(*)
        FROM mention m JOIN item i ON i.id=m.item_id
        JOIN brand b ON b.id=m.brand_id
        WHERE m.excluded=0 AND m.hidden=0 AND b.workspace_id=? AND i.outlet IS NOT NULL
              AND i.outlet != '' AND i.source_kind IN """ + SAFE_SQL + sfrag + """
        GROUP BY i.outlet, b.id""", ws, *sp)


def top_outlet_rows(session, ws, limit, surface=None):
    sfrag, sp = _sf(surface)
    return rows(session, """
        SELECT i.outlet, COUNT(*) FROM mention m JOIN item i ON i.id=m.item_id
        JOIN brand b ON b.id=m.brand_id
        WHERE b.workspace_id=? AND m.excluded=0 AND m.hidden=0 AND i.outlet IS NOT NULL AND i.outlet!=''
              AND i.source_kind IN """ + SAFE_SQL + sfrag + """
        GROUP BY 1 ORDER BY 2 DESC LIMIT ?""", ws, *sp, limit)
