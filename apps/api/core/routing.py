"""Case routing (build plan §5 / P3.3).

* ``auto_assign_new_case`` — a new inbound case goes to the next agent by the
  workspace's chosen rule (``STRATEGIES``: manual / round robin / least busy /
  longest idle). Only ``agent`` / ``senior_agent`` users are ever picked --
  never a supervisor, team lead or admin -- and only if available and under
  capacity.
* ``assign_next`` — the same pick for an explicit "assign to next available".
* ``drain_queue`` — waiting (unassigned) cases go to agents oldest-first (FIFO)
  as capacity frees up.
* ``on_case_closed`` — auto-issue: when an agent closes a case, hand them the
  oldest unassigned open case (if they are under capacity).
* ``reassign`` — needs a logged reason.
* ``arm_sla_timers`` — three one-shot ``scheduled_task`` rows per case (first
  response, resolution, escalation); ``check_sla`` fires a ``sla_breach``
  ``case_event`` when the deadline passes with the condition unmet.
"""
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from core import cases
from jobs import runner

_DEFAULT_POLICY = {"first_response_sla": 900, "resolution_sla": 86400,
                   "escalation_after": 3600, "default_capacity": 5,
                   "assign_strategy": "least_busy"}

# Who auto-assignment may hand a case to. A user who also holds an oversight role
# is skipped: "agents only", never a supervisor or team lead.
AUTO_ASSIGN_ROLES = ("agent", "senior_agent")
_OVERSIGHT_ROLES = ("supervisor", "team_lead", "admin")

# The rules a supervisor can choose between. The text is served to the console
# and shown as the hover explanation, so it is the single source of the wording.
STRATEGIES = (
    {"key": "manual", "label": "Manual",
     "description": "Nothing is assigned automatically. New cases wait in the queue until "
                    "an agent picks one up or a supervisor assigns it."},
    {"key": "round_robin", "label": "Round robin",
     "description": "Agents take turns in a fixed order, each getting the next case in "
                    "their turn regardless of how many they already hold. Simple and "
                    "predictable; agents at capacity or away are skipped."},
    {"key": "least_busy", "label": "Least busy",
     "description": "The next case goes to the available agent with the fewest open "
                    "cases. Keeps workloads level when some cases take much longer than "
                    "others. Ties go to whoever was assigned least recently."},
    {"key": "longest_idle", "label": "Longest idle (first in, first out)",
     "description": "Agents form a queue by when they last received a case; the one who "
                    "has waited longest goes next and then joins the back of the line. "
                    "Fair over time. Waiting cases are always handed out oldest first."},
)
STRATEGY_KEYS = tuple(s["key"] for s in STRATEGIES)


def _now():
    return datetime.now(timezone.utc)


# --- agents / policy -------------------------------------------------------
def upsert_agent(session, workspace_id, user_id, *, capacity=None, available=None):
    session.execute(text("""
        INSERT INTO care_agent (workspace_id, user_id, capacity, available)
        VALUES (:ws, :u, COALESCE(:cap, 5), COALESCE(:av, 1))
        ON CONFLICT (workspace_id, user_id) DO UPDATE SET
            capacity  = COALESCE(:cap, care_agent.capacity),
            available = COALESCE(:av, care_agent.available)
    """), {"ws": workspace_id, "u": user_id, "cap": capacity,
           "av": None if available is None else (1 if available else 0)})


def policy(session, workspace_id) -> dict:
    row = session.execute(text(
        "SELECT first_response_sla, resolution_sla, escalation_after, default_capacity, "
        "assign_strategy FROM routing_policy WHERE workspace_id = :ws"), {"ws": workspace_id}).mappings().first()
    return dict(row) if row else dict(_DEFAULT_POLICY)


def _floor(session, workspace_id) -> int:
    """Auto-assignment only hands out cases with an id above this; 0 = no floor."""
    return int(session.execute(text(
        "SELECT auto_assign_after_case FROM routing_policy WHERE workspace_id = :ws"),
        {"ws": workspace_id}).scalar() or 0)


def set_policy(session, workspace_id, **fields):
    allowed = {k: v for k, v in fields.items() if k in _DEFAULT_POLICY and v is not None}
    if not allowed:
        return
    if "assign_strategy" in allowed:
        if allowed["assign_strategy"] not in STRATEGY_KEYS:
            raise ValueError(f"unknown assignment rule {allowed['assign_strategy']!r}")
        if allowed["assign_strategy"] != strategy(session, workspace_id):
            # A new rule applies to cases that arrive from now on; whatever is waiting
            # unassigned stays for a person to pick up.
            allowed["auto_assign_after_case"] = int(session.execute(text(
                'SELECT COALESCE(MAX(id), 0) FROM "case" WHERE workspace_id = :ws'),
                {"ws": workspace_id}).scalar_one())
    cols = ", ".join(allowed)
    vals = ", ".join(f":{k}" for k in allowed)
    upd = ", ".join(f"{k} = EXCLUDED.{k}" for k in allowed)
    session.execute(text(f"""
        INSERT INTO routing_policy (workspace_id, {cols})
        VALUES (:ws, {vals})
        ON CONFLICT (workspace_id) DO UPDATE SET {upd}, updated_at = now()
    """), {"ws": workspace_id, **allowed})


# --- assignment --------------------------------------------------------
_EPOCH = datetime.min.replace(tzinfo=timezone.utc)


def _lock(session, workspace_id):
    """Serialise picks per workspace so two cases arriving together can't both
    be handed to the same agent past their capacity."""
    session.execute(text("SELECT pg_advisory_xact_lock(7301, :ws)"), {"ws": workspace_id})


def _eligible_agents(session, workspace_id):
    """Agents auto-assignment may use right now: an agent role, active, marked
    available, and not also a supervisor / team lead / admin."""
    return session.execute(text("""
        SELECT a.user_id, a.capacity, a.last_assigned_at,
               COUNT(c.id) FILTER (WHERE c.state <> 'closed') AS live
        FROM care_agent a
        JOIN "user" u ON u.id = a.user_id AND u.active = 1 AND u.role = ANY(:roles)
        LEFT JOIN "case" c ON c.assignee_id = a.user_id AND c.workspace_id = a.workspace_id
        WHERE a.workspace_id = :ws AND a.available = 1
          AND NOT EXISTS (SELECT 1 FROM user_role ur
                          WHERE ur.user_id = a.user_id AND ur.role_key = ANY(:over))
        GROUP BY a.user_id, a.capacity, a.last_assigned_at
    """), {"ws": workspace_id, "roles": list(AUTO_ASSIGN_ROLES),
           "over": list(_OVERSIGHT_ROLES)}).all()


def strategy(session, workspace_id) -> str:
    return policy(session, workspace_id)["assign_strategy"]


def pick_agent(session, workspace_id, rule=None):
    """The next agent for a case under ``rule`` (default: the workspace's rule; a
    ``manual`` workspace still answers an explicit request with *least busy*), or
    ``None`` if no eligible agent is free."""
    rule = rule or strategy(session, workspace_id)
    candidates = [r for r in _eligible_agents(session, workspace_id) if r.live < r.capacity]
    if not candidates:
        return None
    if rule == "round_robin":
        # A ring over user ids, continuing after whoever was handed a case last.
        last = session.execute(text(
            "SELECT user_id FROM care_agent WHERE workspace_id = :ws "
            "AND last_assigned_at IS NOT NULL ORDER BY last_assigned_at DESC, user_id DESC LIMIT 1"),
            {"ws": workspace_id}).scalar()
        ring = sorted(r.user_id for r in candidates)
        return next((u for u in ring if last is not None and u > last), ring[0])
    if rule == "longest_idle":
        return min(candidates, key=lambda r: (r.last_assigned_at or _EPOCH, r.live, r.user_id)).user_id
    return min(candidates, key=lambda r: (r.live, r.last_assigned_at or _EPOCH, r.user_id)).user_id


def _give(session, workspace_id, case_id, agent, *, actor, rule):
    cases.assign(session, case_id, agent, actor=actor, rule=rule)
    session.execute(text(
        "UPDATE care_agent SET last_assigned_at = clock_timestamp() "   # not now(): a batch shares one
        "WHERE workspace_id = :ws AND user_id = :u"), {"ws": workspace_id, "u": agent})


def assign_next(session, workspace_id, case_id, *, actor=None):
    """Assign to the next agent by the workspace rule (or least busy if it is manual)."""
    _lock(session, workspace_id)
    rule = strategy(session, workspace_id)
    rule = "least_busy" if rule == "manual" else rule
    agent = pick_agent(session, workspace_id, rule)
    if agent is None:
        return None
    _give(session, workspace_id, case_id, agent, actor=actor or "routing", rule=rule)
    return agent


def auto_assign_new_case(session, workspace_id, case_id):
    """Hook for a newly opened inbound case: hand it out unless the rule is manual."""
    if strategy(session, workspace_id) == "manual":
        return None
    return assign_next(session, workspace_id, case_id, actor="routing")


def drain_queue(session, workspace_id, *, limit=25) -> int:
    """Hand waiting (unassigned, open) cases to free agents, oldest first. Called
    when capacity frees up -- an agent goes ready, capacity is raised. Only cases
    newer than the rule (``auto_assign_after_case``); older ones stay unassigned."""
    if strategy(session, workspace_id) == "manual":
        return 0
    floor, done = _floor(session, workspace_id), 0
    while done < limit:
        row = session.execute(text("""
            SELECT id FROM "case"
            WHERE workspace_id = :ws AND state = 'open' AND assignee_id IS NULL AND id > :floor
            ORDER BY opened_at, id LIMIT 1
        """), {"ws": workspace_id, "floor": floor}).first()
        if row is None or assign_next(session, workspace_id, row[0], actor="routing") is None:
            break
        done += 1
    return done


def assignment_rule(session, workspace_id) -> dict:
    """What the supervisor console shows: the current rule, the choices, and how
    many agents / waiting cases it currently applies to."""
    eligible = _eligible_agents(session, workspace_id)
    floor = _floor(session, workspace_id)
    waiting, held_back = session.execute(text(
        """SELECT count(*) FILTER (WHERE id > :floor), count(*) FILTER (WHERE id <= :floor)
           FROM "case" WHERE workspace_id = :ws AND state = 'open' AND assignee_id IS NULL"""),
        {"ws": workspace_id, "floor": floor}).one()
    return {"strategy": strategy(session, workspace_id), "strategies": list(STRATEGIES),
            "roles": list(AUTO_ASSIGN_ROLES), "available_agents": len(eligible),
            "free_agents": sum(1 for r in eligible if r.live < r.capacity),
            "waiting_cases": int(waiting),
            # Unassigned before the rule was set: left for a person, never auto-assigned.
            "held_back_cases": int(held_back)}


def reassign(session, case_id, to_user_id, *, actor, reason):
    if not reason:
        raise cases.CaseError("a reason is required to reassign a case")
    session.execute(text(
        'UPDATE "case" SET assignee_id = :u, last_activity_at = now() WHERE id = :c'),
        {"u": to_user_id, "c": case_id})
    cases._event(session, case_id, "reassigned", actor,
                 to_user_id=to_user_id, reason=reason)


def on_case_closed(session, workspace_id, agent_id, *, actor=None):
    """Auto-issue: give the agent who just closed a case the oldest waiting one.
    Only an eligible (agent-role, available, under-capacity) agent, and never
    when the workspace rule is manual."""
    rule = strategy(session, workspace_id)
    if rule == "manual":
        return None
    floor = _floor(session, workspace_id)
    counts = {r.user_id: (r.capacity, r.live) for r in _eligible_agents(session, workspace_id)}
    cap_live = counts.get(agent_id)
    if cap_live is None or cap_live[1] >= cap_live[0]:
        return None
    _lock(session, workspace_id)
    row = session.execute(text("""
        SELECT id FROM "case"
        WHERE workspace_id = :ws AND state <> 'closed' AND assignee_id IS NULL AND id > :floor
        ORDER BY opened_at LIMIT 1
    """), {"ws": workspace_id, "floor": floor}).first()
    if row is None:
        return None
    _give(session, workspace_id, row[0], agent_id, actor=actor or "routing", rule=rule)
    return row[0]


# --- SLA timers ------------------------------------------------------
def arm_sla_timers(session, workspace_id, case_id, *, now=None):
    now = now or _now()
    p = policy(session, workspace_id)
    for label, seconds in (("first_response", p["first_response_sla"]),
                           ("resolution", p["resolution_sla"]),
                           ("escalation", p["escalation_after"])):
        runner.schedule_once(
            session, name=f"sla:{label}:{case_id}",
            at=now + timedelta(seconds=int(seconds)),
            kind="sla_check", payload={"ws": workspace_id, "case_id": case_id,
                                       "check": label},
            tenant_id=workspace_id)


def check_sla(session, payload) -> dict:
    """Job handler for a fired SLA timer. Fires a ``sla_breach`` event when the
    deadline passed with the condition unmet."""
    case_id, check = payload["case_id"], payload["check"]
    row = session.execute(text(
        'SELECT state, first_response_at, closed_at FROM "case" WHERE id = :c'),
        {"c": case_id}).mappings().first()
    if not row:
        return {"case_id": case_id, "check": check, "result": "gone"}

    breached = False
    if check == "first_response":
        breached = row["first_response_at"] is None and row["state"] != "closed"
    elif check == "resolution":
        breached = row["closed_at"] is None
    elif check == "escalation":
        breached = row["first_response_at"] is None and row["state"] not in ("closed",)

    if breached:
        cases._event(session, case_id, "sla_breach", "sla",
                     check=check, state=row["state"])
        if payload.get("ws") is not None:
            from core import macro_rules        # lazy: macro_rules imports cases
            macro_rules.safe(session, macro_rules.on_sla_breach, payload["ws"], case_id)
    return {"case_id": case_id, "check": check, "breached": breached}
