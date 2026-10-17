"""``metric_fact`` access (P4.1) — idempotent daily upserts into the metric
warehouse plus the read helpers the P4.2 metric layer builds on.

A fact is uniquely a ``(workspace, source, entity_type, entity_ref, metric,
day, dims)`` grain. ``dim_hash`` is a stable serialisation of ``dims`` so the
unique index is small and order-independent; callers pass ``dims`` as a plain
dict and never compute the hash themselves.
"""
import json

from sqlalchemy import text


def dim_hash(dims: dict | None) -> str:
    """Order-independent, compact key for a dims dict ('' when empty)."""
    if not dims:
        return ""
    return json.dumps(dims, sort_keys=True, separators=(",", ":"))


def upsert_many(session, workspace_id, facts) -> int:
    """Insert/replace a batch of fact dicts. Each dict:
    ``source, entity_type, metric, day`` (required); ``entity_ref, value,
    numerator, denominator, dims`` (optional). Returns the row count. Caller
    commits."""
    n = 0
    for f in facts:
        dims = f.get("dims") or {}
        session.execute(text("""
            INSERT INTO metric_fact
                (workspace_id, source, entity_type, entity_ref, metric, day,
                 value, numerator, denominator, dims, dim_hash, captured_at)
            VALUES
                (:ws, :source, :etype, :eref, :metric, :day,
                 :value, :num, :den, CAST(:dims AS jsonb), :dh, now())
            ON CONFLICT (workspace_id, source, entity_type, entity_ref, metric,
                         day, dim_hash)
            DO UPDATE SET value = EXCLUDED.value,
                          numerator = EXCLUDED.numerator,
                          denominator = EXCLUDED.denominator,
                          dims = EXCLUDED.dims,
                          captured_at = now()
        """), {"ws": workspace_id, "source": f["source"],
               "etype": f["entity_type"], "eref": f.get("entity_ref") or "",
               "metric": f["metric"], "day": f["day"],
               "value": f.get("value"), "num": f.get("numerator"),
               "den": f.get("denominator"), "dims": json.dumps(dims),
               "dh": dim_hash(dims)})
        n += 1
    return n


def latest_by_metric(session, workspace_id, source, entity_ref=None):
    """{metric: row} — the most-recently-captured row per metric for one
    source (optionally scoped to one entity_ref), e.g. reading back the
    latest app-store rating/count/histogram facts for a dashboard without a
    date range. Empty dict if nothing has ever been written."""
    q = ["SELECT DISTINCT ON (metric) metric, entity_ref, value, numerator,",
         "denominator, dims, day, captured_at",
         "FROM metric_fact WHERE workspace_id = :ws AND source = :source"]
    p = {"ws": workspace_id, "source": source}
    if entity_ref is not None:
        q.append("AND entity_ref = :eref")
        p["eref"] = entity_ref
    q.append("ORDER BY metric, day DESC, captured_at DESC")
    rows = session.execute(text(" ".join(q)), p).mappings().all()
    return {r["metric"]: r for r in rows}


def entity_refs(session, workspace_id, source, entity_type="app"):
    """Distinct entity_refs written for one source, in id order."""
    return [r[0] for r in session.execute(text("""
        SELECT DISTINCT entity_ref FROM metric_fact
        WHERE workspace_id = :ws AND source = :source AND entity_type = :et
          AND entity_ref <> '' ORDER BY entity_ref"""),
        {"ws": workspace_id, "source": source, "et": entity_type})]


def summary(session, workspace_id):
    """Per-source ingestion state — latest day, fact count, distinct metrics."""
    return session.execute(text("""
        SELECT source,
               COUNT(*)             AS facts,
               MAX(day)             AS last_day,
               MIN(day)             AS first_day,
               COUNT(DISTINCT metric) AS metrics,
               MAX(captured_at)     AS last_captured_at
        FROM metric_fact
        WHERE workspace_id = :ws
        GROUP BY source ORDER BY source
    """), {"ws": workspace_id}).mappings().all()


def series(session, workspace_id, *, source, metric, start, end,
           entity_type=None, entity_ref=None):
    """Ordered daily rows for one metric over a date window."""
    q = ["SELECT day, value, numerator, denominator, entity_type, entity_ref, dims",
         "FROM metric_fact",
         "WHERE workspace_id = :ws AND source = :source AND metric = :metric",
         "AND day >= :start AND day <= :end"]
    p = {"ws": workspace_id, "source": source, "metric": metric,
         "start": start, "end": end}
    if entity_type is not None:
        q.append("AND entity_type = :etype")
        p["etype"] = entity_type
    if entity_ref is not None:
        q.append("AND entity_ref = :eref")
        p["eref"] = entity_ref
    q.append("ORDER BY day, entity_ref")
    return session.execute(text(" ".join(q)), p).mappings().all()
