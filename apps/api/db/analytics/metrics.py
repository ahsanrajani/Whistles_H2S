"""Aggregation SQL behind ``core/metrics.py`` (P4.2 metric layer).

All queries read ``metric_fact`` (the P4.1 warehouse). ``core`` keeps the
Python shaping — Wilson intervals on proportions, period deltas, dict
assembly — and calls in here for grouped/rolled-up rows.
"""
from sqlalchemy import text

# dims/columns a caller may group by, mapped to their SQL expression. Anything
# not in here is rejected by ``core.metrics`` before we build a query.
GROUPABLE = {
    "entity_ref": "entity_ref",
    "entity_type": "entity_type",
    "media_type": "COALESCE(dims ->> 'media_type', 'unknown')",
    "country": "COALESCE(dims ->> 'country', 'unknown')",
}


def _scope(params, entity_type):
    sql = ("workspace_id = :ws AND source = :source AND metric = :metric "
           "AND day >= :start AND day <= :end")
    if entity_type is not None:
        sql += " AND entity_type = :etype"
        params["etype"] = entity_type
    return sql


def rollup(session, ws, *, source, metric, start, end, entity_type=None):
    """One row: summed value + summed numerator/denominator + coverage."""
    p = {"ws": ws, "source": source, "metric": metric, "start": start, "end": end}
    where = _scope(p, entity_type)
    return session.execute(text(f"""
        SELECT COALESCE(SUM(value), 0)          AS sum_value,
               SUM(numerator)                   AS sum_num,
               SUM(denominator)                 AS sum_den,
               COUNT(DISTINCT day)              AS days,
               COUNT(*)                         AS rows
        FROM metric_fact WHERE {where}
    """), p).mappings().one()


def daily(session, ws, *, source, metric, start, end, entity_type=None):
    p = {"ws": ws, "source": source, "metric": metric, "start": start, "end": end}
    where = _scope(p, entity_type)
    return session.execute(text(f"""
        SELECT day,
               COALESCE(SUM(value), 0) AS sum_value,
               SUM(numerator)          AS sum_num,
               SUM(denominator)        AS sum_den,
               COUNT(*)                AS rows
        FROM metric_fact WHERE {where}
        GROUP BY day ORDER BY day
    """), p).mappings().all()


def grouped(session, ws, *, source, metric, start, end, group_by, entity_type=None):
    expr = GROUPABLE[group_by]
    p = {"ws": ws, "source": source, "metric": metric, "start": start, "end": end}
    where = _scope(p, entity_type)
    return session.execute(text(f"""
        SELECT {expr} AS grp,
               COALESCE(SUM(value), 0) AS sum_value,
               SUM(numerator)          AS sum_num,
               SUM(denominator)        AS sum_den,
               COUNT(*)                AS rows
        FROM metric_fact WHERE {where}
        GROUP BY {expr} ORDER BY sum_value DESC
    """), p).mappings().all()


def account_rows(session, ws, *, source, start, end):
    """Per-metric window rollup for the non-post (account / page / org) grains —
    the P4.5 account summary."""
    return session.execute(text("""
        SELECT metric,
               COALESCE(SUM(value), 0) AS sum_value,
               SUM(numerator)          AS sum_num,
               SUM(denominator)        AS sum_den,
               COUNT(*)                AS rows
        FROM metric_fact
        WHERE workspace_id = :ws AND source = :source
              AND entity_type <> 'post'
              AND day >= :start AND day <= :end
        GROUP BY metric ORDER BY metric
    """), {"ws": ws, "source": source, "start": start, "end": end}).mappings().all()


def post_rows(session, ws, *, source, start, end, media_types=None, limit=50):
    """Per-post pivot (impressions / engagements / reactions + engagement-rate
    counts), newest-highest-reach first — the P4.5 post / video / Reel
    scorecards."""
    p = {"ws": ws, "source": source, "start": start, "end": end, "lim": limit}
    mt = ""
    if media_types:
        mt = "AND COALESCE(dims ->> 'media_type', 'unknown') = ANY(:mt)"
        p["mt"] = list(media_types)
    return session.execute(text(f"""
        SELECT entity_ref,
               COALESCE(dims ->> 'media_type', 'unknown')          AS media_type,
               SUM(value) FILTER (WHERE metric = 'impressions')     AS impressions,
               SUM(value) FILTER (WHERE metric = 'engagements')     AS engagements,
               SUM(value) FILTER (WHERE metric = 'reactions')       AS reactions,
               SUM(numerator) FILTER (WHERE metric = 'engagement_rate')   AS er_num,
               SUM(denominator) FILTER (WHERE metric = 'engagement_rate') AS er_den,
               MIN(day) AS first_day, MAX(day) AS last_day
        FROM metric_fact
        WHERE workspace_id = :ws AND source = :source AND entity_type = 'post'
              AND day >= :start AND day <= :end {mt}
        GROUP BY entity_ref, media_type
        ORDER BY impressions DESC NULLS LAST
        LIMIT :lim
    """), p).mappings().all()


def catalog(session, ws):
    """What is queryable for this workspace: (source, metric, entity_type) with
    row counts and whether the metric is a proportion (has denominators)."""
    return session.execute(text("""
        SELECT mf.source, mf.metric, mf.entity_type,
               COUNT(DISTINCT mf.id)                       AS rows,
               MIN(mf.day)                                 AS first_day,
               MAX(mf.day)                                 AS last_day,
               BOOL_OR(mf.denominator IS NOT NULL)         AS is_proportion,
               COALESCE(ARRAY_AGG(DISTINCT k.key)
                        FILTER (WHERE k.key IS NOT NULL), '{}') AS dims
        FROM metric_fact mf
        LEFT JOIN LATERAL jsonb_object_keys(mf.dims) AS k(key) ON true
        WHERE mf.workspace_id = :ws
        GROUP BY mf.source, mf.metric, mf.entity_type
        ORDER BY mf.source, mf.metric, mf.entity_type
    """), {"ws": ws}).mappings().all()
