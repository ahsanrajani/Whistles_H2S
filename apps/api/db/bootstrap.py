"""Schema + first-boot seed. Replaces the old ``app.init()`` which ran
``schema.sql`` and a pile of ad-hoc ``ALTER TABLE`` / ``PRAGMA table_info``
migrations — Alembic owns the schema now.
"""
import json
import os

from werkzeug.security import generate_password_hash

from core import entity, sources

from .legacy import LegacyConn
from .session import database_url

_HERE = os.path.dirname(os.path.abspath(__file__))
_API_ROOT = os.path.dirname(_HERE)


def ensure_schema() -> None:
    """``alembic upgrade head`` in-process, so a fresh database is usable."""
    from alembic import command
    from alembic.config import Config

    cfg = Config(os.path.join(_API_ROOT, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(_API_ROOT, "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url())
    command.upgrade(cfg, "head")


def _slugify(name: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-") or "workspace"


def seed(conn: LegacyConn, now: str) -> None:
    """Idempotent first-boot data: the shared credential rows, the Bank Alfalah
    workspace + its seed brands, and the two default users."""
    for var, label in sources.KEYS:
        conn.execute(
            """INSERT INTO api_key(workspace_id,env_var,label,value,status)
               VALUES (0,?,?,?,?) ON CONFLICT DO NOTHING""",
            (var, label, os.environ.get(var),
             "present" if os.environ.get(var) else "missing"))

    # Licensing is enforced by source_kind in client queries — keep older
    # corpora aligned when the registry classification changes.
    for source_id, meta in sources.SOURCES.items():
        conn.execute("UPDATE item SET source_kind=? WHERE source=? AND source_kind!=?",
                     (meta["kind"], source_id, meta["kind"]))

    if not conn.execute("SELECT 1 FROM workspace LIMIT 1").fetchone():
        conn.execute(
            """INSERT INTO workspace(name,slug,market,volume_scenario,sentiment_langs,created_at)
               VALUES (?,?,?,?,?,?)""",
            ("Bank Alfalah", _slugify("Bank Alfalah"), "PK", "high", "en", now))
        ws = conn.execute(
            "SELECT id FROM workspace WHERE name=?", ("Bank Alfalah",)).fetchone()[0]
        for b in entity.SEED:
            conn.execute(
                """INSERT INTO brand(workspace_id,name,is_focus,safe_patterns,
                   gated_patterns,context_patterns,exclude_patterns)
                   VALUES (?,?,?,?,?,?,?)""",
                (ws, b["name"], b["is_focus"], json.dumps(b["safe"]),
                 json.dumps(b["gated"]), json.dumps(b["context"]),
                 json.dumps(b["exclude"])))

    seed_users = (
        ("admin", "GURU_ADMIN_PASSWORD", "admin123", "admin"),
        ("bank", "GURU_VIEWER_PASSWORD", "viewer123", "bank_viewer"),
    )
    for username, env_name, default_password, role in seed_users:
        exists = conn.execute(
            "SELECT 1 FROM \"user\" WHERE username=?", (username,)).fetchone()
        if not exists:
            password = os.environ.get(env_name, default_password)
            conn.execute(
                """INSERT INTO "user"(username,password_hash,role,created_at)
                   VALUES (?,?,?,?)""",
                (username, generate_password_hash(password), role, now))
        elif os.environ.get(env_name):
            conn.execute(
                'UPDATE "user" SET password_hash=? WHERE username=?',
                (generate_password_hash(os.environ[env_name]), username))

    first_ws = conn.execute("SELECT id FROM workspace ORDER BY id LIMIT 1").fetchone()
    if first_ws:
        conn.execute(
            '''UPDATE "user" SET workspace_id=? WHERE role='bank_viewer'
               AND workspace_id IS NULL''', (first_ws[0],))

    # Optional: let "Sign in with Google" for this address log in as admin.
    admin_email = (os.environ.get("GURU_ADMIN_EMAIL") or "").strip().lower()
    if admin_email:
        conn.execute('UPDATE "user" SET email=? WHERE username=? AND email IS NULL',
                     (admin_email, "admin"))

    # Every user carries at least their primary role in user_role (P1.5).
    conn.execute("""
        INSERT INTO user_role(user_id, role_key)
        SELECT u.id, u.role FROM "user" u
        WHERE EXISTS (SELECT 1 FROM role r WHERE r.key = u.role)
          AND NOT EXISTS (SELECT 1 FROM user_role ur WHERE ur.user_id = u.id)
        ON CONFLICT DO NOTHING""")

    # Every workspace has a default 'listening' project (frontend F0.1).
    conn.execute("""
        INSERT INTO project (workspace_id, slug, name, kind)
        SELECT w.id, 'listening', 'Listening', 'listening' FROM workspace w
        ON CONFLICT (workspace_id, slug) DO NOTHING""")
    conn.commit()
