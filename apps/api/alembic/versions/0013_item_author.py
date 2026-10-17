"""item_author + tenant_retention_policy; item.author_id / item.source_class

Revision ID: 0013_item_author
Revises: 0012_source_state_health
Create Date: 2026-09-04

P2.4. Author identity and provenance:

* ``item_author`` — one row per (workspace, author) with a stable salted
  ``author_hash`` that survives PII removal, so repeat-author detection keeps
  working after a tenant switches a source class to ``hashed``.
* ``tenant_retention_policy`` — per (workspace, source_class) retention_mode
  (``full`` | ``hashed``), default ``full``.
* ``item.author_id`` FK, and ``item.source_class`` (backfilled), exposed in the
  mentions CSV export.

Idempotent DDL. The ``source_class`` backfill fills a new column — not
destructive, no §0.6 note.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0013_item_author"
down_revision: Union[str, None] = "0012_source_state_health"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OFFICIAL = ("meta_facebook", "meta_instagram", "google_maps_reviews",
             "appstore_reviews", "playstore_reviews", "regulatory_watch")


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS item_author (
            id             BIGSERIAL PRIMARY KEY,
            workspace_id   INTEGER NOT NULL REFERENCES workspace (id) ON DELETE CASCADE,
            platform       TEXT    NOT NULL,
            platform_id    TEXT,
            author_hash    TEXT    NOT NULL,
            name           TEXT,
            profile_url    TEXT,
            source_class   TEXT    NOT NULL DEFAULT 'third_party',
            retention_mode TEXT    NOT NULL DEFAULT 'full',
            first_seen     TEXT    NOT NULL,
            last_seen      TEXT    NOT NULL,
            CONSTRAINT uq_item_author_ws_hash UNIQUE (workspace_id, author_hash)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_item_author_ws ON item_author (workspace_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS tenant_retention_policy (
            workspace_id   INTEGER NOT NULL REFERENCES workspace (id) ON DELETE CASCADE,
            source_class   TEXT    NOT NULL,
            retention_mode TEXT    NOT NULL DEFAULT 'full',
            updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT pk_tenant_retention_policy PRIMARY KEY (workspace_id, source_class)
        )
    """)

    op.execute("ALTER TABLE item ADD COLUMN IF NOT EXISTS author_id BIGINT "
               "REFERENCES item_author (id) ON DELETE SET NULL")
    op.execute("ALTER TABLE item ADD COLUMN IF NOT EXISTS source_class TEXT")
    op.execute("CREATE INDEX IF NOT EXISTS ix_item_author_id ON item (author_id)")

    quoted = ", ".join(f"'{s}'" for s in _OFFICIAL)
    op.execute(f"UPDATE item SET source_class = 'official' "
               f"WHERE source_class IS NULL AND source IN ({quoted})")
    op.execute("UPDATE item SET source_class = 'third_party' WHERE source_class IS NULL")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_item_author_id")
    op.execute("ALTER TABLE item DROP COLUMN IF EXISTS author_id")
    op.execute("ALTER TABLE item DROP COLUMN IF EXISTS source_class")
    op.drop_table("tenant_retention_policy")
    op.drop_table("item_author")
