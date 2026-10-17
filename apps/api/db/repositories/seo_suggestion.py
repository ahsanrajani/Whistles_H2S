"""``seo_suggestion`` access -- LLM-generated SEO recommendations. Every
function takes a ``Session`` and leaves the commit to the caller."""
import json

from sqlalchemy import text


def record(session, workspace_id, *, provider, model, prompt, raw_text,
          suggestions, error=None) -> dict:
    row = session.execute(text("""
        INSERT INTO seo_suggestion (workspace_id, provider, model, prompt, raw_text,
                                    suggestions, error)
        VALUES (:ws, :provider, :model, :prompt, :raw, CAST(:sugg AS jsonb), :err)
        RETURNING id, provider, model, prompt, raw_text, suggestions, error, created_at
    """), {"ws": workspace_id, "provider": provider, "model": model, "prompt": prompt,
           "raw": raw_text, "sugg": json.dumps(suggestions), "err": error}).mappings().one()
    return dict(row)


def latest(session, workspace_id) -> dict | None:
    row = session.execute(text("""
        SELECT id, provider, model, prompt, raw_text, suggestions, error, created_at
        FROM seo_suggestion WHERE workspace_id = :ws
        ORDER BY created_at DESC LIMIT 1
    """), {"ws": workspace_id}).mappings().first()
    return dict(row) if row else None
