"""Aggregation SQL behind core/insights/kpis.py::deltas."""
from ._util import SAFE_SQL, _sf, rows


def mention_dates(session, ws, surface=None):
    sfrag, sp = _sf(surface)
    return rows(session, """
        SELECT i.published_at FROM mention m JOIN item i ON i.id=m.item_id
        JOIN brand b ON b.id=m.brand_id
        LEFT JOIN dupe_edge dd ON dd.item_id=i.id
        WHERE b.workspace_id=? AND m.excluded=0 AND m.hidden=0 AND dd.item_id IS NULL
              AND i.source_kind IN """ + SAFE_SQL + sfrag, ws, *sp)


def focus_sentiment_dates(session, ws, surface=None):
    sfrag, sp = _sf(surface)
    return rows(session, """
        SELECT i.published_at, s.label FROM mention m JOIN item i ON i.id=m.item_id
        JOIN brand b ON b.id=m.brand_id JOIN sentiment s ON s.mention_id=m.id
        WHERE b.workspace_id=? AND b.is_focus=1 AND m.excluded=0 AND m.hidden=0
              AND s.label IN ('pos','neu','neg') AND i.source_kind IN """ + SAFE_SQL + sfrag,
        ws, *sp)


def focus_flag_dates(session, ws, surface=None):
    sfrag, sp = _sf(surface)
    return rows(session, """
        SELECT i.published_at, b.is_focus FROM mention m JOIN item i ON i.id=m.item_id
        JOIN brand b ON b.id=m.brand_id
        LEFT JOIN dupe_edge dd ON dd.item_id=i.id
        WHERE b.workspace_id=? AND m.excluded=0 AND m.hidden=0 AND dd.item_id IS NULL
              AND i.source_kind IN """ + SAFE_SQL + sfrag, ws, *sp)


def rating_dates(session, ws):
    from .reviews import rating_rows
    return rating_rows(session, ws)
