"""Macros: reply text with placeholders + a list of case actions.

A macro is a ``care_template`` row (0035 adds shortcut / quick pin / actions /
active). Authoring is gated by ``templates:create|edit|delete`` in the router;
everyone with ``templates:view`` can list and apply them. This module is the
domain half: validation, ``{{placeholder}}`` rendering, and running the actions
through the same case-engine primitives the console buttons use, so a macro can
never do anything an agent could not do by hand.

Auto (rule-triggered) macros live in ``macro_rules.py`` and reuse
``apply_actions`` from here.
"""
import json
import re

from sqlalchemy import text

from core import cases


class MacroError(ValueError):
    """An invalid macro or macro operation (the router maps it to a 400)."""


class MacroConflict(MacroError):
    """A uniqueness clash, e.g. a shortcut already in use (the router maps it to 409)."""


ACTION_TYPES = ("set_status", "assign", "add_note", "set_priority", "add_tags")
PRIORITIES = ("low", "normal", "high", "urgent")
ASSIGN_MODES = ("self", "agent", "auto")
MAX_ACTIONS = 10
MAX_QUICK = 8

# placeholder -> what an unknown value renders as when the author gave no
# ``{{key|fallback}}`` of their own. Never render a raw ``{{...}}`` to a customer.
PLACEHOLDERS = {
    "customer.first_name": "there",
    "customer.name": "there",
    "customer.handle": "",
    "agent.name": "our team",
    "case.id": "",
}
_PH = re.compile(r"\{\{\s*([A-Za-z_.]+)\s*(?:\|([^{}]*))?\}\}")
_SHORTCUT = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
_COLS = ("m.id, m.name, m.category, m.body, m.shortcut, m.description, m.is_quick, "
         "m.quick_order, m.actions, m.active, m.updated_at")


# --- validation ------------------------------------------------------------
def check_placeholders(body) -> None:
    for key, _ in _PH.findall(body or ""):
        if key not in PLACEHOLDERS:
            raise MacroError(f"unknown placeholder {{{{{key}}}}} — "
                             f"use one of {', '.join(sorted(PLACEHOLDERS))}")


def validate_actions(actions, *, allow_self=True) -> list[dict]:
    if actions is None:
        return []
    if not isinstance(actions, list) or len(actions) > MAX_ACTIONS:
        raise MacroError(f"actions must be a list of at most {MAX_ACTIONS}")
    out = []
    for raw in actions:
        kind = (raw or {}).get("type")
        if kind not in ACTION_TYPES:
            raise MacroError(f"unknown action type {kind!r}")
        if kind == "set_status":
            status = raw.get("status")
            if status not in cases.STATES:
                raise MacroError(f"unknown status {status!r}")
            act = {"type": kind, "status": status}
            if status == cases.CLOSED:
                cat = (raw.get("closure_category") or "").strip()
                if not cat:
                    raise MacroError("closing a case needs a closure_category")
                act["closure_category"] = cat
        elif kind == "assign":
            mode = raw.get("mode")
            if mode not in ASSIGN_MODES:
                raise MacroError(f"assign mode must be one of {', '.join(ASSIGN_MODES)}")
            if mode == "self" and not allow_self:
                raise MacroError("an automatic macro cannot assign to 'the agent who applies it'")
            act = {"type": kind, "mode": mode}
            if mode == "agent":
                try:
                    act["user_id"] = int(raw.get("user_id"))
                except (TypeError, ValueError):
                    raise MacroError("assign to an agent needs a user_id") from None
        elif kind == "add_note":
            body = (raw.get("body") or "").strip()
            if not body:
                raise MacroError("an add_note action needs a body")
            check_placeholders(body)
            act = {"type": kind, "body": body}
        elif kind == "set_priority":
            if raw.get("priority") not in PRIORITIES:
                raise MacroError(f"priority must be one of {', '.join(PRIORITIES)}")
            act = {"type": kind, "priority": raw["priority"]}
        else:  # add_tags
            tags = [str(t).strip().lower() for t in (raw.get("tags") or []) if str(t).strip()]
            tags = list(dict.fromkeys(tags))
            if not tags or len(tags) > 10 or any(len(t) > 32 for t in tags):
                raise MacroError("add_tags needs 1-10 tags of at most 32 characters")
            act = {"type": kind, "tags": tags}
        out.append(act)
    return out


def normalise_shortcut(value) -> str | None:
    s = (value or "").strip().lstrip("/").lower()
    if not s:
        return None
    if not _SHORTCUT.match(s):
        raise MacroError("shortcut may use letters, digits, '-' and '_' (max 32)")
    return s


# --- CRUD ------------------------------------------------------------------
def _shape(row) -> dict:
    d = dict(row)
    d["actions"] = d.get("actions") or []
    return d


def list_macros(session, ws, *, category="", active_only=True, quick_only=False) -> list[dict]:
    where, params = ["m.workspace_id = :ws"], {"ws": ws}
    if category:
        where.append("m.category = :cat")
        params["cat"] = category
    if active_only:
        where.append("m.active")
    if quick_only:
        where.append("m.is_quick")
    rows = session.execute(text(f"""
        SELECT {_COLS},
               (SELECT count(*) FROM care_macro_rule r WHERE r.macro_id = m.id) AS rule_count
        FROM care_template m WHERE {' AND '.join(where)}
        ORDER BY m.is_quick DESC, m.quick_order, m.category, m.name
    """), params).mappings().all()
    return [_shape(r) for r in rows]


def get_macro(session, ws, macro_id) -> dict | None:
    row = session.execute(text(
        f"SELECT {_COLS} FROM care_template m WHERE m.id = :i AND m.workspace_id = :ws"),
        {"i": macro_id, "ws": ws}).mappings().first()
    return _shape(row) if row else None


def save_macro(session, ws, data, *, macro_id=None, actor=None) -> int:
    """Create (``macro_id`` None) or partially update a macro. Returns its id;
    raises ``MacroError`` / ``MacroConflict`` on bad input."""
    cur = {}
    if macro_id is not None:
        cur = get_macro(session, ws, macro_id)
        if cur is None:
            raise LookupError("macro not found")
    merged = {**cur, **{k: v for k, v in (data or {}).items() if k in (
        "name", "category", "body", "shortcut", "description", "is_quick",
        "quick_order", "actions", "active")}}
    name = (merged.get("name") or "").strip()
    if not name:
        raise MacroError("name is required")
    body = merged.get("body") or ""
    check_placeholders(body)
    actions = validate_actions(merged.get("actions"))
    if not body.strip() and not actions:
        raise MacroError("a macro needs reply text, at least one action, or both")
    shortcut = normalise_shortcut(merged.get("shortcut"))
    if shortcut and session.execute(text(
            "SELECT 1 FROM care_template WHERE workspace_id = :ws AND lower(shortcut) = :s "
            "AND id <> COALESCE(:i, 0)"), {"ws": ws, "s": shortcut, "i": macro_id}).first():
        raise MacroConflict(f"the shortcut /{shortcut} is already used by another macro")
    is_quick, active = bool(merged.get("is_quick")), merged.get("active") is not False
    order = int(merged.get("quick_order") or 0)
    if is_quick and active:
        taken = session.execute(text(
            "SELECT count(*), COALESCE(max(quick_order), 0) FROM care_template "
            "WHERE workspace_id = :ws AND is_quick AND active AND id <> COALESCE(:i, 0)"),
            {"ws": ws, "i": macro_id}).one()
        if taken[0] >= MAX_QUICK:
            raise MacroError(f"at most {MAX_QUICK} quick macros can be pinned — unpin one first")
        if not order or not cur.get("is_quick"):
            order = int(taken[1]) + 1
    params = {"ws": ws, "n": name, "c": (merged.get("category") or "general").strip() or "general",
              "b": body, "s": shortcut, "d": (merged.get("description") or "").strip() or None,
              "q": is_quick, "o": order, "a": _json(actions), "act": active, "by": actor}
    if macro_id is None:
        return int(session.execute(text("""
            INSERT INTO care_template (workspace_id, name, category, body, shortcut, description,
                                       is_quick, quick_order, actions, active, created_by)
            VALUES (:ws, :n, :c, :b, :s, :d, :q, :o, CAST(:a AS jsonb), :act, :by) RETURNING id
        """), params).scalar_one())
    session.execute(text("""
        UPDATE care_template SET name=:n, category=:c, body=:b, shortcut=:s, description=:d,
            is_quick=:q, quick_order=:o, actions=CAST(:a AS jsonb), active=:act, updated_at=now()
        WHERE id = :i AND workspace_id = :ws
    """), {**params, "i": macro_id})
    return macro_id


def delete_macro(session, ws, macro_id) -> bool:
    return bool(session.execute(text(
        "DELETE FROM care_template WHERE id = :i AND workspace_id = :ws"),
        {"i": macro_id, "ws": ws}).rowcount)


def _json(value) -> str:
    return json.dumps(value)


# --- rendering -------------------------------------------------------------
def context(session, ws, case_id, *, agent_id=None) -> dict:
    row = session.execute(text("""
        SELECT c.id, cu.display_name, cu.preferred_name, cu.handle
        FROM "case" c JOIN customer cu ON cu.id = c.customer_id
        WHERE c.id = :c AND c.workspace_id = :ws
    """), {"c": case_id, "ws": ws}).mappings().first()
    if not row:
        raise LookupError("case not found")
    full = (row["preferred_name"] or row["display_name"] or "").strip()
    first = full.split()[0] if full and "@" not in full else ""
    agent = ""
    if agent_id is not None:
        agent = session.execute(text('SELECT username FROM "user" WHERE id = :u'),
                                {"u": agent_id}).scalar() or ""
    return {"customer.first_name": first, "customer.name": full,
            "customer.handle": row["handle"] or "", "agent.name": agent,
            "case.id": str(row["id"])}


def render(body, ctx) -> str:
    def sub(m):
        key, fallback = m.group(1), m.group(2)
        value = (ctx.get(key) or "").strip()
        if value:
            return value
        return fallback.strip() if fallback is not None else PLACEHOLDERS.get(key, "")
    return _PH.sub(sub, body or "")


def preview(session, ws, case_id, macro, *, agent_id=None) -> dict:
    """What applying ``macro`` to this case would say and do, without doing it."""
    ctx = context(session, ws, case_id, agent_id=agent_id)
    return {"macro_id": macro["id"], "name": macro["name"], "text": render(macro["body"], ctx),
            "actions": [{**a, "summary": describe(a)} for a in macro["actions"]]}


def describe(action) -> str:
    t = action["type"]
    if t == "set_status":
        return f"Set status to {action['status'].replace('_', ' ')}"
    if t == "assign":
        return {"self": "Assign to me", "auto": "Assign to the next available agent"}.get(
            action["mode"], f"Assign to agent #{action.get('user_id')}")
    if t == "add_note":
        return "Add internal note"
    if t == "set_priority":
        return f"Set priority to {action['priority']}"
    return "Add tags: " + ", ".join(action["tags"])


# --- running actions -------------------------------------------------------
def _do_set_status(session, ws, case_id, act, *, actor, ctx, agent_id):
    cases.transition(session, case_id, act["status"], actor=actor,
                     closure_category=act.get("closure_category"))
    return {"status": act["status"]}


def _do_assign(session, ws, case_id, act, *, actor, ctx, agent_id):
    from core import routing
    mode = act["mode"]
    if mode == "auto":
        chosen = routing.assign_next(session, ws, case_id, actor=actor)
        if chosen is None:
            raise MacroError("no agent is available to take the case")
        return {"assignee_id": chosen}
    uid = agent_id if mode == "self" else act["user_id"]
    if uid is None:
        raise MacroError("no agent to assign to")
    if not session.execute(text(
            "SELECT 1 FROM care_agent WHERE workspace_id = :ws AND user_id = :u"),
            {"ws": ws, "u": uid}).first():
        raise MacroError("that user is not a care agent in this workspace")
    cases.assign(session, case_id, int(uid), actor=actor)
    return {"assignee_id": int(uid)}


def _do_add_note(session, ws, case_id, act, *, actor, ctx, agent_id):
    nid = cases.add_note(session, case_id, agent_id, render(act["body"], ctx), actor=actor)
    return {"note_id": nid}


def _do_set_priority(session, ws, case_id, act, *, actor, ctx, agent_id):
    session.execute(text('UPDATE "case" SET priority = :p, last_activity_at = now() WHERE id = :c'),
                    {"p": act["priority"], "c": case_id})
    cases._event(session, case_id, "priority_change", actor, priority=act["priority"])
    return {"priority": act["priority"]}


def _do_add_tags(session, ws, case_id, act, *, actor, ctx, agent_id):
    have = session.execute(text('SELECT tags FROM "case" WHERE id = :c'),
                           {"c": case_id}).scalar() or []
    merged = list(dict.fromkeys([*have, *act["tags"]]))
    session.execute(text('UPDATE "case" SET tags = CAST(:t AS jsonb) WHERE id = :c'),
                    {"t": _json(merged), "c": case_id})
    cases._event(session, case_id, "tags_added", actor, tags=act["tags"])
    return {"tags": merged}


_RUN = {"set_status": _do_set_status, "assign": _do_assign, "add_note": _do_add_note,
        "set_priority": _do_set_priority, "add_tags": _do_add_tags}


def apply_actions(session, ws, case_id, macro, *, actor, indexes=None, source="manual") -> list[dict]:
    """Run ``macro``'s actions on a case (all of them, or only ``indexes``), one
    savepoint each so a failing action doesn't undo the ones that worked. Returns
    a per-action result list and writes one ``macro_applied`` timeline event."""
    agent_id = actor if isinstance(actor, int) else None
    ctx = context(session, ws, case_id, agent_id=agent_id)
    results = []
    for i, act in enumerate(macro["actions"]):
        if indexes is not None and i not in indexes:
            continue
        try:
            with session.begin_nested():
                detail = _RUN[act["type"]](session, ws, case_id, act, actor=actor,
                                           ctx=ctx, agent_id=agent_id)
            results.append({"index": i, "type": act["type"], "ok": True, **detail})
        except (cases.CaseError, MacroError) as exc:
            results.append({"index": i, "type": act["type"], "ok": False, "error": str(exc)})
    cases._event(session, case_id, "macro_applied", actor, macro_id=macro["id"],
                 macro=macro["name"], source=source,
                 results=[{"type": r["type"], "ok": r["ok"]} for r in results])
    return results
