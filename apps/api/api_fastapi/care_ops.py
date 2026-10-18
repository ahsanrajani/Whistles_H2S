"""Care supervisor + operational surfaces (build plan §5 / P3.5, P3.8), split
out of care.py (which had grown past the 600-line file limit).
Presence/roster/queue health/performance, the held-reply approval
queue, scheduled-message and block/unblock actions, case export, and search
— everything that isn't a single case's own read/reply/note/assign/transition
lifecycle (that stays in care.py).
"""
from datetime import datetime

from fastapi import APIRouter, Body, Depends
from fastapi.responses import Response
from sqlalchemy import text

import app as _app
from core import care_audit, care_search, case_export, cases, presence, realtime, routing
from db import repositories as repo
from integrations import write
from jobs import runner

from .deps import ApiError, Ctx, assert_case_access, guard, is_agent_scoped, require_feature

router = APIRouter(prefix="/api/v1", tags=["care"])


def _require_oversight(ctx: Ctx) -> None:
    """403 an agent-scoped user out of a workspace-wide surface (other
    agents' roster/availability, queue health, cross-case search) -- Hamza:
    "the agent accounts should be able to access only the conversations
    assigned to them, nothing else." No-op for anyone with Care oversight."""
    if is_agent_scoped(ctx):
        ctx.close()
        raise ApiError(403, "forbidden")


# --- supervisor interface (P3.5) --------------------------------------
@router.post("/care/heartbeat")
def heartbeat(ctx: Ctx = Depends(guard("care", "view"))):
    presence.heartbeat(ctx.ws_id, ctx.session.get("user_id"))
    ctx.close()
    return {"ok": True}


@router.post("/care/session")
def agent_session(body: dict | None = Body(default=None),
                  ctx: Ctx = Depends(guard("care", "view"))):
    """Record a shift event (login / logout / ready / not_ready / idle / active)
    into ``agent_activity`` — the source the P4.3 care reports reconstruct
    session / ready / not-ready / idle time from."""
    b = body or {}
    state = b.get("state")
    reason = (b.get("reason") or "").strip() or None
    actor = ctx.session.get("user_id")
    try:
        repo.agent_activity.record(ctx.db.session, workspace_id=ctx.ws_id,
                                   user_id=actor, kind=state,
                                   meta={"reason": reason} if reason else None)
    except ValueError as exc:
        ctx.close()
        raise ApiError(400, str(exc))
    if state in ("ready", "active"):
        routing.upsert_agent(ctx.db.session, ctx.ws_id, actor, available=True)
    elif state in ("not_ready", "logout"):
        routing.upsert_agent(ctx.db.session, ctx.ws_id, actor, available=False)
    if state in ("ready", "active"):
        routing.drain_queue(ctx.db.session, ctx.ws_id)       # capacity just freed up
    ctx.db.commit()
    ws = ctx.ws_id
    ctx.close()
    # nudge the supervisor roster (F1.9)
    presence.heartbeat(ws, actor,
                       status="online" if state in ("ready", "active", "login")
                       else "idle" if state == "idle" else "offline")
    care_audit.emit("care.session", actor=actor, ws=ws, target=actor,
                    after={"state": state, "reason": reason})
    return {"ok": True, "state": state}


# Not "ready"/"not_ready" — those are shift *events*; a plain "not present
# yet" default for a session that has never posted one at all.
_DEFAULT_STATE = "not_ready"


@router.get("/care/session")
def agent_session_state(ctx: Ctx = Depends(guard("care", "view"))):
    """This agent's own current status -- Hamza: "make sure the .../busy/
    break/ toggle ... works". The header control used to just hardcode
    "Not available" on every mount regardless of the real, persisted
    state; this is what it reads on load instead."""
    actor = ctx.session.get("user_id")
    row = repo.agent_activity.latest(ctx.db.session, ctx.ws_id, actor)
    ctx.close()
    if not row:
        return {"state": _DEFAULT_STATE, "reason": None, "at": None}
    kind, at, meta = row
    state = kind if kind in ("ready", "not_ready", "idle", "active") else _DEFAULT_STATE
    return {"state": state, "reason": meta.get("reason"), "at": at}


@router.get("/care/session/history")
def agent_session_history(ctx: Ctx = Depends(guard("care", "view"))):
    """This agent's own recent shift activity -- the "all times/activity is
    logged and displayed" half of the same request."""
    actor = ctx.session.get("user_id")
    rows = repo.agent_activity.recent(ctx.db.session, ctx.ws_id, actor)
    ctx.close()
    return {"events": rows}


@router.get("/care/roster")
def roster(ctx: Ctx = Depends(guard("care", "view"))):
    _require_oversight(ctx)
    rows = ctx.db.session.execute(text("""
        SELECT a.user_id, u.username, a.capacity, a.available,
               COUNT(c.id) FILTER (WHERE c.state <> 'closed') AS live
        FROM care_agent a JOIN "user" u ON u.id = a.user_id
        LEFT JOIN "case" c ON c.assignee_id = a.user_id AND c.workspace_id = a.workspace_id
        WHERE a.workspace_id = :ws
        GROUP BY a.user_id, u.username, a.capacity, a.available
        ORDER BY u.username
    """), {"ws": ctx.ws_id}).mappings().all()
    pres = presence.roster(ctx.ws_id, [r["user_id"] for r in rows])
    ctx.close()
    return {"agents": [{**dict(r), **pres.get(r["user_id"], {})} for r in rows]}


@router.post("/care/agents/{user_id}/status")
def set_agent_status(user_id: int, body: dict | None = Body(default=None),
                     ctx: Ctx = Depends(guard("care", "approve"))):
    b = body or {}
    routing.upsert_agent(ctx.db.session, ctx.ws_id, user_id,
                         available=b.get("available"), capacity=b.get("capacity"))
    if b.get("available") is not None:
        repo.agent_activity.record(
            ctx.db.session, workspace_id=ctx.ws_id, user_id=user_id,
            kind="ready" if b["available"] else "not_ready",
            meta={"by": "supervisor"})
    if b.get("available") or b.get("capacity") is not None:
        routing.drain_queue(ctx.db.session, ctx.ws_id)       # capacity may have freed up
    ctx.db.commit()
    actor, ws = ctx.session.get("user_id"), ctx.ws_id
    ctx.close()
    care_audit.emit("care.agent_status", actor=actor, ws=ws, target=user_id,
                    after={"available": b.get("available"),
                           "capacity": b.get("capacity")})
    return {"ok": True}


@router.get("/care/assignment-rule")
def assignment_rule(ctx: Ctx = Depends(guard("care", "view"))):
    """The rule that hands new cases to agents, its choices (with the wording
    shown on hover) and how many agents / waiting cases it currently covers."""
    _require_oversight(ctx)
    out = routing.assignment_rule(ctx.db.session, ctx.ws_id)
    ctx.close()
    return out


@router.put("/care/assignment-rule")
def set_assignment_rule(body: dict | None = Body(default=None),
                        ctx: Ctx = Depends(guard("care", "approve"))):
    """Choose the auto-assignment rule (supervisor / team lead / admin)."""
    rule = (body or {}).get("strategy")
    if not rule:
        ctx.close()
        raise ApiError(400, "strategy is required")
    before = routing.strategy(ctx.db.session, ctx.ws_id)
    try:
        routing.set_policy(ctx.db.session, ctx.ws_id, assign_strategy=rule)
    except ValueError as exc:
        ctx.close()
        raise ApiError(400, str(exc))
    # Build the reply before committing: the tenant setting behind row-level security
    # lasts one transaction, so a read after commit() sees no rows and would answer
    # with the built-in default rule instead of the one just saved.
    out = routing.assignment_rule(ctx.db.session, ctx.ws_id)
    ctx.db.commit()
    actor, ws = ctx.session.get("user_id"), ctx.ws_id
    ctx.close()
    care_audit.emit("care.assignment_rule", actor=actor, ws=ws, target=ws,
                    before={"strategy": before}, after={"strategy": rule})
    return out


@router.get("/care/queues")
def queues(ctx: Ctx = Depends(guard("care", "view"))):
    _require_oversight(ctx)
    frt = int(routing.policy(ctx.db.session, ctx.ws_id)["first_response_sla"])
    rows = ctx.db.session.execute(text("""
        SELECT channel,
               COUNT(*) FILTER (WHERE assignee_id IS NULL)               AS unassigned,
               COUNT(*)                                                  AS open,
               COALESCE(MAX(EXTRACT(EPOCH FROM (now() - last_activity_at))), 0) AS oldest_waiting_s,
               COUNT(*) FILTER (WHERE first_response_at IS NULL
                                AND EXTRACT(EPOCH FROM (now() - opened_at)) > :frt)          AS breached,
               COUNT(*) FILTER (WHERE first_response_at IS NULL
                                AND EXTRACT(EPOCH FROM (now() - opened_at)) BETWEEN :warn AND :frt) AS at_risk
        FROM "case" WHERE workspace_id = :ws AND state <> 'closed'
        GROUP BY channel ORDER BY channel
    """), {"ws": ctx.ws_id, "frt": frt, "warn": max(0, frt - 300)}).mappings().all()
    ctx.close()
    return {"queues": [{**dict(r), "oldest_waiting_s": float(r["oldest_waiting_s"])}
                       for r in rows]}


@router.get("/care/performance")
def performance(ctx: Ctx = Depends(guard("care", "view"))):
    """Per-agent stats (all-time) plus a workspace-wide snapshot for the
    console header: currently open, closed, avg first response, avg handle
    time — the numbers Hamza asked to see "on the care dashboard top"."""
    _require_oversight(ctx)
    summary = ctx.db.session.execute(text("""
        SELECT COUNT(*) FILTER (WHERE state <> 'closed') AS open_cases,
               COUNT(*) FILTER (WHERE state = 'closed') AS closed_cases,
               AVG(EXTRACT(EPOCH FROM (first_response_at - opened_at)))
                   FILTER (WHERE first_response_at IS NOT NULL) AS avg_first_response_s,
               AVG(EXTRACT(EPOCH FROM (closed_at - opened_at)))
                   FILTER (WHERE closed_at IS NOT NULL) AS avg_handle_s
        FROM "case" WHERE workspace_id = :ws
    """), {"ws": ctx.ws_id}).mappings().one()
    rows = ctx.db.session.execute(text("""
        SELECT u.id AS user_id, u.username,
               COUNT(c.id) AS assigned,
               COUNT(c.id) FILTER (WHERE c.state = 'closed') AS closed,
               AVG(EXTRACT(EPOCH FROM (c.first_response_at - c.opened_at)))
                   FILTER (WHERE c.first_response_at IS NOT NULL) AS avg_first_response_s,
               AVG(EXTRACT(EPOCH FROM (c.closed_at - c.opened_at)))
                   FILTER (WHERE c.closed_at IS NOT NULL) AS avg_handle_s
        FROM "user" u
        JOIN care_agent a ON a.user_id = u.id AND a.workspace_id = :ws
        LEFT JOIN "case" c ON c.assignee_id = u.id AND c.workspace_id = :ws
        GROUP BY u.id, u.username ORDER BY u.username
    """), {"ws": ctx.ws_id}).mappings().all()
    breaches = dict(ctx.db.session.execute(text("""
        SELECT c.assignee_id, COUNT(*) FROM case_event e
        JOIN "case" c ON c.id = e.case_id
        WHERE c.workspace_id = :ws AND e.kind = 'sla_breach'
        GROUP BY c.assignee_id
    """), {"ws": ctx.ws_id}).all())
    ctx.close()
    return {"summary": dict(summary),
            "agents": [{**dict(r), "sla_breaches": breaches.get(r["user_id"], 0)}
                       for r in rows]}


@router.get("/care/pending")
def pending(ctx: Ctx = Depends(guard("care", "approve"))):
    rows = ctx.db.session.execute(text("""
        SELECT id, platform, action, target_ref, request, actor, created_at
        FROM outbound_action WHERE workspace_id = :ws AND state = 'pending'
        ORDER BY created_at
    """), {"ws": ctx.ws_id}).mappings().all()
    ctx.close()
    return {"pending": [dict(r) for r in rows]}


@router.put("/care/outbound/{action_id}")
def edit_pending(action_id: int, body: dict | None = Body(default=None),
                 ctx: Ctx = Depends(guard("care", "approve"))):
    b = body or {}
    row = repo.outbound.get(ctx.db.session, action_id)
    if not row or row["workspace_id"] != ctx.ws_id or row["state"] != "pending":
        ctx.close()
        raise ApiError(404, "no pending action")
    req = dict(row["request"] or {})
    if (b.get("text") or "").strip():
        req["text"] = b["text"].strip()
    repo.outbound.update_request(ctx.db.session, action_id, req)
    ctx.db.commit()
    ctx.close()
    _app.audit(actor=ctx.session.get("user_id"), tenant_id=ctx.ws_id,
               action="care.reply_edit", target=action_id)
    return {"ok": True}


@router.post("/care/outbound/{action_id}/approve")
def approve_pending(action_id: int, ctx: Ctx = Depends(guard("care", "approve"))):
    s = ctx.db.session
    row = repo.outbound.get(s, action_id)
    if not row or row["workspace_id"] != ctx.ws_id or row["state"] != "pending":
        ctx.close()
        raise ApiError(404, "no pending action")
    client = write.client_for(row["platform"], _app.keys(ctx.ws_id))
    result = client.deliver(s, action_id)
    req = repo.outbound.get(s, action_id)["request"] or {}
    if result.state == "sent" and req.get("case_id"):
        cases.post_reply(s, int(req["case_id"]), ctx.ws_id, body=req.get("text", ""),
                         channel=req.get("channel") or row["platform"],
                         platform_ref=row["target_ref"],
                         actor=ctx.session.get("user_id"),
                         outbound_action_id=action_id)
    s.commit()
    ctx.close()
    _app.audit(actor=ctx.session.get("user_id"), tenant_id=ctx.ws_id,
               action="care.reply_approve", target=action_id,
               after={"state": result.state})
    if req.get("case_id"):
        realtime.publish(f"case:{int(req['case_id'])}", {"kind": "reply_approved"})
        realtime.publish(f"queue:{ctx.ws_id}", {"kind": "reply_approved",
                                                "case_id": int(req["case_id"])})
    return {"ok": result.state == "sent", "state": result.state,
            "external_id": result.external_id}


@router.post("/care/outbound/{action_id}/reject")
def reject_pending(action_id: int, body: dict | None = Body(default=None),
                   ctx: Ctx = Depends(guard("care", "approve"))):
    """Reject a held reply with a note back to the agent (F2.4)."""
    s = ctx.db.session
    note = (body or {}).get("note") or ""
    row = repo.outbound.get(s, action_id)
    if not row or row["workspace_id"] != ctx.ws_id or row["state"] != "pending":
        ctx.close()
        raise ApiError(404, "no pending action")
    repo.outbound.set_state(s, action_id, "rejected", error=note or "rejected")
    case_id = (row["request"] or {}).get("case_id")
    actor = ctx.session.get("user_id")
    if case_id:
        cases._event(s, int(case_id), "reply_rejected", actor,
                     outbound_action_id=action_id, note=note)
    s.commit()
    ws = ctx.ws_id
    ctx.close()
    _app.audit(actor=actor, tenant_id=ws, action="care.reply_reject",
               target=action_id, after={"note": note})
    if case_id:
        realtime.publish(f"case:{int(case_id)}", {"kind": "reply_rejected"})
    return {"ok": True}


# --- scheduling / block / export (P3.8) ------------------------------
@router.post("/care/cases/{case_id}/schedule")
def schedule_message(case_id: int, body: dict | None = Body(default=None),
                     ctx: Ctx = Depends(guard("care", "edit"))):
    assert_case_access(ctx, case_id)
    b = body or {}
    text_body, platform, at = (b.get("text") or "").strip(), b.get("platform"), b.get("at")
    if not (text_body and platform and at):
        ctx.close()
        raise ApiError(400, "text, platform and at are required")
    s = ctx.db.session
    case = s.execute(text('SELECT channel FROM "case" WHERE id=:c AND workspace_id=:ws'),
                     {"c": case_id, "ws": ctx.ws_id}).first()
    if not case:
        ctx.close()
        raise ApiError(404, "case not found")
    try:
        when = datetime.fromisoformat(str(at).replace("Z", "+00:00"))
    except ValueError:
        ctx.close()
        raise ApiError(400, "at must be an ISO-8601 datetime")
    client = write.client_for(platform, _app.keys(ctx.ws_id))
    req = {"text": text_body, "case_id": case_id, "channel": case[0]}
    action = "reply_public" if b.get("target_ref") else "publish"
    aid = client.create_pending(s, ctx.ws_id, action=action,
                                target_ref=b.get("target_ref"), request=req,
                                actor=ctx.session.get("user_id"))
    runner.schedule_once(s, name=f"send:{aid}", at=when, kind="send_scheduled",
                         payload={"ws": ctx.ws_id, "action_id": aid, "case_id": case_id},
                         tenant_id=ctx.ws_id)
    actor = ctx.session.get("user_id")
    cases._event(s, case_id, "reply_scheduled", actor,
                 outbound_action_id=aid, at=at)
    s.commit()
    ws = ctx.ws_id
    ctx.close()
    care_audit.emit("care.schedule", actor=actor, ws=ws, target=case_id,
                    after={"outbound_action_id": aid, "scheduled_for": at})
    realtime.publish(f"case:{case_id}", {"kind": "reply_scheduled"})
    return {"ok": True, "outbound_action_id": aid, "scheduled_for": at}


@router.get("/care/cases/{case_id}/scheduled")
def list_scheduled(case_id: int, ctx: Ctx = Depends(guard("care", "view"))):
    """Pending scheduled outbound actions for a case (F1.8)."""
    assert_case_access(ctx, case_id)
    rows = ctx.db.session.execute(text("""
        SELECT o.id, o.request, o.created_at, s.next_run
        FROM outbound_action o
        LEFT JOIN scheduled_task s ON s.name = 'send:' || o.id
        WHERE o.workspace_id = :ws AND o.state = 'pending'
          AND (o.request ->> 'case_id') = :c
        ORDER BY s.next_run NULLS LAST, o.id
    """), {"ws": ctx.ws_id, "c": str(case_id)}).mappings().all()
    ctx.close()
    return {"scheduled": [
        {"outbound_action_id": r["id"],
         "text": (r["request"] or {}).get("text", ""),
         "scheduled_for": r["next_run"].isoformat() if r["next_run"] else None,
         "created_at": r["created_at"].isoformat() if r["created_at"] else None}
        for r in rows]}


@router.post("/care/cases/{case_id}/scheduled/{action_id}/cancel")
def cancel_scheduled(case_id: int, action_id: int,
                     ctx: Ctx = Depends(guard("care", "edit"))):
    """Cancel a scheduled message: reject the outbound action and disable its
    one-shot task (F1.8)."""
    assert_case_access(ctx, case_id)
    s = ctx.db.session
    row = repo.outbound.get(s, action_id)
    if not row or row["workspace_id"] != ctx.ws_id or row["state"] != "pending":
        ctx.close()
        raise ApiError(404, "no pending scheduled message")
    repo.outbound.set_state(s, action_id, "rejected", error="cancelled by agent")
    s.execute(text("UPDATE scheduled_task SET enabled = 0 WHERE name = :n"),
              {"n": f"send:{action_id}"})
    actor = ctx.session.get("user_id")
    cases._event(s, case_id, "reply_unscheduled", actor, outbound_action_id=action_id)
    s.commit()
    ws = ctx.ws_id
    ctx.close()
    care_audit.emit("care.schedule", actor=actor, ws=ws, target=case_id,
                    after={"cancelled": action_id})
    realtime.publish(f"case:{case_id}", {"kind": "reply_unscheduled"})
    return {"ok": True}


def _block(case_id, body, ctx, verb):
    assert_case_access(ctx, case_id)
    b = body or {}
    missing = [k for k in ("target_ref", "platform", "reason", "category")
               if not (b.get(k) or "").strip()]
    if missing:
        ctx.close()
        raise ApiError(400, f"{', '.join(missing)} are required")
    client = write.client_for(b["platform"], _app.keys(ctx.ws_id))
    fn = client.block if verb == "block" else client.unblock
    result = fn(ctx.db.session, ctx.ws_id, target_ref=b["target_ref"],
                actor=ctx.session.get("user_id"), reason=b["reason"],
                category=b["category"])
    ctx.db.commit()
    actor = ctx.session.get("user_id")
    ws = ctx.ws_id
    ctx.close()
    _app.audit(actor=actor, tenant_id=ws, action=f"care.{verb}",
               target=b["target_ref"],
               after={"reason": b["reason"], "category": b["category"],
                      "case_id": case_id})
    return {"ok": result.state == "sent", "state": result.state}


@router.post("/care/cases/{case_id}/block")
def block_customer(case_id: int, body: dict | None = Body(default=None),
                   ctx: Ctx = Depends(guard("care", "edit"))):
    return _block(case_id, body, ctx, "block")


@router.post("/care/cases/{case_id}/unblock")
def unblock_customer(case_id: int, body: dict | None = Body(default=None),
                     ctx: Ctx = Depends(guard("care", "edit"))):
    return _block(case_id, body, ctx, "unblock")


@router.get("/care/cases/{case_id}/export")
def export_case(case_id: int, format: str = "pdf",
                ctx: Ctx = Depends(guard("care", "export"))):
    require_feature(ctx, "cap.export")
    out = case_export.export(ctx.db.session, ctx.ws_id, case_id,
                             fmt="xlsx" if format == "xlsx" else "pdf")
    ctx.close()
    if out is None:
        raise ApiError(404, "case not found")
    media, blob = out
    ext = "xlsx" if format == "xlsx" else "pdf"
    return Response(content=blob, media_type=media, headers={
        "Content-Disposition": f'attachment; filename="case-{case_id}.{ext}"'})


@router.get("/care/search")
def search(q: str = "", limit: int = 10, ctx: Ctx = Depends(guard("care", "view"))):
    """Cross-entity autocomplete (P3.9) — customers, cases, message bodies."""
    _require_oversight(ctx)
    out = care_search.search(ctx.db.session, ctx.ws_id, q, limit=min(limit, 25))
    ctx.close()
    return out


@router.get("/care/agents")
def agents(ctx: Ctx = Depends(guard("care", "view"))):
    _require_oversight(ctx)
    rows = ctx.db.session.execute(text("""
        SELECT a.user_id, u.username, a.capacity, a.available,
               COUNT(c.id) FILTER (WHERE c.state <> 'closed') AS live
        FROM care_agent a JOIN "user" u ON u.id = a.user_id
        LEFT JOIN "case" c ON c.assignee_id = a.user_id AND c.workspace_id = a.workspace_id
        WHERE a.workspace_id = :ws
        GROUP BY a.user_id, u.username, a.capacity, a.available
        ORDER BY u.username
    """), {"ws": ctx.ws_id}).mappings().all()
    ctx.close()
    return {"agents": [dict(r) for r in rows]}
