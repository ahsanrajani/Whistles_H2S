"""Aggregation SQL behind core/insights/overview.py."""
from ._util import SAFE_SQL, _sf, rows, scalar


def surface_status_rows(session, ws, run_id):
    return rows(session, """SELECT surface,state,n_sources,estimable,note
                            FROM surface_status WHERE workspace_id=? AND run_id=?""",
                ws, run_id)


def language_rows(session, ws, surface=None):
    sfrag, sp = _sf(surface)
    return rows(session, """SELECT i.lang_guess, COUNT(*), COUNT(s.mention_id) FROM mention m
                        JOIN item i ON i.id=m.item_id JOIN brand b ON b.id=m.brand_id
                        LEFT JOIN sentiment s ON s.mention_id=m.id
                        WHERE b.workspace_id=? AND m.excluded=0 AND m.hidden=0
                              AND i.source_kind IN """ + SAFE_SQL + sfrag + """
                        GROUP BY 1 ORDER BY 2 DESC""", ws, *sp)


def author_rows(session, ws, surface=None):
    sfrag, sp = _sf(surface)
    return rows(session, """
        SELECT i.author, COUNT(*) FROM mention m JOIN item i ON i.id=m.item_id
        JOIN brand b ON b.id=m.brand_id
        WHERE b.workspace_id=? AND m.excluded=0 AND m.hidden=0 AND i.source_kind IN """ + SAFE_SQL + sfrag + """
              AND i.author IS NOT NULL AND i.author != '' AND i.author != i.outlet
        GROUP BY 1 ORDER BY 2 DESC LIMIT 40""", ws, *sp)


def mention_mix_rows(session, ws, surface=None):
    sfrag, sp = _sf(surface)
    return rows(session, """
        SELECT COALESCE(mc.category,'other'),
               (SELECT s.label FROM sentiment s WHERE s.mention_id=m.id),
               i.published_at
        FROM mention m JOIN item i ON i.id=m.item_id JOIN brand b ON b.id=m.brand_id
        LEFT JOIN dupe_edge dd ON dd.item_id=i.id
        LEFT JOIN mention_class mc ON mc.mention_id=m.id
        WHERE b.workspace_id=? AND m.excluded=0 AND m.hidden=0 AND dd.item_id IS NULL
              AND i.source_kind IN """ + SAFE_SQL + sfrag, ws, *sp)


def recent_window_rows(session, ws):
    return rows(session, """
        SELECT b.name, i.published_at
        FROM mention m JOIN item i ON i.id=m.item_id JOIN brand b ON b.id=m.brand_id
        WHERE b.workspace_id=? AND m.excluded=0 AND m.hidden=0 AND i.published_at IS NOT NULL
              AND i.source_kind IN """ + SAFE_SQL, ws)


def review_backlog_count(session, ws):
    return scalar(session, """
        SELECT COUNT(*) FROM mention m
        JOIN item i ON i.id=m.item_id JOIN brand b ON b.id=m.brand_id
        LEFT JOIN gold_label gl ON gl.mention_id=m.id
        WHERE b.workspace_id=? AND m.excluded=0 AND m.hidden=0 AND m.needs_review=1
              AND gl.mention_id IS NULL AND i.source_kind IN """ + SAFE_SQL, ws)
