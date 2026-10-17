"""rbac — role / permission / role_permission / user_role + the seeded matrix

Revision ID: 0006_rbac
Revises: 0005_oauth_identity
Create Date: 2026-09-03

P1.5a. Schema + the seeded catalogue; enforcement (the ``@requires`` decorator,
deletion of the ``admin_only`` path list) is P1.5b, so behaviour is unchanged
by this revision alone.

Roles: the five care-team roles from the build plan (Agent → Administrator)
plus ``bank_viewer`` — the read-only client role that predates them and stays
until Phase 3. The Administrator role keeps the key ``admin`` so the existing
``session["role"] == "admin"`` checks (and the frontend) are untouched by this
revision. ``user.role`` is the *primary* role (display + the
operator-connection check); the full set is ``user_role``.

Permissions: six areas × six verbs = 36. The per-role grants below are a
starting point — tune with a follow-up revision, not by editing this one.

Idempotent: ``CREATE TABLE IF NOT EXISTS`` + ``ON CONFLICT DO NOTHING`` — the
``0001`` baseline already builds the four tables from ``Base.metadata``.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0006_rbac"
down_revision: Union[str, None] = "0005_oauth_identity"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

AREAS = ("care", "listening", "reporting", "templates", "queue", "admin")
VERBS = ("view", "create", "edit", "delete", "export", "approve")

_ROLES = (
    ("bank_viewer", "Client Viewer", 5),
    ("agent", "Agent", 10),
    ("senior_agent", "Senior Agent", 20),
    ("supervisor", "Supervisor", 30),
    ("team_lead", "Team Lead", 40),
    ("admin", "Administrator", 50),          # key kept as "admin" (see module docstring)
)

_ALL = {(a, v) for a in AREAS for v in VERBS}


def _grants():
    """role_key -> set of (area, verb). ("admin", …) below is the admin *area*."""
    g = {}
    g["admin"] = set(_ALL)
    g["team_lead"] = _ALL - {("admin", "delete")}
    g["supervisor"] = (
        {("care", v) for v in VERBS}
        | {("queue", v) for v in VERBS}
        | {("templates", v) for v in ("view", "create", "edit", "approve")}
        | {("listening", v) for v in ("view", "export")}
        | {("reporting", v) for v in ("view", "create", "edit", "export", "approve")}
    )
    g["senior_agent"] = (
        {("care", v) for v in ("view", "create", "edit", "export", "approve")}
        | {("queue", v) for v in ("view", "edit")}
        | {("templates", "view"), ("listening", "view"), ("reporting", "view")}
    )
    g["agent"] = (
        {("care", v) for v in ("view", "create", "edit")}
        | {("queue", "view"), ("templates", "view"),
           ("listening", "view"), ("reporting", "view")}
    )
    g["bank_viewer"] = {("listening", "view"), ("reporting", "view"), ("reporting", "export")}
    return g


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS role (
            key   TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            rank  INTEGER NOT NULL DEFAULT 0
        )""")
    op.execute("""
        CREATE TABLE IF NOT EXISTS permission (
            id   SERIAL PRIMARY KEY,
            area TEXT NOT NULL,
            verb TEXT NOT NULL,
            CONSTRAINT uq_permission_area_verb UNIQUE (area, verb)
        )""")
    op.execute("""
        CREATE TABLE IF NOT EXISTS role_permission (
            role_key      TEXT    NOT NULL REFERENCES role(key) ON DELETE CASCADE,
            permission_id INTEGER NOT NULL REFERENCES permission(id) ON DELETE CASCADE,
            PRIMARY KEY (role_key, permission_id)
        )""")
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_role (
            user_id  INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
            role_key TEXT    NOT NULL REFERENCES role(key) ON DELETE CASCADE,
            PRIMARY KEY (user_id, role_key)
        )""")

    bind = op.get_bind()
    from sqlalchemy import text as _t

    for key, label, rank in _ROLES:
        bind.execute(_t("INSERT INTO role(key,label,rank) VALUES (:k,:l,:r) "
                        "ON CONFLICT (key) DO UPDATE SET label=EXCLUDED.label, rank=EXCLUDED.rank"),
                     {"k": key, "l": label, "r": rank})
    for area in AREAS:
        for verb in VERBS:
            bind.execute(_t("INSERT INTO permission(area,verb) VALUES (:a,:v) "
                            "ON CONFLICT (area,verb) DO NOTHING"),
                         {"a": area, "v": verb})
    for role_key, pairs in _grants().items():
        for area, verb in pairs:
            bind.execute(_t("""
                INSERT INTO role_permission(role_key, permission_id)
                SELECT :rk, p.id FROM permission p WHERE p.area=:a AND p.verb=:v
                ON CONFLICT DO NOTHING"""), {"rk": role_key, "a": area, "v": verb})

    # the old CHECK only allowed ('admin','bank_viewer'); drop it so a user can
    # hold any catalogue role. Then give every user a user_role row.
    op.execute('ALTER TABLE "user" DROP CONSTRAINT IF EXISTS ck_user_role_enum')
    op.execute("""
        INSERT INTO user_role(user_id, role_key)
        SELECT u.id, u.role FROM "user" u
        WHERE EXISTS (SELECT 1 FROM role r WHERE r.key = u.role)
        ON CONFLICT DO NOTHING""")


def downgrade() -> None:
    op.drop_table("user_role")
    op.drop_table("role_permission")
    op.drop_table("permission")
    op.drop_table("role")
