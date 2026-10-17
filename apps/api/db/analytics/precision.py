"""Aggregation SQL behind core/precision.py (P2.8 match-precision report)."""
from ._util import SAFE_SQL, rows

# identity rules — the source *is* the brand, so they are not "matches" to score
_IDENTITY = "('app_review', 'meta_mention', 'brightdata_owned_channel')"


def match_precision_rows(session, ws):
    """(brand, needs_review, matched, labelled, correct) per brand × pattern
    class, over client-safe sources, excluding identity rules."""
    return rows(session, f"""
        SELECT b.name, m.needs_review,
               COUNT(*),
               SUM(CASE WHEN g.correct IS NOT NULL THEN 1 ELSE 0 END),
               SUM(CASE WHEN g.correct = 1 THEN 1 ELSE 0 END)
        FROM mention m
        JOIN item i ON i.id = m.item_id
        JOIN brand b ON b.id = m.brand_id
        LEFT JOIN gold_label g ON g.mention_id = m.id
        WHERE b.workspace_id = ? AND m.excluded = 0 AND m.hidden = 0
              AND m.rule NOT IN {_IDENTITY}
              AND i.source_kind IN {SAFE_SQL}
        GROUP BY b.name, m.needs_review
        ORDER BY b.name, m.needs_review
    """, ws)
