"""Row-level security — the P1.3b exit test.

Drives the ``guru_app`` engine directly (RLS **is** enforced for that role) and
proves tenant isolation end to end:

* no ``app.tenant_id`` set  -> every tenant-scoped table returns zero rows
* ``app.tenant_id`` = a workspace id -> only that workspace's rows are visible
* a second workspace's rows stay invisible
* ``WITH CHECK`` rejects a write aimed at another workspace
* the ``guru_operator`` engine (``BYPASSRLS``) still sees everything

Fixture rows are inserted through the BYPASSRLS ``operator_engine`` — a plain
``guru_app`` connection could not create rows for two different workspaces.
Every ``guru_app`` transaction sets the GUC transaction-locally (``set_config``
third arg ``true``) so nothing leaks across pooled connections.
"""
import unittest

import sqlalchemy as sa

from db.session import engine, operator_engine

from . import truncate_all

_ITEM_COLS = ("workspace_id", "surface", "source", "source_kind", "external_id",
              "url", "outlet", "title", "body", "lang_guess", "raw_json",
              "collected_at", "content_hash")


class RowLevelSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        truncate_all()
        with operator_engine.begin() as c:
            for wid, name in ((1, "Alfa"), (2, "Beta")):
                c.execute(sa.text(
                    "INSERT INTO workspace(id,name,market,created_at) "
                    "VALUES (:i,:n,'PK','now')"), {"i": wid, "n": name})
                c.execute(sa.text(
                    "INSERT INTO brand(workspace_id,name,is_focus) "
                    "VALUES (:i,:n,1)"), {"i": wid, "n": name})
                c.execute(sa.text(
                    "INSERT INTO item(%s) VALUES (%s)" % (
                        ",".join(_ITEM_COLS),
                        ",".join(f":{col}" for col in _ITEM_COLS))),
                    {"workspace_id": wid, "surface": "news",
                     "source": "googlenews_rss", "source_kind": "public",
                     "external_id": f"e{wid}", "url": f"https://src/{wid}",
                     "outlet": "Outlet", "title": "Item", "body": "Body",
                     "lang_guess": "en", "raw_json": "{}", "collected_at": "now",
                     "content_hash": f"h{wid}"})

    @classmethod
    def tearDownClass(cls):
        truncate_all()

    def test_no_tenant_context_sees_zero_rows(self):
        with engine.connect() as c:
            for table in ("workspace", "brand", "item"):
                self.assertEqual(
                    c.execute(sa.text(f"SELECT count(*) FROM {table}")).scalar(), 0,
                    f"{table} leaked rows with no app.tenant_id")

    def test_tenant_context_scopes_to_its_workspace(self):
        with engine.begin() as c:
            c.execute(sa.text("SELECT set_config('app.tenant_id', '1', true)"))
            self.assertEqual(c.execute(sa.text("SELECT count(*) FROM workspace")).scalar(), 1)
            self.assertEqual(c.execute(sa.text("SELECT id FROM workspace")).scalar(), 1)
            self.assertEqual(c.execute(sa.text("SELECT name FROM brand")).scalar(), "Alfa")
            self.assertEqual(c.execute(sa.text("SELECT count(*) FROM item")).scalar(), 1)

    def test_other_tenants_rows_are_invisible(self):
        with engine.begin() as c:
            c.execute(sa.text("SELECT set_config('app.tenant_id', '1', true)"))
            self.assertEqual(
                c.execute(sa.text("SELECT count(*) FROM brand WHERE name = 'Beta'")).scalar(), 0)
        with engine.begin() as c:
            c.execute(sa.text("SELECT set_config('app.tenant_id', '2', true)"))
            self.assertEqual(c.execute(sa.text("SELECT name FROM brand")).scalar(), "Beta")

    def test_with_check_rejects_cross_tenant_write(self):
        with engine.begin() as c:
            c.execute(sa.text("SELECT set_config('app.tenant_id', '1', true)"))
            with self.assertRaises(sa.exc.DBAPIError):
                c.execute(sa.text(
                    "INSERT INTO brand(workspace_id,name,is_focus) VALUES (2,'Sneak',0)"))

    def test_operator_engine_bypasses_rls(self):
        with operator_engine.connect() as c:
            self.assertEqual(c.execute(sa.text("SELECT count(*) FROM workspace")).scalar(), 2)
            self.assertEqual(c.execute(sa.text("SELECT count(*) FROM brand")).scalar(), 2)


if __name__ == "__main__":
    unittest.main()
