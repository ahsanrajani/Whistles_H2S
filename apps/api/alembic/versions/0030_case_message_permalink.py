"""case_message.permalink — the real, clickable URL of the source comment/
post/review

Revision ID: 0030_case_message_permalink
Revises: 0029_llm_panel
Create Date: 2026-09-10

`platform_ref` is the API-addressable id a reply targets (what the write
transport needs); it is not always a URL a person can open. `permalink` is
the real public link to the source content, when the collector captured one
(item.url) -- lets a care agent click straight through to the actual
comment/post/review instead of working blind. Nullable; a message ingested
without a permalink (e.g. hand-typed) is unaffected.

Idempotent DDL; reversible.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0030_case_message_permalink"
down_revision: Union[str, None] = "0029_llm_panel"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE case_message ADD COLUMN IF NOT EXISTS permalink TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE case_message DROP COLUMN IF EXISTS permalink")
