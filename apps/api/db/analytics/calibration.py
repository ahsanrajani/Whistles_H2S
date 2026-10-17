"""Aggregation SQL behind core/insights/calibration.py."""
from ._util import SAFE_SQL, rows


def rule_precision_rows(session, ws):
    return rows(session, """
        SELECT m.rule, COUNT(*),
               SUM(m.needs_review),
               SUM(CASE WHEN g.correct IS NOT NULL THEN 1 ELSE 0 END),
               SUM(CASE WHEN g.correct=1 THEN 1 ELSE 0 END)
        FROM mention m JOIN item i ON i.id=m.item_id JOIN brand b ON b.id=m.brand_id
        LEFT JOIN gold_label g ON g.mention_id=m.id
        WHERE b.workspace_id=? AND m.excluded=0 AND m.hidden=0 AND i.source_kind IN """ + SAFE_SQL + """
        GROUP BY m.rule ORDER BY 2 DESC""", ws)


def calibration_status_rows(session, ws):
    return rows(session, """
        SELECT m.rule, COUNT(*),
               SUM(CASE WHEN m.needs_review=1 THEN 1 ELSE 0 END),
               SUM(CASE WHEN g.correct IS NOT NULL THEN 1 ELSE 0 END),
               SUM(CASE WHEN g.correct=1 THEN 1 ELSE 0 END)
        FROM mention m JOIN item i ON i.id=m.item_id JOIN brand b ON b.id=m.brand_id
        LEFT JOIN gold_label g ON g.mention_id=m.id
        WHERE b.workspace_id=? AND m.excluded=0 AND m.hidden=0 AND i.source_kind IN """ + SAFE_SQL + """
        GROUP BY m.rule ORDER BY 3 DESC, 2 DESC""", ws)


def review_batch_rows(session, ws, per_rule):
    return rows(session, """
        WITH ranked AS (
          SELECT b.name, i.surface, i.source, i.outlet, i.published_at, i.url,
                 COALESCE(i.title, i.body) AS text, m.rule, m.needs_review,
                 i.lang_guess, i.sampled, m.id AS mid,
                 ROW_NUMBER() OVER (PARTITION BY m.rule
                                    ORDER BY m.needs_review DESC, i.id DESC) AS rn
          FROM mention m
          JOIN item i ON i.id = m.item_id
          JOIN brand b ON b.id = m.brand_id
          LEFT JOIN gold_label g ON g.mention_id = m.id
          WHERE b.workspace_id = ? AND m.excluded = 0 AND m.hidden = 0 AND g.mention_id IS NULL
                AND m.rule NOT IN ('app_review', 'meta_mention')
                AND i.source_kind IN """ + SAFE_SQL + """
        )
        SELECT name, surface, source, outlet, published_at, url, text, rule,
               needs_review, lang_guess, sampled, mid
        FROM ranked WHERE rn <= ?
        ORDER BY needs_review DESC, rule, mid DESC""", ws, per_rule)


def exclusion_rows(session, ws):
    return rows(session, """SELECT m.exclude_reason, COUNT(*) FROM mention m
        JOIN item i ON i.id=m.item_id JOIN brand b ON b.id=m.brand_id
        WHERE b.workspace_id=? AND m.excluded=1 AND i.source_kind IN """ + SAFE_SQL + """
                        GROUP BY 1 ORDER BY 2 DESC""", ws)
