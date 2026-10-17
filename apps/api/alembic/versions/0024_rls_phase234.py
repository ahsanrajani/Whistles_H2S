"""row-level security for the Phase 2-4 tenant tables

Revision ID: 0024_rls_phase234
Revises: 0023_report_schedule
Create Date: 2026-09-04

Backfills the ``tenant_isolation`` policy (same shape as ``0003_rls``) onto every
tenant-scoped table added in Phases 2-4, so isolation is enforced by Postgres
and not only by an explicit ``WHERE workspace_id = :ws`` in each query.

Child tables reached only through a policied parent (``case_note``,
``case_event``, ``kb_attachment``, ``content_event``) are left alone — they
carry no ``workspace_id`` and the app never queries them without joining the
parent.

``guru_operator`` keeps ``BYPASSRLS``, so the worker, seeds and operator=True
admin routes are unaffected.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0024_rls_phase234"
down_revision: Union[str, None] = "0023_report_schedule"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TID = "NULLIF(current_setting('app.tenant_id', true), '')::int"

_TABLES = (
    "source_state", "item_author", "tenant_retention_policy", "outbound_action",
    "customer", "case", "case_message", "care_agent",
    "routing_policy", "kb_article", "care_template", "metric_fact",
    "agent_activity", "content_item", "survey", "survey_response",
    "report_schedule",
)


def upgrade() -> None:
    for table in _TABLES:
        expr = f"workspace_id = {_TID}"
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
        op.execute(
            f'CREATE POLICY tenant_isolation ON "{table}" '
            f'USING ({expr}) WITH CHECK ({expr})')


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
