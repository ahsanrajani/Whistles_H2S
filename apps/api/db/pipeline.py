"""Write/read helpers for the collection pipeline — the SQL behind
``core/collector.run_collection`` and ``collection/{dedupe,match,status}.py``.
Postgres text(); each function takes a ``Session``.
"""
from sqlalchemy import text

from .analytics._util import _bind, one, rows, scalar


def _exec(session, sql, *params):
    converted, binds = _bind(sql, params)
    return session.execute(text(converted), binds)


# ---- monthly budget lookups (feed the Bright Data / X guards) --------------

def x_units_this_month(session, month):
    return scalar(session,
        "SELECT COALESCE(SUM(units),0) FROM call_log WHERE source='x_recent' AND substr(at,1,7)=?",
        month)


def bright_data_month_usage(session, month):
    """(records_used, spend_usd) across the Bright Data sources this month."""
    r = one(session, """
        SELECT COALESCE(SUM(units),0), COALESCE(SUM(units*unit_cost_usd),0)
        FROM call_log
        WHERE source IN ('brightdata_facebook_posts','brightdata_facebook_comments',
                         'brightdata_instagram_posts','brightdata_instagram_comments')
              AND substr(at,1,7)=?""", month)
    return (r[0], r[1])


def recent_post_urls(session, ws, source, limit=50):
    return [r[0] for r in rows(session, """
        SELECT url FROM item
        WHERE workspace_id=? AND source=? AND url IS NOT NULL AND url != ''
        ORDER BY id DESC LIMIT ?""", ws, source, limit)]


def insert_call_log(session, *, workspace_id, run_id, source, calls, units, unit_cost,
                    ok, at):
    _exec(session, """INSERT INTO call_log(workspace_id,run_id,source,calls,units,unit_cost_usd,ok,at)
                      VALUES (?,?,?,?,?,?,?,?)""",
          workspace_id, run_id, source, calls, units, unit_cost, 1 if ok else 0, at)


# ---- item / mention writes during a run -----------------------------------

def insert_item(session, values):
    """values: the 21-tuple in the column order below (``author_id`` /
    ``source_class`` last, P2.4). Returns rowcount (0 on conflict)."""
    return _exec(session,
        """INSERT INTO item
           (workspace_id,surface,source,source_kind,external_id,url,
            outlet,author,published_at,title,body,lang_guess,rating,sampled,
            collection_run_id,raw_json,collected_at,content_hash,simhash,
            author_id,source_class)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT DO NOTHING""", *values).rowcount


def item_id_by_external(session, ws, source, external_id):
    return scalar(session,
        "SELECT id FROM item WHERE workspace_id=? AND source=? AND external_id=?",
        ws, source, external_id)


def insert_implicit_mention(session, *, brand_id, rule, ws, source, external_id):
    _exec(session, """INSERT INTO mention (item_id,brand_id,workspace_id,rule,needs_review,excluded)
                      SELECT id,?,?,?,0,0 FROM item
                      WHERE workspace_id=? AND source=? AND external_id=?
                      ON CONFLICT DO NOTHING""",
          brand_id, ws, rule, ws, source, external_id)


# ---- dedupe -------------------------------------------------------------------

# canonical = the lowest-id `official` item in the group if any (Graph wins over
# a third-party scrape — P2.5), else the lowest id.
_CANON = "COALESCE(MIN(id) FILTER (WHERE source_class = 'official'), MIN(id))"


def dupe_groups_by_column(session, ws, col):
    return rows(session,
        f"""SELECT {col}, {_CANON} FROM item WHERE workspace_id=? AND {col} IS NOT NULL
            AND {col} != '' GROUP BY {col} HAVING COUNT(*)>1""", ws)


def fold_column_dupes(session, ws, col, key, canon, method):
    return _exec(session,
        f"""INSERT INTO dupe_edge(item_id,canonical_id,method,workspace_id)
            SELECT id,?,?,? FROM item WHERE workspace_id=? AND {col}=? AND id!=?
            ON CONFLICT DO NOTHING""", canon, method, ws, ws, key, canon).rowcount


def title_dupe_groups(session, ws):
    return rows(session, f"""
        SELECT outlet, lower(trim(title)) AS k, {_CANON} FROM item
        WHERE workspace_id=? AND title IS NOT NULL AND trim(title) != ''
              AND id NOT IN (SELECT item_id FROM dupe_edge)
        GROUP BY outlet, k HAVING COUNT(*) > 1""", ws)


def fold_title_dupes(session, ws, canon, key, outlet):
    return _exec(session, """
        INSERT INTO dupe_edge(item_id, canonical_id, method, workspace_id)
        SELECT id, ?, 'norm_title', ? FROM item
        WHERE workspace_id=? AND id != ? AND lower(trim(title)) = ?
              AND outlet IS NOT DISTINCT FROM ?
              AND id NOT IN (SELECT item_id FROM dupe_edge)
        ON CONFLICT DO NOTHING""", canon, ws, ws, canon, key, outlet).rowcount


def simhash_rows(session, ws):
    """(id, simhash) for hashed, non-folded, non-regulatory items — the input to
    the SimHash near-duplicate pass (P2.1). Ordered ``official`` first, then by
    id, so a Graph item becomes the bucket canonical over a third-party scrape
    of the same post (P2.5)."""
    return rows(session, """
        SELECT i.id, i.simhash FROM item i
        LEFT JOIN dupe_edge d ON d.item_id = i.id
        WHERE i.workspace_id = ? AND d.item_id IS NULL
              AND i.simhash IS NOT NULL AND i.simhash <> 0
              AND i.surface != 'regulatory'
        ORDER BY (i.source_class = 'official') DESC, i.id""", ws)


def fold_simhash_dupes(session, ws, item_id, canonical_id):
    return _exec(session, """
        INSERT INTO dupe_edge(item_id, canonical_id, method, workspace_id)
        VALUES (?, ?, 'simhash', ?)
        ON CONFLICT DO NOTHING""", item_id, canonical_id, ws).rowcount


# ---- match -----------------------------------------------------------------

def matchable_items(session, ws):
    """(id, title, body) for non-regulatory, non-duplicate items."""
    return rows(session, """
        SELECT i.id,i.title,i.body FROM item i
        LEFT JOIN dupe_edge d ON d.item_id=i.id
        WHERE i.workspace_id=? AND d.item_id IS NULL AND i.surface != 'regulatory'""", ws)


def insert_mention(session, ws, iid, bid, rule, review, exc, reason):
    return _exec(session, """
        INSERT INTO mention (item_id,brand_id,workspace_id,rule,needs_review,excluded,exclude_reason)
        VALUES (?,?,?,?,?,?,?) ON CONFLICT DO NOTHING""",
        iid, bid, ws, rule, review, exc, reason).rowcount


# ---- surface status ------------------------------------------------------------

_SURFACE_STATUS_UPSERT = """INSERT INTO surface_status
    (run_id,workspace_id,surface,state,n_sources,estimable,note)
    VALUES (?,?,?,?,?,?,?)
    ON CONFLICT (run_id,workspace_id,surface) DO UPDATE SET
      state=EXCLUDED.state, n_sources=EXCLUDED.n_sources,
      estimable=EXCLUDED.estimable, note=EXCLUDED.note"""


def upsert_surface_status(session, *, run_id, ws, surface, state, n_sources, estimable,
                          note):
    _exec(session, _SURFACE_STATUS_UPSERT,
          run_id, ws, surface, state, n_sources, estimable, note)


def latest_surface_status(session, ws):
    """Each surface's most recently recorded status, across every run (not
    just the latest one) -- lets a per-source-scheduled tick (P2.7) that
    didn't happen to touch a surface carry that surface's last real state
    forward instead of write_status() papering over the gap as "failed"."""
    result = rows(session, """
        SELECT DISTINCT ON (ss.surface) ss.surface, ss.state, ss.n_sources,
               ss.estimable, ss.note
        FROM surface_status ss JOIN run r ON r.id = ss.run_id
        WHERE ss.workspace_id = ?
        ORDER BY ss.surface, r.started_at DESC""", ws)
    return {r[0]: {"state": r[1], "n_sources": r[2], "estimable": r[3], "note": r[4]}
           for r in result}


# ---- scoring workers (sentiment / classify) -------------------------------
_SAFE = "('public','licensed')"


def clear_sentiment(session, ws):
    return _exec(session, """
        DELETE FROM sentiment WHERE mention_id IN
        (SELECT m.id FROM mention m JOIN brand b ON b.id = m.brand_id
         WHERE b.workspace_id = ?)""", ws).rowcount


def pending_sentiment(session, ws, limit):
    """(mention_id, lang_guess, surface, rating, text) for unscored client-safe rows."""
    return rows(session, """
        SELECT m.id, i.lang_guess, i.surface, i.rating,
               TRIM(COALESCE(i.title,'') || ' ' || COALESCE(i.body,''))
        FROM mention m
        JOIN item i ON i.id = m.item_id
        JOIN brand b ON b.id = m.brand_id
        LEFT JOIN sentiment s ON s.mention_id = m.id
        WHERE b.workspace_id = ? AND m.excluded = 0
              AND i.source_kind IN """ + _SAFE + """
              AND s.mention_id IS NULL
        ORDER BY i.id DESC LIMIT ?""", ws, limit)


def upsert_sentiment(session, *, workspace_id, mention_id, label, model_id, scored_lang,
                     scored_at, note):
    _exec(session, """
        INSERT INTO sentiment (mention_id, workspace_id, label, model_id, scored_lang, scored_at, note)
        VALUES (?,?,?,?,?,?,?)
        ON CONFLICT (mention_id) DO UPDATE SET
          label=EXCLUDED.label, model_id=EXCLUDED.model_id,
          scored_lang=EXCLUDED.scored_lang, scored_at=EXCLUDED.scored_at,
          note=EXCLUDED.note""",
          mention_id, workspace_id, label, model_id, scored_lang, scored_at, note)


def clear_mention_class(session, ws):
    return _exec(session, """
        DELETE FROM mention_class WHERE mention_id IN
        (SELECT m.id FROM mention m JOIN brand b ON b.id = m.brand_id
         WHERE b.workspace_id = ?)""", ws).rowcount


def pending_mention_class(session, ws, limit):
    """(mention_id, lang_guess, surface, rating, text, sentiment_label) for
    unclassified client-safe rows."""
    return rows(session, """
        SELECT m.id, i.lang_guess, i.surface, i.rating,
               TRIM(COALESCE(i.title,'') || ' ' || COALESCE(i.body,'')),
               (SELECT s.label FROM sentiment s WHERE s.mention_id = m.id)
        FROM mention m
        JOIN item i ON i.id = m.item_id
        JOIN brand b ON b.id = m.brand_id
        LEFT JOIN mention_class mc ON mc.mention_id = m.id
        WHERE b.workspace_id = ? AND m.excluded = 0
              AND i.source_kind IN """ + _SAFE + """
              AND mc.mention_id IS NULL
        ORDER BY i.id DESC LIMIT ?""", ws, limit)


def upsert_mention_class(session, *, workspace_id, mention_id, category, confidence,
                         model_id, classified_at):
    _exec(session, """
        INSERT INTO mention_class (mention_id, workspace_id, category, confidence, model_id, classified_at)
        VALUES (?,?,?,?,?,?)
        ON CONFLICT (mention_id) DO UPDATE SET
          category=EXCLUDED.category, confidence=EXCLUDED.confidence,
          model_id=EXCLUDED.model_id, classified_at=EXCLUDED.classified_at""",
        mention_id, workspace_id, category, confidence, model_id, classified_at)
