"""``outbound_action`` access (P3.1) — record a platform write, and surface the
ones a platform rejected so an agent can rework them."""
import json

from sqlalchemy import text


def record(session, *, workspace_id, platform, action, target_ref, request,
           response=None, external_id=None, state="pending", error=None,
           actor=None) -> int:
    row = session.execute(text("""
        INSERT INTO outbound_action
            (workspace_id, platform, action, target_ref, request, response,
             external_id, state, error, actor)
        VALUES (:ws, :platform, :action, :ref, CAST(:req AS jsonb),
                CAST(:resp AS jsonb), :ext, :state, :error, :actor)
        RETURNING id
    """), {"ws": workspace_id, "platform": platform, "action": action,
           "ref": target_ref, "req": json.dumps(request or {}),
           "resp": json.dumps(response) if response is not None else None,
           "ext": external_id, "state": state, "error": error,
           "actor": None if actor is None else str(actor)}).scalar_one()
    return int(row)


def set_state(session, action_id, state, *, error=None, response=None,
              external_id=None) -> None:
    session.execute(text("""
        UPDATE outbound_action SET
            state = :state,
            error = COALESCE(:error, error),
            response = COALESCE(CAST(:resp AS jsonb), response),
            external_id = COALESCE(:ext, external_id),
            updated_at = now()
        WHERE id = :id
    """), {"id": action_id, "state": state, "error": error, "ext": external_id,
           "resp": json.dumps(response) if response is not None else None})


def get(session, action_id):
    return session.execute(text(
        "SELECT id, workspace_id, platform, action, target_ref, request, state, "
        "external_id FROM outbound_action WHERE id = :id"),
        {"id": action_id}).mappings().first()


def update_request(session, action_id, request) -> None:
    session.execute(text(
        "UPDATE outbound_action SET request = CAST(:r AS jsonb), updated_at = now() "
        "WHERE id = :id AND state = 'pending'"),
        {"id": action_id, "r": json.dumps(request or {})})


def mark_rejected(session, action_id, reason) -> None:
    """A platform rejected an already-submitted write (Google review replies can
    be). The row moves to ``rejected`` and shows up in :func:`pending_rework`."""
    set_state(session, action_id, "rejected", error=str(reason)[:2000])


def mark_reworked(session, action_id) -> None:
    set_state(session, action_id, "reworked")


def pending_rework(session, workspace_id):
    return session.execute(text("""
        SELECT id, platform, action, target_ref, external_id, error, created_at
        FROM outbound_action
        WHERE workspace_id = :ws AND state = 'rejected'
        ORDER BY created_at DESC
    """), {"ws": workspace_id}).mappings().all()


def recent(session, workspace_id, limit=50):
    return session.execute(text("""
        SELECT id, platform, action, target_ref, external_id, state, error, created_at
        FROM outbound_action WHERE workspace_id = :ws
        ORDER BY created_at DESC LIMIT :lim
    """), {"ws": workspace_id, "lim": limit}).mappings().all()
