"""CSAT / survey module — survey, survey_response

Revision ID: 0022_survey
Revises: 0021_content_calendar
Create Date: 2026-09-04

P4.7. A ``survey`` is a workspace's CSAT / NPS / CES definition; a
``survey_response`` is one issued (and possibly answered) instance, tied to a
case. ``token`` is the per-response identifier a tokenised link would carry.
Complaint analytics read ``case`` / ``case_event`` and join these responses.

Idempotent DDL; reversible.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0022_survey"
down_revision: Union[str, None] = "0021_content_calendar"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS survey (
            id           BIGSERIAL PRIMARY KEY,
            workspace_id INTEGER NOT NULL REFERENCES workspace (id) ON DELETE CASCADE,
            name         TEXT NOT NULL,
            kind         TEXT NOT NULL DEFAULT 'csat',     -- csat | nps | ces
            scale_min    INTEGER NOT NULL DEFAULT 1,
            scale_max    INTEGER NOT NULL DEFAULT 5,
            question     TEXT NOT NULL DEFAULT 'How satisfied were you?',
            active       BOOLEAN NOT NULL DEFAULT true,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_survey_ws_active "
               "ON survey (workspace_id, active)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS survey_response (
            id           BIGSERIAL PRIMARY KEY,
            workspace_id INTEGER NOT NULL REFERENCES workspace (id) ON DELETE CASCADE,
            survey_id    BIGINT NOT NULL REFERENCES survey (id) ON DELETE CASCADE,
            case_id      BIGINT REFERENCES "case" (id) ON DELETE SET NULL,
            customer_id  BIGINT REFERENCES customer (id) ON DELETE SET NULL,
            channel      TEXT,
            token        TEXT NOT NULL UNIQUE,
            score        INTEGER,
            comment      TEXT,
            bucket       TEXT,                              -- promoter/passive/detractor | satisfied/...
            issued_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            responded_at TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_survey_response_ws_time "
               "ON survey_response (workspace_id, issued_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_survey_response_case "
               "ON survey_response (case_id)")


def downgrade() -> None:
    op.drop_table("survey_response")
    op.drop_table("survey")
