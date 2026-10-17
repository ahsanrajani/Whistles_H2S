"""``ai_suggestion_cache`` access. Every function takes a ``Session`` and
leaves the commit to the caller."""
import json

from sqlalchemy import text


def get(session, case_id, kind) -> dict | None:
    row = session.execute(text("""
        SELECT fingerprint, suggestion, sources, mock, created_at
        FROM ai_suggestion_cache WHERE case_id = :c AND kind = :k
    """), {"c": case_id, "k": kind}).mappings().first()
    return dict(row) if row else None


def upsert(session, workspace_id, case_id, kind, *, fingerprint, suggestion,
          sources, mock) -> None:
    session.execute(text("""
        INSERT INTO ai_suggestion_cache
            (workspace_id, case_id, kind, fingerprint, suggestion, sources, mock)
        VALUES (:ws, :c, :k, :fp, :sugg, CAST(:src AS jsonb), :mock)
        ON CONFLICT (case_id, kind) DO UPDATE SET
            fingerprint = EXCLUDED.fingerprint, suggestion = EXCLUDED.suggestion,
            sources = EXCLUDED.sources, mock = EXCLUDED.mock,
            created_at = now()
    """), {"ws": workspace_id, "c": case_id, "k": kind, "fp": fingerprint,
           "sugg": suggestion, "src": json.dumps(sources), "mock": mock})
