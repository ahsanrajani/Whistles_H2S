"""Shared helpers for the analytics query modules.

These functions hold the hand-written aggregation SQL that used to live in
``core/insights`` and the deterministic scanners. ``core`` keeps the Python
shaping (Wilson intervals, ranking, dict assembly) and calls in here for rows.

``?`` positional placeholders are rewritten to ``:pN`` + ``text()`` — the same
convention ``db.legacy.LegacyConn`` uses — so the SQL bodies could move here
verbatim.
"""
import re

from sqlalchemy import text

SAFE_SQL = "('public','licensed')"

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


def rows(session, sql, *params):
    converted, binds = _bind(sql, params)
    return session.execute(text(converted), binds).fetchall()


def one(session, sql, *params):
    converted, binds = _bind(sql, params)
    return session.execute(text(converted), binds).fetchone()


def scalar(session, sql, *params):
    converted, binds = _bind(sql, params)
    return session.execute(text(converted), binds).scalar()


def _sf(surface):
    """(sql_fragment, params) that restricts to one item surface, or a no-op.
    The CAST keeps Postgres from choking on a bare NULL parameter."""
    if surface:
        return " AND (CAST(? AS text) IS NULL OR i.surface = ?)", [surface, surface]
    return " AND (CAST(? AS text) IS NULL OR i.surface = ?)", [None, None]
