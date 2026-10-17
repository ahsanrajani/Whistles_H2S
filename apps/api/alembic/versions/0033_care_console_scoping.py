"""care console scoping -- narrow agent/supervisor to Care only

Revision ID: 0033_care_console_scoping
Revises: 0032_ai_suggestion_cache
Create Date: 2026-09-11

Hamza, 2026-09-11: "supervisor accounts should be able to access only the
care console, and the agent accounts should be able to access only the
conversations assigned to them, nothing else."

0006_rbac's original grants gave both roles listening:view and
reporting:view (Mentions/Sentiment/Reviews/Vantage/SEO/Reports nav, all
permission-gated per apps/web/lib/permissions.ts) plus, for agent,
queue:view -- none of that is "the care console". This revision revokes:

  agent:      queue:view, listening:view, reporting:view
  supervisor: listening:view, listening:export,
              reporting:view, reporting:create, reporting:edit,
              reporting:export, reporting:approve

agent keeps care:view/create/edit + templates:view (the in-composer
knowledge-base search a reply needs is part of the care workflow, not a
separate surface). supervisor keeps care:*, queue:*, templates:* -- the
Care and Supervisor consoles plus the knowledge base they curate.

The *assigned-to-them-only* half of the agent restriction is row-level
(which cases an agent can see/act on within care:view), not a permission
grant -- that's enforced in api_fastapi/deps.py::assert_case_access /
care_visibility_clause, not here.

senior_agent and team_lead are unchanged -- Hamza named "agent" and
"supervisor" specifically; senior_agent's broader queue:edit/care:approve
grants read as a deliberate step up, not an oversight.
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text as _t

revision: str = "0033_care_console_scoping"
down_revision: Union[str, None] = "0032_ai_suggestion_cache"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_AGENT_REVOKE = {("queue", "view"), ("listening", "view"), ("reporting", "view")}
_SUPERVISOR_REVOKE = {
    ("listening", "view"), ("listening", "export"),
    ("reporting", "view"), ("reporting", "create"), ("reporting", "edit"),
    ("reporting", "export"), ("reporting", "approve"),
}


def _apply(bind, grants: dict) -> None:
    for role_key, pairs in grants.items():
        for area, verb in pairs:
            bind.execute(_t("""
                DELETE FROM role_permission
                WHERE role_key = :rk AND permission_id = (
                    SELECT id FROM permission WHERE area = :a AND verb = :v)
            """), {"rk": role_key, "a": area, "v": verb})


def upgrade() -> None:
    bind = op.get_bind()
    _apply(bind, {"agent": _AGENT_REVOKE, "supervisor": _SUPERVISOR_REVOKE})


def downgrade() -> None:
    bind = op.get_bind()
    for role_key, pairs in {"agent": _AGENT_REVOKE, "supervisor": _SUPERVISOR_REVOKE}.items():
        for area, verb in pairs:
            bind.execute(_t("""
                INSERT INTO role_permission(role_key, permission_id)
                SELECT :rk, p.id FROM permission p WHERE p.area = :a AND p.verb = :v
                ON CONFLICT DO NOTHING"""), {"rk": role_key, "a": area, "v": verb})
