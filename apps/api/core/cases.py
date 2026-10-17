"""The case engine (build plan §5 / P3.2).

* ``resolve_customer`` — one ``customer`` per person across channels, matched on
  (platform, handle) then email then phone.
* ``ingest_message`` — an inbound/outbound message for a customer joins an open
  case whose last activity is within the two-hour consolidation window;
  otherwise it opens a new case.
* ``transition`` — the state machine
  Open → Assigned → In Progress → Internal Hold → Pending Approval → Closed
  (Closed → Open to reopen). Closing requires a ``closure_category``.

Every mutation writes a ``case_event`` — the log the SLA reports (P3.3) and the
care audit (P3.10) read.
"""
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

CONSOLIDATION_WINDOW = timedelta(hours=2)

OPEN, ASSIGNED, IN_PROGRESS, INTERNAL_HOLD, PENDING_APPROVAL, CLOSED = (
    "open", "assigned", "in_progress", "internal_hold", "pending_approval", "closed")
STATES = (OPEN, ASSIGNED, IN_PROGRESS, INTERNAL_HOLD, PENDING_APPROVAL, CLOSED)

_TRANSITIONS = {
    OPEN: {ASSIGNED, IN_PROGRESS, CLOSED},
    ASSIGNED: {IN_PROGRESS, INTERNAL_HOLD, PENDING_APPROVAL, CLOSED, ASSIGNED},
    IN_PROGRESS: {INTERNAL_HOLD, PENDING_APPROVAL, ASSIGNED, CLOSED},
    INTERNAL_HOLD: {IN_PROGRESS, ASSIGNED, CLOSED},
    PENDING_APPROVAL: {IN_PROGRESS, ASSIGNED, CLOSED},
    CLOSED: {OPEN},
}


class CaseError(Exception):
    """An invalid case operation."""


def _now():
    return datetime.now(timezone.utc)


def _event(session, case_id, kind, actor, **detail):
    session.execute(text(
        "INSERT INTO case_event (case_id, actor, kind, detail) "
        "VALUES (:c, :a, :k, CAST(:d AS jsonb))"),
        {"c": case_id, "a": None if actor is None else str(actor), "k": kind,
         "d": json.dumps(detail)})


def resolve_customer(session, workspace_id, *, platform=None, handle=None,
                     email=None, phone=None, display_name=None) -> int:
    for field, value in (("email", email), ("phone", phone)):
        if value:
            row = session.execute(text(
                f"SELECT id FROM customer WHERE workspace_id=:ws AND {field}=:v "
                "ORDER BY id LIMIT 1"), {"ws": workspace_id, "v": value}).first()
            if row:
                _touch_customer(session, row[0], email=email, phone=phone,
                                display_name=display_name)
                return row[0]
    if platform and handle:
        row = session.execute(text(
            "SELECT id FROM customer WHERE workspace_id=:ws AND platform=:p AND handle=:h "
            "ORDER BY id LIMIT 1"), {"ws": workspace_id, "p": platform, "h": handle}).first()
        if row:
            _touch_customer(session, row[0], email=email, phone=phone,
                            display_name=display_name)
            return row[0]
    return session.execute(text("""
        INSERT INTO customer (workspace_id, display_name, platform, handle, email, phone)
        VALUES (:ws, :name, :p, :h, :e, :ph) RETURNING id
    """), {"ws": workspace_id, "name": display_name, "p": platform, "h": handle,
           "e": email, "ph": phone}).scalar_one()


def _touch_customer(session, customer_id, *, email=None, phone=None, display_name=None):
    session.execute(text("""
        UPDATE customer SET
            email = COALESCE(email, :e),
            phone = COALESCE(phone, :ph),
            display_name = COALESCE(display_name, :name)
        WHERE id = :id
    """), {"id": customer_id, "e": email, "ph": phone, "name": display_name})


def ingest_message(session, workspace_id, *, platform, handle=None, body,
                   channel=None, platform_ref=None, permalink=None, sent_at=None,
                   direction="inbound", email=None, phone=None, display_name=None,
                   actor=None, outbound_action_id=None) -> dict:
    """Route a message into a case (new or consolidated). Returns
    ``{"case_id", "customer_id", "new"}``."""
    sent_at = sent_at or _now()
    channel = channel or platform
    customer_id = resolve_customer(
        session, workspace_id, platform=platform, handle=handle, email=email,
        phone=phone, display_name=display_name)

    row = session.execute(text("""
        SELECT id FROM "case"
        WHERE workspace_id = :ws AND customer_id = :cid AND state <> 'closed'
          AND (:ts - last_activity_at) <= :win
        ORDER BY last_activity_at DESC LIMIT 1
    """), {"ws": workspace_id, "cid": customer_id, "ts": sent_at,
           "win": CONSOLIDATION_WINDOW}).first()

    new = row is None
    if new:
        case_id = session.execute(text("""
            INSERT INTO "case" (workspace_id, customer_id, channel, state,
                                opened_at, last_activity_at)
            VALUES (:ws, :cid, :ch, 'open', :ts, :ts) RETURNING id
        """), {"ws": workspace_id, "cid": customer_id, "ch": channel, "ts": sent_at}).scalar_one()
        _event(session, case_id, "created", actor, channel=channel,
               customer_id=customer_id)
    else:
        case_id = row[0]

    session.execute(text("""
        INSERT INTO case_message (case_id, workspace_id, direction, channel,
                                  platform_ref, permalink, author, body, sent_at,
                                  outbound_action_id)
        VALUES (:c, :ws, :dir, :ch, :ref, :perma, :au, :body, :ts, :oa)
    """), {"c": case_id, "ws": workspace_id, "dir": direction, "ch": channel,
           "ref": platform_ref, "perma": permalink,
           "au": handle if direction == "inbound" else actor,
           "body": body, "ts": sent_at, "oa": outbound_action_id})

    session.execute(text("""
        UPDATE "case" SET
            last_activity_at = GREATEST(last_activity_at, :ts),
            first_response_at = CASE
                WHEN :dir = 'outbound' AND first_response_at IS NULL THEN :ts
                ELSE first_response_at END
        WHERE id = :c
    """), {"c": case_id, "ts": sent_at, "dir": direction})

    _event(session, case_id, "message_out" if direction == "outbound" else "message_in",
           actor, platform_ref=platform_ref, channel=channel)
    if direction == "inbound":
        from core import macro_rules, routing   # lazy: both import this module
        if new:                                 # assign first, so macro rules see the assignee
            macro_rules.safe(session, routing.auto_assign_new_case, workspace_id, case_id)
        macro_rules.safe(session, macro_rules.on_inbound, workspace_id, case_id, new=new,
                         body=body, channel=channel, sent_at=sent_at)
    return {"case_id": case_id, "customer_id": customer_id, "new": new}


def post_reply(session, case_id, workspace_id, *, body, channel, actor,
               platform_ref=None, outbound_action_id=None, at=None) -> None:
    """Append an outbound reply to a specific case (the console reply box). Sets
    ``first_response_at`` if this is the first reply and moves an ``open`` case
    to ``in_progress``."""
    at = at or _now()
    session.execute(text("""
        INSERT INTO case_message (case_id, workspace_id, direction, channel,
                                  platform_ref, author, body, sent_at, outbound_action_id)
        VALUES (:c, :ws, 'outbound', :ch, :ref, :au, :body, :ts, :oa)
    """), {"c": case_id, "ws": workspace_id, "ch": channel, "ref": platform_ref,
           "au": None if actor is None else str(actor), "body": body, "ts": at,
           "oa": outbound_action_id})
    session.execute(text("""
        UPDATE "case" SET
            last_activity_at = GREATEST(last_activity_at, :ts),
            first_response_at = COALESCE(first_response_at, :ts),
            state = CASE WHEN state = 'open' THEN 'in_progress' ELSE state END
        WHERE id = :c
    """), {"c": case_id, "ts": at})
    _event(session, case_id, "message_out", actor, platform_ref=platform_ref,
           channel=channel)


def assign(session, case_id, user_id, *, actor=None, **detail) -> None:
    cur = _state(session, case_id)
    to = ASSIGNED if cur == OPEN else cur
    session.execute(text(
        'UPDATE "case" SET assignee_id = :u, state = :s, last_activity_at = now() '
        'WHERE id = :c'), {"u": user_id, "s": to, "c": case_id})
    _event(session, case_id, "assigned", actor, assignee_id=user_id, **detail)


def add_note(session, case_id, author_id, body, *, actor=None) -> int:
    nid = session.execute(text(
        "INSERT INTO case_note (case_id, author_id, body) VALUES (:c, :a, :b) RETURNING id"),
        {"c": case_id, "a": author_id, "b": body}).scalar_one()
    _event(session, case_id, "note", actor or author_id, note_id=nid)
    return int(nid)


def transition(session, case_id, to_state, *, actor=None, closure_category=None) -> None:
    if to_state not in STATES:
        raise CaseError(f"unknown state {to_state!r}")
    cur = _state(session, case_id)
    if to_state not in _TRANSITIONS.get(cur, set()):
        raise CaseError(f"{cur} → {to_state} is not allowed")
    if to_state == CLOSED and not closure_category:
        raise CaseError("a closure category is required to close a case")
    session.execute(text("""
        UPDATE "case" SET
            state = :s,
            closure_category = CASE WHEN :s = 'closed' THEN :cc
                                    WHEN :s = 'open' THEN NULL
                                    ELSE closure_category END,
            closed_at = CASE WHEN :s = 'closed' THEN now() ELSE NULL END,
            last_activity_at = now()
        WHERE id = :c
    """), {"c": case_id, "s": to_state, "cc": closure_category})
    _event(session, case_id, "closed" if to_state == CLOSED else "state_change",
           actor, from_state=cur, to_state=to_state, closure_category=closure_category)


def _state(session, case_id) -> str:
    row = session.execute(text('SELECT state FROM "case" WHERE id = :c'),
                          {"c": case_id}).first()
    if not row:
        raise CaseError(f"no case {case_id}")
    return row[0]


def timeline(session, case_id):
    return session.execute(text(
        "SELECT kind, actor, detail, at FROM case_event WHERE case_id = :c ORDER BY at, id"),
        {"c": case_id}).mappings().all()


def messages(session, case_id):
    return session.execute(text(
        "SELECT direction, channel, author, body, sent_at, platform_ref, permalink "
        "FROM case_message WHERE case_id = :c ORDER BY sent_at, id"),
        {"c": case_id}).mappings().all()
