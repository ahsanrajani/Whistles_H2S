"""The per-request DB handle: a sqlite3-``Connection``-shaped wrapper over a
SQLAlchemy ``Session``.

``app.db()`` returns one of these. Application code reaches persistence through
``connection.session`` + the ``db/repositories`` / ``db/analytics`` / ``db/pipeline``
functions; ``connection.commit()`` / ``.close()`` handle lifecycle. The
``.execute("… ? …", params)`` method is kept for test fixtures that build rows
directly — it rewrites ``?`` placeholders to ``:pN`` and runs ``text()``.
"""
import re

from sqlalchemy import text
from sqlalchemy.orm import Session

from .session import OperatorSession, SessionLocal

_QMARK = re.compile(r"\?")


def _bind(sql, params):
    if not params:
        return sql, {}
    counter = {"i": 0}

    def repl(_m):
        i = counter["i"]
        counter["i"] += 1
        return f":p{i}"

    converted = _QMARK.sub(repl, sql)
    if counter["i"] != len(params):
        raise ValueError(
            f"placeholder/param count mismatch: {counter['i']} '?' vs {len(params)} params")
    return converted, {f"p{i}": v for i, v in enumerate(params)}


class LegacyConn:
    def __init__(self, session: Session | None = None):
        self._s = session or SessionLocal()

    @property
    def session(self) -> Session:
        return self._s

    def set_tenant(self, workspace_id) -> None:
        """Scope this transaction's row-level security to one tenant. A no-op if
        `workspace_id` is None; cleared automatically when the transaction ends."""
        if workspace_id is not None:
            from sqlalchemy import text
            self._s.execute(text("SELECT set_config('app.tenant_id', :t, true)"),
                            {"t": str(int(workspace_id))})

    def execute(self, sql, params=()):
        converted, binds = _bind(sql, params)
        return self._s.execute(text(converted), binds)

    def commit(self):
        self._s.commit()

    def rollback(self):
        self._s.rollback()

    def close(self):
        self._s.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def legacy_conn() -> LegacyConn:
    """An RLS-enforced request handle (role guru_app)."""
    return LegacyConn()


def operator_conn() -> LegacyConn:
    """A BYPASSRLS handle (role guru_operator) for the operator/admin surface."""
    return LegacyConn(OperatorSession())
