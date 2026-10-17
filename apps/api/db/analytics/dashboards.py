"""Small router-level reads: the sidebar stats ticker and the mentions facets."""
from ._util import one, rows, scalar


def stats_counts(session, ws):
    """(item_count, mention_count, last_done_finished_at)."""
    items = scalar(session,
        "SELECT COUNT(*) FROM item WHERE workspace_id=? AND source_kind IN ('public','licensed')",
        ws)
    mentions = scalar(session, """
        SELECT COUNT(*) FROM mention m JOIN brand b ON b.id=m.brand_id
        JOIN item i ON i.id=m.item_id WHERE b.workspace_id=? AND m.excluded=0
        AND m.hidden=0 AND i.source_kind IN ('public','licensed')""", ws)
    last = one(session, """
        SELECT finished_at FROM run WHERE workspace_id=? AND state='done'
        ORDER BY started_at DESC LIMIT 1""", ws)
    return items, mentions, (last[0] if last else None)


def surfaces(session, ws):
    """DISTINCT client-safe item surfaces for the channel filter."""
    return [r[0] for r in rows(session, """
        SELECT DISTINCT surface FROM item WHERE workspace_id=?
        AND source_kind IN ('public','licensed') ORDER BY 1""", ws)]


def preview_items(session, ws, limit):
    """(id, title, body, outlet, surface) newest-first, for the brand-rule
    preview / onboarding-preview sample match."""
    return rows(session, """
        SELECT id,title,body,outlet,surface FROM item WHERE workspace_id=?
        ORDER BY published_at DESC, id DESC LIMIT ?""", ws, limit)


def focus_brand_name(session, ws):
    row = one(session,
              "SELECT name FROM brand WHERE workspace_id=? AND is_focus=1 AND active=1 LIMIT 1",
              ws)
    return row[0] if row else None


def focus_mention_count(session, ws):
    return scalar(session,
        "SELECT COUNT(*) FROM mention m JOIN item i ON i.id=m.item_id JOIN brand b ON b.id=m.brand_id "
        "WHERE b.workspace_id=? AND b.is_focus=1 AND m.excluded=0 AND m.hidden=0 "
        "AND i.source_kind IN ('public','licensed')", ws)


def outlets(session, ws):
    """DISTINCT non-empty client-safe item outlets for the mentions filter."""
    return [r[0] for r in rows(session, """
        SELECT DISTINCT outlet FROM item WHERE workspace_id=? AND outlet IS NOT NULL
        AND outlet != '' AND source_kind IN ('public','licensed') ORDER BY 1""", ws)]
