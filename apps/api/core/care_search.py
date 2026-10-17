"""Cross-entity care search / autocomplete (build plan §5 / P3.9).

One query per entity, unioned and ranked:

* customers — name / handle / email / phone by trigram similarity + prefix
* cases     — a numeric id or a ``C-<id>`` reference
* messages  — full-text over ``case_message.body``

Backed by the pg_trgm and GIN indexes in Alembic 0018.
"""
import re

from sqlalchemy import text

_REF = re.compile(r"^\s*C-?(\d+)\s*$", re.I)
_DIGITS = re.compile(r"\d")


def search(session, workspace_id, q, *, limit=10) -> dict:
    q = (q or "").strip()
    if len(q) < 2 and not q.isdigit():
        return {"query": q, "results": []}
    results = []

    ref = _REF.match(q)
    if ref or q.isdigit():
        cid = int(ref.group(1) if ref else q)
        row = session.execute(text(
            'SELECT c.id, c.state, cu.display_name, cu.handle FROM "case" c '
            'JOIN customer cu ON cu.id = c.customer_id '
            'WHERE c.workspace_id = :ws AND c.id = :id'),
            {"ws": workspace_id, "id": cid}).first()
        if row:
            results.append({"type": "case", "id": row[0], "case_id": row[0],
                            "label": f"C-{row[0]} · {row[2] or row[3] or 'customer'}",
                            "detail": row[1], "score": 1.0})

    like = f"%{q.lower()}%"
    cust = session.execute(text("""
        SELECT id, display_name, handle, email, phone,
               GREATEST(similarity(lower(coalesce(display_name,'')), :q),
                        similarity(lower(coalesce(handle,'')), :q),
                        similarity(lower(coalesce(email,'')), :q),
                        similarity(lower(coalesce(phone,'')), :q)) AS sim
        FROM customer
        WHERE workspace_id = :ws
          AND (lower(coalesce(display_name,'')) LIKE :like
            OR lower(coalesce(handle,'')) LIKE :like
            OR lower(coalesce(email,'')) LIKE :like
            OR lower(coalesce(phone,'')) LIKE :like
            OR similarity(lower(coalesce(display_name,'')), :q) > 0.2)
        ORDER BY sim DESC NULLS LAST LIMIT :lim
    """), {"ws": workspace_id, "q": q.lower(), "like": like, "lim": limit}).mappings().all()
    for r in cust:
        latest = session.execute(text(
            'SELECT id FROM "case" WHERE customer_id = :cid ORDER BY last_activity_at DESC LIMIT 1'),
            {"cid": r["id"]}).scalar()
        results.append({
            "type": "customer", "id": r["id"], "case_id": latest,
            "label": r["display_name"] or r["handle"] or r["email"] or r["phone"],
            "detail": r["handle"] or r["email"], "score": float(r["sim"] or 0.0)})

    if not _DIGITS.search(q) or len(q) > 4:
        msgs = session.execute(text("""
            SELECT m.id, m.case_id, left(m.body, 160) AS snippet,
                   ts_rank(to_tsvector('english', m.body),
                           plainto_tsquery('english', :q)) AS rank
            FROM case_message m
            WHERE m.workspace_id = :ws
              AND to_tsvector('english', m.body) @@ plainto_tsquery('english', :q)
            ORDER BY rank DESC LIMIT :lim
        """), {"ws": workspace_id, "q": q, "lim": limit}).mappings().all()
        for r in msgs:
            results.append({"type": "message", "id": r["id"], "case_id": r["case_id"],
                            "label": r["snippet"], "detail": f"case C-{r['case_id']}",
                            "score": float(r["rank"] or 0.0)})

    results.sort(key=lambda x: x["score"], reverse=True)
    return {"query": q, "results": results[:limit]}
