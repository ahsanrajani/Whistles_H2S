"""``llm_prompt`` / ``llm_panel_response`` access -- the Vantage AI-visibility
panel. Every function takes a ``Session`` and leaves the commit to the caller.
"""
import json

from sqlalchemy import text


def count(session, workspace_id) -> int:
    return session.execute(text(
        "SELECT count(*) FROM llm_prompt WHERE workspace_id = :ws"),
        {"ws": workspace_id}).scalar()


def add_prompt(session, workspace_id, prompt_text) -> int:
    return session.execute(text(
        "INSERT INTO llm_prompt (workspace_id, prompt_text) VALUES (:ws, :p) "
        "RETURNING id"), {"ws": workspace_id, "p": prompt_text}).scalar_one()


def list_prompts(session, workspace_id):
    return session.execute(text(
        "SELECT id, prompt_text, active, created_at FROM llm_prompt "
        "WHERE workspace_id = :ws ORDER BY id"), {"ws": workspace_id}).mappings().all()


def active_prompts(session, workspace_id):
    return session.execute(text(
        "SELECT id, prompt_text FROM llm_prompt "
        "WHERE workspace_id = :ws AND active = true ORDER BY id"),
        {"ws": workspace_id}).mappings().all()


def set_prompt_active(session, workspace_id, prompt_id, active: bool) -> None:
    session.execute(text(
        "UPDATE llm_prompt SET active = :a WHERE id = :id AND workspace_id = :ws"),
        {"a": active, "id": prompt_id, "ws": workspace_id})


def delete_prompt(session, workspace_id, prompt_id) -> None:
    session.execute(text(
        "DELETE FROM llm_prompt WHERE id = :id AND workspace_id = :ws"),
        {"id": prompt_id, "ws": workspace_id})


def record_response(session, workspace_id, prompt_id, *, provider, model, day,
                    response_text, mentions) -> None:
    session.execute(text("""
        INSERT INTO llm_panel_response
            (workspace_id, prompt_id, provider, model, day, response_text, mentions)
        VALUES (:ws, :pid, :provider, :model, :day, :text, CAST(:mentions AS jsonb))
    """), {"ws": workspace_id, "pid": prompt_id, "provider": provider, "model": model,
           "day": day, "text": response_text, "mentions": json.dumps(mentions)})


def record_error(session, workspace_id, prompt_id, *, model, day, error, provider="") -> None:
    session.execute(text("""
        INSERT INTO llm_panel_response
            (workspace_id, prompt_id, provider, model, day, response_text, mentions, error)
        VALUES (:ws, :pid, :provider, :model, :day, '', CAST('[]' AS jsonb), :err)
    """), {"ws": workspace_id, "pid": prompt_id, "provider": provider, "model": model,
           "day": day, "err": str(error)[:2000]})


def responses(session, workspace_id, *, since=None, limit=2000):
    q = ("SELECT r.id, r.prompt_id, p.prompt_text, r.provider, r.model, r.day, "
         "r.response_text, r.mentions, r.error "
         "FROM llm_panel_response r JOIN llm_prompt p ON p.id = r.prompt_id "
         "WHERE r.workspace_id = :ws")
    params = {"ws": workspace_id, "lim": limit}
    if since is not None:
        q += " AND r.day >= CAST(:since AS date)"
        params["since"] = since
    q += " ORDER BY r.day DESC, r.id DESC LIMIT :lim"
    return session.execute(text(q), params).mappings().all()
