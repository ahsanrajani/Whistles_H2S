"""Care console API (build plan §5 / P3.4 backend).

A single case's lifecycle: list per tab, full detail (messages + notes +
timeline + customer), inbound ingestion (what a channel webhook or the
collector calls), and the console actions on one case — reply through the
write layer, AI-assisted suggestion, note, assign, reassign, transition,
survey issue/response. Roster/queue/performance, held-reply approval,
scheduling, block/unblock, export and search live in ``care_ops.py`` (split
out to stay under the 600-line file limit).
"""
from fastapi import APIRouter, Body, Depends, Request
from sqlalchemy import text

import app as _app
from core import ai_assist, care_audit, cases, realtime, routing, surveys
from integrations import write

from .deps import (ApiError, Ctx, assert_case_access, care_visibility_clause,
                   guard, is_agent_scoped, require_feature)

router = APIRouter(prefix="/api/v1", tags=["care"])

_TABS = {
    "queue": "state <> 'closed' AND assignee_id IS NULL",
    "assigned": "state <> 'closed' AND assignee_id IS NOT NULL",
    "mine": "state <> 'closed' AND assignee_id = :me",
    "hold": "state = 'internal_hold'",
    "closed": "state = 'closed'",
}


@router.get("/care/cases")
def list_cases(request: Request, tab: str = "queue", limit: int = 50,
               ctx: Ctx = Depends(guard("care", "view"))):
    if tab not in _TABS:
        ctx.close()
        raise ApiError(400, f"unknown tab {tab!r}")
    where = _TABS[tab]
    params = {"ws": ctx.ws_id, "lim": min(limit, 200)}
    if ":me" in where:
        params["me"] = ctx.session.get("user_id")
    # An agent-scoped user (plain "agent" role, no Care oversight) only ever
    # sees their own assigned cases, regardless of which tab was asked for --
    # Hamza: "the agent accounts should be able to access only the
    # conversations assigned to them, nothing else." This naturally empties
    # "queue" (unassigned) for them and collapses "assigned"/"closed" down
    # to their own.
    scope_sql, scope_params = care_visibility_clause(ctx)
    params.update(scope_params)
    rows = ctx.db.session.execute(text(f"""
        SELECT c.id, c.state, c.channel, c.assignee_id, c.opened_at, c.priority AS priority_set, c.tags,
               c.last_activity_at, c.first_response_at, c.closed_at,
               cu.display_name, cu.handle, cu.platform,
               EXTRACT(EPOCH FROM (now() - c.opened_at))          AS opened_age_s,
               EXTRACT(EPOCH FROM (now() - c.last_activity_at))   AS waiting_seconds,
               (SELECT count(*) FROM case_message m WHERE m.case_id = c.id) AS messages
        FROM "case" c JOIN customer cu ON cu.id = c.customer_id
        WHERE c.workspace_id = :ws AND {where} AND {scope_sql}
        ORDER BY c.last_activity_at DESC LIMIT :lim
    """), params).mappings().all()
    frt_sla = int(routing.policy(ctx.db.session, ctx.ws_id)["first_response_sla"])
    ctx.close()

    def enrich(r):
        d = dict(r)
        age = float(d.pop("opened_age_s") or 0.0)
        d["waiting_seconds"] = float(d["waiting_seconds"] or 0.0)
        if d["state"] == "closed":
            d["sla_state"] = None
        elif d["first_response_at"] is not None:
            d["sla_state"] = "ok"
        elif age > frt_sla:
            d["sla_state"] = "breached"
        elif age > frt_sla - 300:
            d["sla_state"] = "at_risk"
        else:
            d["sla_state"] = "ok"
        # A priority a macro / agent set explicitly outranks the SLA-derived one.
        d["priority"] = (
            "high" if d["sla_state"] == "breached" or d["priority_set"] in ("high", "urgent")
            else "elevated" if (d["assignee_id"] is None and d["sla_state"] == "at_risk")
            else "normal")
        return d

    return {"tab": tab, "cases": [enrich(r) for r in rows]}


def _resolve_actor_usernames(session, events: list[dict], notes: list[dict]) -> None:
    """Every event/note's raw actor/author id (and an assign/reassign
    event's target id) resolved to a real username, in place. Hamza: "with
    every message, assignment/reassignment authorship/ownership is logged
    and displayed eg admin assigned this convo to hamza_rep etc." -- the
    ids were always recorded (core/cases.py::_event), just never resolved
    to anything a human reads."""
    ids: set[int] = set()
    for e in events:
        if e.get("actor") and str(e["actor"]).isdigit():
            ids.add(int(e["actor"]))
        detail = e.get("detail") or {}
        for key in ("assignee_id", "to_user_id"):
            if detail.get(key) is not None:
                ids.add(int(detail[key]))
    for n in notes:
        if n.get("author_id") is not None:
            ids.add(int(n["author_id"]))
    if not ids:
        return
    rows = session.execute(text('SELECT id, username FROM "user" WHERE id = ANY(:ids)'),
                           {"ids": list(ids)}).all()
    usernames = {uid: uname for uid, uname in rows}
    for e in events:
        actor_id = int(e["actor"]) if e.get("actor") and str(e["actor"]).isdigit() else None
        e["actor_username"] = usernames.get(actor_id) if actor_id is not None else None
        detail = e.get("detail") or {}
        if detail.get("assignee_id") is not None:
            detail["assignee_username"] = usernames.get(int(detail["assignee_id"]))
        if detail.get("to_user_id") is not None:
            detail["to_username"] = usernames.get(int(detail["to_user_id"]))
    for n in notes:
        n["author_username"] = (usernames.get(int(n["author_id"]))
                                if n.get("author_id") is not None else None)


@router.get("/care/cases/{case_id}")
def case_detail(case_id: int, ctx: Ctx = Depends(guard("care", "view"))):
    assert_case_access(ctx, case_id)
    s = ctx.db.session
    case = s.execute(text("""
        SELECT c.*, cu.display_name, cu.handle, cu.platform, cu.email, cu.phone,
               cu.preferred_name, cu.other_handles, cu.location, cu.country,
               cu.language, cu.timezone, cu.segment, cu.account_status, cu.vip,
               cu.blocked, cu.preferred_channel, cu.tags, cu.notes,
               cu.created_at AS customer_since
        FROM "case" c JOIN customer cu ON cu.id = c.customer_id
        WHERE c.id = :c AND c.workspace_id = :ws
    """), {"c": case_id, "ws": ctx.ws_id}).mappings().first()
    if not case:
        ctx.close()
        raise ApiError(404, "case not found")
    msgs = [dict(m) for m in cases.messages(s, case_id)]
    notes = [dict(n) for n in s.execute(text(
        "SELECT id, author_id, body, created_at FROM case_note "
        "WHERE case_id = :c ORDER BY created_at"), {"c": case_id}).mappings().all()]
    events = [dict(e) for e in cases.timeline(s, case_id)]
    _resolve_actor_usernames(s, events, notes)
    history = [dict(h) for h in s.execute(text("""
        SELECT id, state, channel, opened_at, closed_at FROM "case"
        WHERE customer_id = :cust AND workspace_id = :ws AND id <> :c
        ORDER BY opened_at DESC LIMIT 25
    """), {"cust": case["customer_id"], "ws": ctx.ws_id, "c": case_id}).mappings().all()]
    ctx.close()
    customer_fields = ("display_name", "handle", "platform", "email", "phone",
                       "preferred_name", "other_handles", "location", "country",
                       "language", "timezone", "segment", "account_status", "vip",
                       "blocked", "preferred_channel", "tags", "notes")
    return {
        "case": dict(case),
        "customer": {"id": case["customer_id"],
                     **{f: case[f] for f in customer_fields},
                     "customer_since": case["customer_since"]},
        "messages": msgs, "notes": notes, "timeline": events, "history": history,
    }


# Editable customer-profile fields (Hamza, Customer panel screenshot:
# "these details should be editable"). platform/handle are deliberately
# absent -- core/cases.py::resolve_customer()'s match key; editing them here
# could silently stop matching this customer's future real messages.
_CUSTOMER_TEXT_FIELDS = (
    "display_name", "preferred_name", "email", "phone", "other_handles",
    "location", "country", "language", "timezone", "segment",
    "account_status", "preferred_channel", "tags", "notes",
)
_CUSTOMER_BOOL_FIELDS = ("vip", "blocked")


@router.put("/care/customers/{customer_id}")
def update_customer(customer_id: int, body: dict | None = Body(default=None),
                    ctx: Ctx = Depends(guard("care", "edit"))):
    owned = ctx.db.session.execute(text(
        'SELECT 1 FROM customer WHERE id = :c AND workspace_id = :ws'),
        {"c": customer_id, "ws": ctx.ws_id}).first()
    if not owned:
        ctx.close()
        raise ApiError(404, "customer not found")
    if is_agent_scoped(ctx):
        # an agent may only edit a customer they actually have a case with
        theirs = ctx.db.session.execute(text(
            'SELECT 1 FROM "case" WHERE customer_id = :c AND workspace_id = :ws '
            'AND assignee_id = :me'),
            {"c": customer_id, "ws": ctx.ws_id, "me": ctx.session.get("user_id")}).first()
        if not theirs:
            ctx.close()
            raise ApiError(404, "customer not found")
    b = body or {}
    sets, params = [], {"c": customer_id}
    for field in _CUSTOMER_TEXT_FIELDS:
        if field in b:
            value = b[field]
            sets.append(f"{field} = :{field}")
            params[field] = (str(value).strip() or None) if value is not None else None
    for field in _CUSTOMER_BOOL_FIELDS:
        if field in b:
            sets.append(f"{field} = :{field}")
            params[field] = bool(b[field]) if b[field] is not None else None
    if not sets:
        ctx.close()
        raise ApiError(400, "no editable fields in body")
    ctx.db.session.execute(text(
        f'UPDATE customer SET {", ".join(sets)} WHERE id = :c'), params)
    ctx.db.commit()
    actor, ws = ctx.session.get("user_id"), ctx.ws_id
    ctx.close()
    care_audit.emit("care.customer_update", actor=actor, ws=ws, target=customer_id,
                    after={k: v for k, v in params.items() if k != "c"})
    return {"ok": True}


@router.post("/care/cases/ingest")
def ingest(body: dict | None = Body(default=None),
           ctx: Ctx = Depends(guard("care", "edit"))):
    b = body or {}
    if not b.get("platform") or not b.get("body"):
        ctx.close()
        raise ApiError(400, "platform and body are required")
    out = cases.ingest_message(
        ctx.db.session, ctx.ws_id, platform=b["platform"], handle=b.get("handle"),
        email=b.get("email"), phone=b.get("phone"), display_name=b.get("display_name"),
        body=b["body"], channel=b.get("channel"), platform_ref=b.get("platform_ref"))
    if out["new"]:
        routing.arm_sla_timers(ctx.db.session, ctx.ws_id, out["case_id"])
    ctx.db.commit()
    actor, ws = ctx.session.get("user_id"), ctx.ws_id
    ctx.close()
    care_audit.emit("care.ingest", actor=actor, ws=ws, target=out["case_id"],
                    after={"platform": b["platform"], "new": out["new"]})
    channel = b.get("channel") or b["platform"]
    event_kind = "meta_message" if channel in {
        "facebook", "instagram", "messenger", "instagram_dm",
    } else "ingest"
    realtime.publish(f"queue:{ws}", {"kind": event_kind, "case_id": out["case_id"],
                                     "new": out["new"], "channel": channel})
    return out


@router.post("/care/cases/{case_id}/reply")
def reply(case_id: int, body: dict | None = Body(default=None),
          ctx: Ctx = Depends(guard("care", "edit"))):
    b = body or {}
    text_body, platform = (b.get("text") or "").strip(), b.get("platform")
    if not text_body or not platform:
        ctx.close()
        raise ApiError(400, "text and platform are required")
    assert_case_access(ctx, case_id)
    s, actor = ctx.db.session, ctx.session.get("user_id")
    case = s.execute(text('SELECT c.channel, cu.handle FROM "case" c '
                          'JOIN customer cu ON cu.id=c.customer_id '
                          'WHERE c.id=:c AND c.workspace_id=:ws'),
                     {"c": case_id, "ws": ctx.ws_id}).first()
    if not case:
        ctx.close()
        raise ApiError(404, "case not found")
    try:
        client = write.client_for(platform, _app.keys(ctx.ws_id))
    except ValueError as exc:
        ctx.close()
        raise ApiError(400, str(exc))
    req = {"text": text_body, "case_id": case_id, "channel": case[0]}
    is_dm = case[0] in {"messenger", "instagram_dm"}
    target_ref = b.get("target_ref") or (case[1] if is_dm else None)
    action = "reply_dm" if is_dm else "reply_public"
    if b.get("hold"):
        # supervisor intervention (P3.5): record it pending, don't send
        aid = client.create_pending(s, ctx.ws_id, action=action,
                                    target_ref=target_ref, request=req,
                                    actor=actor)
        cases._event(s, case_id, "reply_pending", actor, outbound_action_id=aid)
        s.commit()
        held_ws = ctx.ws_id
        ctx.close()
        realtime.publish(f"queue:{held_ws}", {"kind": "reply_pending", "case_id": case_id})
        realtime.publish(f"case:{case_id}", {"kind": "reply_pending"})
        return {"ok": True, "state": "pending", "outbound_action_id": aid}

    send = client.reply_dm if is_dm else client.reply_public
    result = send(s, ctx.ws_id, target_ref=target_ref,
                  text=text_body, actor=actor, channel=case[0], case_id=case_id)
    # DM sends: dm_sync.py's next poll re-fetches this same message from
    # Meta's Conversations API and dedupes on case_message.platform_ref
    # matching the message's own Graph id (_already_seen). Recording
    # target_ref (the recipient) here instead of that id meant every live
    # DM reply went unrecognised on the next poll and got duplicated as a
    # second, actor-less row (Hamza screenshot, C-117, 2026-09-12). Public
    # replies are a separate, item-table-based ingestion path with no such
    # re-poll, so their platform_ref (the comment/post replied to) is
    # untouched.
    message_ref = result.external_id if (is_dm and result.external_id) else target_ref
    cases.post_reply(s, case_id, ctx.ws_id, body=text_body, channel=case[0],
                     platform_ref=message_ref, actor=actor,
                     outbound_action_id=result.action_id)
    s.commit()
    reply_ws = ctx.ws_id
    ctx.close()
    _app.audit(actor=actor, tenant_id=reply_ws, action="care.reply",
               target=case_id, after={"platform": platform, "state": result.state})
    realtime.publish(f"queue:{reply_ws}", {"kind": "reply", "case_id": case_id})
    realtime.publish(f"case:{case_id}", {"kind": "reply", "state": result.state})
    return {"ok": result.state == "sent", "state": result.state,
            "outbound_action_id": result.action_id, "external_id": result.external_id,
            "error": result.error}


@router.post("/care/cases/{case_id}/suggest")
def suggest(case_id: int, body: dict | None = Body(default=None),
            ctx: Ctx = Depends(guard("care", "view"))):
    """AI reply assistance (P3.7). Returns text only — never sends anything;
    the agent must paste it into the reply box and submit explicitly."""
    require_feature(ctx, "cap.ai_assist")
    assert_case_access(ctx, case_id)
    b = body or {}
    owned = ctx.db.session.execute(text(
        'SELECT 1 FROM "case" WHERE id = :c AND workspace_id = :ws'),
        {"c": case_id, "ws": ctx.ws_id}).first()
    if not owned:
        ctx.close()
        raise ApiError(404, "case not found")
    try:
        out = ai_assist.suggest(ctx.db.session, ctx.ws_id, case_id,
                                kind=b.get("kind", "reply"), draft=b.get("draft"),
                                keys=_app.keys(ctx.ws_id), force=bool(b.get("force")))
    except ValueError as exc:
        ctx.close()
        raise ApiError(400, str(exc))
    ctx.db.commit()  # a "reply" suggestion may have just written to ai_suggestion_cache
    ctx.close()
    return out


@router.post("/care/cases/{case_id}/note")
def note(case_id: int, body: dict | None = Body(default=None),
         ctx: Ctx = Depends(guard("care", "edit"))):
    b = body or {}
    if not (b.get("body") or "").strip():
        ctx.close()
        raise ApiError(400, "body is required")
    assert_case_access(ctx, case_id)
    actor = ctx.session.get("user_id")
    nid = cases.add_note(ctx.db.session, case_id, actor, b["body"], actor=actor)
    ctx.db.commit()
    ws = ctx.ws_id
    ctx.close()
    care_audit.emit("care.note", actor=actor, ws=ws, target=case_id,
                    after={"note_id": nid})
    return {"ok": True, "note_id": nid}


@router.post("/care/cases/{case_id}/assign")
def assign_case(case_id: int, body: dict | None = Body(default=None),
                ctx: Ctx = Depends(guard("care", "edit"))):
    assert_case_access(ctx, case_id)
    b = body or {}
    actor = ctx.session.get("user_id")
    uid = b.get("user_id")
    if uid:
        cases.assign(ctx.db.session, case_id, int(uid), actor=actor)
        chosen = int(uid)
    else:
        chosen = routing.assign_next(ctx.db.session, ctx.ws_id, case_id, actor=actor)
    ctx.db.commit()
    ws = ctx.ws_id
    ctx.close()
    care_audit.emit("care.assign", actor=actor, ws=ws, target=case_id,
                    after={"assignee_id": chosen, "manual": bool(uid)})
    realtime.publish(f"queue:{ws}", {"kind": "assigned", "case_id": case_id,
                                     "assignee_id": chosen})
    return {"ok": chosen is not None, "assignee_id": chosen}


@router.post("/care/cases/{case_id}/reassign")
def reassign_case(case_id: int, body: dict | None = Body(default=None),
                  ctx: Ctx = Depends(guard("care", "edit"))):
    b = body or {}
    if not b.get("user_id") or not (b.get("reason") or "").strip():
        ctx.close()
        raise ApiError(400, "user_id and reason are required")
    assert_case_access(ctx, case_id)
    actor = ctx.session.get("user_id")
    try:
        routing.reassign(ctx.db.session, case_id, int(b["user_id"]),
                         actor=actor, reason=b["reason"])
    except cases.CaseError as exc:
        ctx.close()
        raise ApiError(400, str(exc))
    ctx.db.commit()
    ws = ctx.ws_id
    ctx.close()
    care_audit.emit("care.reassign", actor=actor, ws=ws, target=case_id,
                    after={"assignee_id": int(b["user_id"]), "reason": b["reason"]})
    realtime.publish(f"queue:{ws}", {"kind": "reassigned", "case_id": case_id,
                                     "assignee_id": int(b["user_id"])})
    realtime.publish(f"case:{case_id}", {"kind": "reassigned"})
    return {"ok": True}


@router.post("/care/cases/{case_id}/transition")
def transition_case(case_id: int, body: dict | None = Body(default=None),
                    ctx: Ctx = Depends(guard("care", "edit"))):
    assert_case_access(ctx, case_id)
    b = body or {}
    to_state = b.get("state")
    actor = ctx.session.get("user_id")
    try:
        prior_assignee = ctx.db.session.execute(text(
            'SELECT assignee_id FROM "case" WHERE id=:c'), {"c": case_id}).scalar()
        cases.transition(ctx.db.session, case_id, to_state, actor=actor,
                         closure_category=b.get("closure_category"))
        if to_state == "closed":
            if prior_assignee:
                routing.on_case_closed(ctx.db.session, ctx.ws_id, prior_assignee,
                                       actor="routing")
            surveys.on_case_closed(ctx.db.session, ctx.ws_id, case_id)
    except cases.CaseError as exc:
        ctx.close()
        raise ApiError(400, str(exc))
    ctx.db.commit()
    ws = ctx.ws_id
    ctx.close()
    _app.audit(actor=actor, tenant_id=ws, action="care.state_change",
               target=case_id, after={"state": to_state})
    if to_state == "closed":
        care_audit.emit(care_audit.CLOSURE_ACTION, actor=actor, ws=ws,
                        target=case_id,
                        after={"closure_category": b.get("closure_category")})
    realtime.publish(f"queue:{ws}", {"kind": "state_change", "case_id": case_id,
                                     "state": to_state})
    realtime.publish(f"case:{case_id}", {"kind": "state_change", "state": to_state})
    return {"ok": True, "state": to_state}


@router.post("/care/cases/{case_id}/survey")
def issue_survey(case_id: int, body: dict | None = Body(default=None),
                 ctx: Ctx = Depends(guard("care", "edit"))):
    """Issue a post-resolution CSAT survey for a case (P4.7). Returns the
    response token a tokenised link would carry."""
    require_feature(ctx, "cap.surveys")
    assert_case_access(ctx, case_id)
    b = body or {}
    actor = ctx.session.get("user_id")
    owned = ctx.db.session.execute(text(
        'SELECT 1 FROM "case" WHERE id = :c AND workspace_id = :ws'),
        {"c": case_id, "ws": ctx.ws_id}).first()
    if not owned:
        ctx.close()
        raise ApiError(404, "case not found")
    out = surveys.issue(ctx.db.session, ctx.ws_id, case_id=case_id,
                        survey_id=b.get("survey_id"))
    ctx.db.commit()
    ws = ctx.ws_id
    ctx.close()
    care_audit.emit("care.survey_issue", actor=actor, ws=ws, target=case_id,
                    after={"token": out["token"]})
    return out


@router.post("/care/surveys/respond")
def respond_survey(body: dict | None = Body(default=None),
                   ctx: Ctx = Depends(guard("care", "edit"))):
    """Record a survey score against its token (P4.7). Agent-assisted capture;
    a public tokenised link reuses ``surveys.record``."""
    b = body or {}
    actor = ctx.session.get("user_id")
    try:
        out = surveys.record(ctx.db.session, ctx.ws_id, b.get("token"),
                             b.get("score"), comment=b.get("comment"))
    except surveys.SurveyError as exc:
        ctx.close()
        raise ApiError(400, str(exc))
    ctx.db.commit()
    ws = ctx.ws_id
    ctx.close()
    care_audit.emit("care.survey_response", actor=actor, ws=ws,
                    target=out["id"], after={"bucket": out["bucket"]})
    return out
