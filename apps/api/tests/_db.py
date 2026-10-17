"""Base classes for DB-backed tests on Postgres (``guru_test``).

``DbTestCase`` — for tests that drive ``core`` functions directly. Runs on the
BYPASSRLS ``operator_engine`` so fixtures can insert rows for a workspace
without a tenant context; each test is an outer transaction rolled back in
teardown. ``self.db`` is a ``LegacyConn``-shaped handle.

``ApiTestCase`` — for tests that go through the HTTP API. Since P1.10 the
client drives ``asgi.app`` (FastAPI outer, Flask mounted as the fallback)
through ``tests._client.AsgiTestClient``, so a test hits whichever framework
currently owns the path. Truncates every table and re-seeds via the operator
connection before each test.

Row-level security itself is exercised by ``test_rls.py`` (the ``guru_app``
engine directly).
"""
import unittest

from sqlalchemy.orm import Session

from db.legacy import LegacyConn
from db.session import operator_engine

from . import truncate_all
from ._client import AsgiTestClient, asgi_client  # noqa: F401 — re-exported for tests


class DbTestCase(unittest.TestCase):
    def setUp(self):
        self._conn = operator_engine.connect()
        # Register teardown the moment the connection exists — a failure later in
        # setUp (a fixture INSERT, say) otherwise leaks the connection, and a
        # handful of those exhausts the pool and wedges the rest of the run.
        self.addCleanup(self._conn.close)
        self._outer = self._conn.begin()
        self.addCleanup(lambda: self._outer.is_active and self._outer.rollback())
        self._session = Session(bind=self._conn, join_transaction_mode="create_savepoint",
                                expire_on_commit=False, autoflush=False)
        self.addCleanup(self._session.close)
        self.db = LegacyConn(self._session)


class ApiTestCase(unittest.TestCase):
    def setUp(self):
        import app
        from db.bootstrap import seed
        truncate_all()
        conn = app.db_operator()
        try:
            seed(conn, app.now())
        finally:
            conn.close()
        self.app = app
        self.client = AsgiTestClient()

    def tearDown(self):
        truncate_all()
