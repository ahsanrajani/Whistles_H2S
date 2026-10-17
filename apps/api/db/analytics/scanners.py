"""Query bodies for the standalone deterministic scanners
(scam / triage / switch-intent / incidents / product-lines / regulatory /
branch-perf). The Python scoring stays in ``core/*``."""
from ._util import SAFE_SQL, _sf, rows


def scam_comment_rows(session, ws, comment_sources, limit, surface=None):
    ph = ",".join("?" for _ in comment_sources)
    return rows(
        session,
        "SELECT i.id, i.surface, i.source, i.outlet, i.author, i.published_at, "
        "       i.url, i.title, i.body, i.raw_json, "
        "       (SELECT b.name FROM mention m JOIN brand b ON b.id=m.brand_id "
        "        WHERE m.item_id=i.id AND m.excluded=0 AND m.hidden=0 "
        "        ORDER BY b.is_focus DESC LIMIT 1) "
        "FROM item i "
        "WHERE i.workspace_id=? AND i.source_kind IN " + SAFE_SQL + " "
        "      AND i.source IN (" + ph + ") "
        "      AND (CAST(? AS text) IS NULL OR i.surface = ?) "
        "ORDER BY i.published_at DESC, i.id DESC LIMIT " + str(int(limit)),
        ws, *comment_sources, surface, surface)


def triage_rows(session, ws, limit):
    return rows(
        session,
        "SELECT i.id, b.id, b.name, b.is_focus, i.surface, i.source, i.outlet, "
        "       i.author, i.published_at, i.url, COALESCE(i.title,i.body) AS text, "
        "       i.rating, s.label, mc.category, m.needs_review "
        "FROM mention m JOIN item i ON i.id=m.item_id JOIN brand b ON b.id=m.brand_id "
        "LEFT JOIN dupe_edge dd ON dd.item_id=i.id "
        "LEFT JOIN sentiment s ON s.mention_id=m.id "
        "LEFT JOIN mention_class mc ON mc.mention_id=m.id "
        "WHERE b.workspace_id=? AND m.excluded=0 AND m.hidden=0 AND dd.item_id IS NULL "
        "      AND i.source_kind IN " + SAFE_SQL + " "
        "      AND (mc.category IN ('complaint','fraud') OR s.label='neg' "
        "           OR i.rating IN (1,2)) "
        "ORDER BY i.published_at DESC, i.id DESC LIMIT " + str(int(limit)),
        ws)


def switch_intent_rows(session, focus_brand_id, limit):
    return rows(
        session,
        "SELECT i.id, i.surface, i.source, i.outlet, i.author, i.published_at, i.url, "
        "       COALESCE(i.title,i.body) AS text, i.rating, s.label, mc.category "
        "FROM mention m JOIN item i ON i.id=m.item_id "
        "LEFT JOIN dupe_edge dd ON dd.item_id=i.id "
        "LEFT JOIN sentiment s ON s.mention_id=m.id "
        "LEFT JOIN mention_class mc ON mc.mention_id=m.id "
        "WHERE m.brand_id=? AND m.excluded=0 AND m.hidden=0 AND dd.item_id IS NULL "
        "      AND i.source_kind IN " + SAFE_SQL + " "
        "ORDER BY i.published_at DESC, i.id DESC LIMIT " + str(int(limit)),
        focus_brand_id)


def incident_rows(session, ws):
    return rows(
        session,
        "SELECT b.name, b.is_focus, i.id, i.published_at, i.outlet, i.url, "
        "       COALESCE(i.title,i.body) AS text "
        "FROM mention m JOIN item i ON i.id=m.item_id JOIN brand b ON b.id=m.brand_id "
        "LEFT JOIN dupe_edge dd ON dd.item_id=i.id "
        "WHERE b.workspace_id=? AND b.active=1 AND m.excluded=0 AND m.hidden=0 "
        "      AND dd.item_id IS NULL AND i.source_kind IN " + SAFE_SQL + " "
        "      AND i.published_at IS NOT NULL",
        ws)


def product_line_rows(session, focus_brand_id):
    return rows(
        session,
        "SELECT i.id, i.outlet, i.url, i.published_at, COALESCE(i.title,i.body) AS text, "
        "       s.label "
        "FROM mention m JOIN item i ON i.id=m.item_id "
        "LEFT JOIN dupe_edge dd ON dd.item_id=i.id "
        "LEFT JOIN sentiment s ON s.mention_id=m.id "
        "WHERE m.brand_id=? AND m.excluded=0 AND m.hidden=0 AND dd.item_id IS NULL "
        "      AND i.source_kind IN " + SAFE_SQL + " "
        "ORDER BY i.published_at DESC, i.id DESC",
        focus_brand_id)


def regulatory_item_rows(session, ws, limit):
    return rows(
        session,
        "SELECT id, outlet, url, published_at, title, body, raw_json "
        "FROM item WHERE workspace_id=? AND source='regulatory_watch' "
        "ORDER BY published_at DESC, id DESC LIMIT " + str(int(limit)),
        ws)


def branch_perf_rows(session, focus_brand_id):
    return rows(
        session,
        "SELECT i.id, i.surface, i.source, i.outlet, i.published_at, i.url, "
        "       COALESCE(i.title,i.body) AS text, i.rating, i.raw_json, "
        "       s.label, mc.category "
        "FROM mention m JOIN item i ON i.id=m.item_id "
        "LEFT JOIN dupe_edge dd ON dd.item_id=i.id "
        "LEFT JOIN sentiment s ON s.mention_id=m.id "
        "LEFT JOIN mention_class mc ON mc.mention_id=m.id "
        "WHERE m.brand_id=? AND m.excluded=0 AND m.hidden=0 AND dd.item_id IS NULL "
        "      AND i.source_kind IN " + SAFE_SQL + " "
        "ORDER BY i.published_at DESC, i.id DESC",
        focus_brand_id)
