"""Care audit coverage (build plan §5 / P3.10).

Every care mutation writes one ``audit_event`` row. The seven BRD action
classes — assignment, reassignment, status change, block / unblock, template
change, supervisor action, case closure — plus the remaining care mutations map
to a canonical action name in one place here, so coverage is *enumerable*:
``tests/test_care_audit.py`` walks the care + knowledge routers and asserts
every mutating route is registered and every BRD class is covered.

The actual audit rows are written through ``app.audit`` (imported lazily in
``emit`` to keep ``core/`` free of an ``app`` import); this module is the
registry + a thin ``emit`` wrapper so the call sites stay one line.
"""

# BRD §5 audit action classes.
BRD_CLASSES = frozenset({
    "assignment", "reassignment", "status change", "block/unblock",
    "template change", "supervisor action", "case closure",
})

# care.py route function name -> (canonical audit action, {BRD classes it covers})
CARE_MUTATIONS = {
    "update_customer":  ("care.customer_update", frozenset()),
    "ingest":           ("care.ingest",         frozenset()),
    "reply":            ("care.reply",          frozenset({"supervisor action"})),
    "note":             ("care.note",           frozenset()),
    "agent_session":    ("care.session",        frozenset()),
    "issue_survey":     ("care.survey_issue",   frozenset()),
    "respond_survey":   ("care.survey_response", frozenset()),
    "assign_case":      ("care.assign",         frozenset({"assignment"})),
    "reassign_case":    ("care.reassign",       frozenset({"reassignment"})),
    "transition_case":  ("care.state_change",   frozenset({"status change", "case closure"})),
    "schedule_message": ("care.schedule",       frozenset({"supervisor action"})),
    "cancel_scheduled": ("care.schedule",       frozenset()),
    "block_customer":   ("care.block",          frozenset({"block/unblock"})),
    "unblock_customer": ("care.unblock",        frozenset({"block/unblock"})),
    "set_agent_status": ("care.agent_status",   frozenset({"supervisor action"})),
    "set_assignment_rule": ("care.assignment_rule", frozenset({"supervisor action"})),
    "edit_pending":     ("care.reply_edit",     frozenset({"supervisor action"})),
    "approve_pending":  ("care.reply_approve",  frozenset({"supervisor action"})),
    "reject_pending":   ("care.reply_reject",   frozenset({"supervisor action"})),
}

# knowledge.py route function name -> canonical audit action (all "template change")
TEMPLATE_MUTATIONS = {
    "create_article":  "care.template_change",
    "update_article":  "care.template_change",
    "delete_article":  "care.template_change",
    "add_attachment":  "care.template_change",
    "create_template": "care.template_change",
    "update_template": "care.template_change",
    "delete_template": "care.template_change",
}

# macros.py route function name -> canonical audit action. Library / rule edits are
# "template change"; applying a macro to a case is its own action, and an auto
# macro firing is written by the ``macro_rule`` job (``care.macro_auto``).
MACRO_MUTATIONS = {
    "create_macro":  "care.template_change",
    "update_macro":  "care.template_change",
    "delete_macro":  "care.template_change",
    "apply_macro":   "care.macro_applied",
    "create_rule":   "care.template_change",
    "update_rule":   "care.template_change",
    "delete_rule":   "care.template_change",
}
# preview_macro is a POST that renders text and changes nothing.
MACRO_NON_AUDITED = frozenset({"preview_macro"})

# POST routes on the care router that change no persistent state, so carry no
# audit row: ``heartbeat`` (Redis presence bookkeeping) and ``suggest`` (returns
# AI draft text, never sends or stores anything).
NON_AUDITED = frozenset({"heartbeat", "suggest"})

# emitted in addition to care.state_change when a case is transitioned to closed.
CLOSURE_ACTION = "care.case_closed"


def emit(action, *, actor, ws, target=None, before=None, after=None):
    """Write one audit row on its own committed transaction. A ``None`` action
    is a no-op (keeps call sites unconditional)."""
    if action is None:
        return
    import app as _app

    _app.audit(actor=actor, tenant_id=ws, action=action, target=target,
               before=before, after=after)
