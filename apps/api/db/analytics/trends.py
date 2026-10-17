"""Aggregation SQL behind core/insights/trends.py."""
from ._util import SAFE_SQL, _sf, rows


def timeline_rows(session, ws, surface=None):
    """(brand_name, published_at) for every dated client-safe mention."""
    sfrag, sp = _sf(surface)
    return rows(session, """
        SELECT b.name, i.published_at
        FROM mention m JOIN item i ON i.id=m.item_id JOIN brand b ON b.id=m.brand_id
        WHERE b.workspace_id=? AND m.excluded=0 AND m.hidden=0 AND i.published_at IS NOT NULL
              AND i.source_kind IN """ + SAFE_SQL + sfrag, ws, *sp)


def press_volume_rows(session, ws, surface=None):
    """(brand_name, is_focus, published_at). No channel filter -> news-wire only."""
    if surface:
        srcfrag, sp = " AND i.surface = ?", [surface]
    else:
        srcfrag, sp = " AND i.source = 'googlenews_rss'", []
    return rows(session, """
        SELECT b.name, b.is_focus, i.published_at
        FROM mention m JOIN item i ON i.id=m.item_id JOIN brand b ON b.id=m.brand_id
        WHERE b.workspace_id=? AND m.excluded=0 AND m.hidden=0 AND b.active=1
              AND i.source_kind IN """ + SAFE_SQL + srcfrag, ws, *sp)


def peak_hour_rows(session, ws, surface=None):
    """published_at for every dated client-safe mention."""
    sfrag, sp = _sf(surface)
    return rows(session, """
        SELECT i.published_at FROM mention m JOIN item i ON i.id=m.item_id
        JOIN brand b ON b.id=m.brand_id
        WHERE b.workspace_id=? AND m.excluded=0 AND m.hidden=0 AND i.published_at IS NOT NULL
              AND i.source_kind IN """ + SAFE_SQL + sfrag, ws, *sp)
