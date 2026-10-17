"""The client-safe story feed and the fully-filtered evidence table — dynamic
SQL behind core/insights/evidence.py."""
from datetime import datetime, timedelta, timezone

from ._util import SAFE_SQL, rows

_EVIDENCE_SORTS = {
    "new": "published_at DESC, iid DESC",
    "old": "published_at ASC, iid ASC",
    "top": "rating IS NULL, rating DESC, published_at DESC",
    "low": "rating IS NULL, rating ASC, published_at DESC",
    "spread": "spread DESC, published_at DESC",
}
_RATING_BANDS = {"high": "i.rating >= 4", "mid": "i.rating = 3",
                 "low": "i.rating BETWEEN 1 AND 2"}


def feed_rows(session, ws, limit=25, brand_id=None, only_review=False, surface=None):
    sql = """SELECT b.name, i.surface, i.source, i.outlet, i.published_at, i.url,
                    COALESCE(i.title, i.body), m.rule, m.needs_review, i.lang_guess,
                    i.sampled, m.id,
                    (SELECT s.label FROM sentiment s WHERE s.mention_id=m.id),
                    (SELECT mc.category FROM mention_class mc WHERE mc.mention_id=m.id)
             FROM mention m JOIN item i ON i.id=m.item_id JOIN brand b ON b.id=m.brand_id
             LEFT JOIN dupe_edge dd ON dd.item_id=i.id
             WHERE b.workspace_id=? AND m.excluded=0 AND m.hidden=0 AND dd.item_id IS NULL
                   AND i.source_kind IN """ + SAFE_SQL
    args = [ws]
    if brand_id:
        sql += " AND b.id=?"
        args.append(brand_id)
    if surface:
        sql += " AND i.surface=?"
        args.append(surface)
    if only_review:
        sql += " AND m.needs_review=1"
    sql += " ORDER BY m.needs_review DESC, i.id DESC LIMIT ?"
    args.append(max(limit * 6, 60))                    # over-fetch, then de-dupe by title
    return rows(session, sql, *args)


def evidence_query(session, ws, *, limit=100, brand_id=None, outlet="", surface="",
                   rule="", sentiment="", since=None, q="", category="", rating="",
                   sort="new", include_hidden=False):
    where = ["b.workspace_id=?", "m.excluded=0", "dd.item_id IS NULL",
             "i.source_kind IN " + SAFE_SQL]
    if not include_hidden:
        where.append("m.hidden=0")
    args = [ws]
    for value, clause in ((brand_id, "b.id=?"), (outlet, "i.outlet=?"),
                          (surface, "i.surface=?"), (rule, "m.rule=?"),
                          (sentiment, "s.label=?"),
                          (category, "COALESCE(mc.category,'other')=?")):
        if value:
            where.append(clause)
            args.append(value)
    if rating in _RATING_BANDS:
        where.append(_RATING_BANDS[rating])
    elif str(rating) in ("1", "2", "3", "4", "5"):     # exact-star click-through
        where.append("i.rating=?")
        args.append(int(rating))
    if q and q.strip():
        needle = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        where.append("COALESCE(i.title,i.body) LIKE ? ESCAPE '\\'")
        args.append("%" + needle + "%")
    if since:
        cutoff = (datetime.now(timezone.utc).date()
                  - timedelta(days=int(since))).isoformat()
        where.append("substr(i.published_at,1,10) >= ?")
        args.append(cutoff)
    joins = """FROM mention m JOIN item i ON i.id=m.item_id JOIN brand b ON b.id=m.brand_id
               LEFT JOIN dupe_edge dd ON dd.item_id=i.id
               LEFT JOIN sentiment s ON s.mention_id=m.id
               LEFT JOIN mention_class mc ON mc.mention_id=m.id"""
    predicate = " AND ".join(where)
    total = rows(session, "SELECT COUNT(DISTINCT i.id) " + joins + " WHERE " + predicate,
                 *args)[0][0]

    order = _EVIDENCE_SORTS.get(sort, _EVIDENCE_SORTS["new"])
    rep_hidden = "" if include_hidden else " AND m2.hidden=0"
    result = rows(
        session,
        "WITH ev AS (SELECT m.id AS mid, b.id AS bid, b.name AS bname, i.surface, i.source,"
        " i.source_kind, i.outlet, i.author, i.published_at, i.collected_at,"
        " i.collection_run_id, i.url, COALESCE(i.title,i.body) AS text, m.rule,"
        " m.needs_review, i.sampled, i.lang_guess, s.label AS senti, i.rating,"
        " mc.category AS cat, m.hidden AS hidden, i.id AS iid,"
        " (SELECT COUNT(*) FROM dupe_edge x WHERE x.canonical_id=i.id) AS spread,"
        " (SELECT string_agg(DISTINCT b2.name, ',') FROM mention m2"
        "  JOIN brand b2 ON b2.id=m2.brand_id"
        "  WHERE m2.item_id=i.id AND m2.excluded=0" + rep_hidden + " AND b2.id != b.id) AS other_brands,"
        " ROW_NUMBER() OVER (PARTITION BY i.id ORDER BY"
        "   CASE WHEN CAST(? AS integer) IS NOT NULL AND b.id = ? THEN 0"
        "        WHEN b.is_focus = 1 THEN 1 ELSE 2 END, m.needs_review, m.id) AS rn "
        + joins + " WHERE " + predicate + ")"
        " SELECT mid,bid,bname,surface,source,source_kind,outlet,author,published_at,"
        " collected_at,collection_run_id,url,text,rule,needs_review,sampled,lang_guess,"
        " senti,rating,cat,hidden,other_brands FROM ev WHERE rn = 1 ORDER BY "
        + order + " LIMIT ?", brand_id, brand_id, *args, limit)
    return result, total
