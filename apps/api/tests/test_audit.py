"""P1.6 — the audit log: the six wired events, and DB-level immutability.

Every event is written on its own committed transaction by ``app.audit`` and
read back through the operator connection. ``audit_event`` is append-only at
the database level — a ``BEFORE UPDATE OR DELETE`` trigger raises for everyone,
owner included.
"""
import json

import sqlalchemy as sa

from db import repositories as repo

from . import owner_engine
from ._db import ApiTestCase


class AuditEventTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        connection = self.app.db_operator()
        connection.execute(
            """INSERT INTO workspace(name,slug,market,volume_scenario,sentiment_langs,
               onboarding_step,created_at) VALUES('Second','second','PK','mid','en',0,'now')""")
        self.ws2 = connection.execute(
            "SELECT id FROM workspace WHERE name='Second'").fetchone()[0]
        connection.commit()
        connection.close()

    def _csrf(self):
        return self.client.get("/api/v1/csrf").get_json()["token"]

    def _login(self, username, password):
        self.client.post("/api/v1/auth/login",
                         json={"username": username, "password": password},
                         headers={"X-CSRF-Token": self._csrf()})
        with self.client.session_transaction() as session:
            self.token = session.get("csrf_token")

    def _by_action(self, action):
        connection = self.app.db_operator()
        try:
            return repo.audit.by_action(connection.session, action)
        finally:
            connection.close()

    def _count(self):
        connection = self.app.db_operator()
        try:
            return connection.execute("SELECT COUNT(*) FROM audit_event").fetchone()[0]
        finally:
            connection.close()

    # --- the six wired events -------------------------------------------------
    def test_login_success_and_failure_are_logged(self):
        self.client.post("/api/v1/auth/login",
                         json={"username": "admin", "password": "wrong"},
                         headers={"X-CSRF-Token": self._csrf()})
        self._login("admin", "admin123")
        ok = self._by_action("auth.login")
        bad = self._by_action("auth.login_failed")
        self.assertEqual([r.target for r in ok], ["admin"])
        self.assertIsNotNone(ok[0].actor)
        self.assertEqual([r.target for r in bad], ["admin"])
        self.assertIsNone(bad[0].actor)

    def test_tenant_switch_records_before_and_after(self):
        self._login("admin", "admin123")
        self.client.post("/api/v1/workspace/switch", json={"ws_id": self.ws2},
                         headers={"X-CSRF-Token": self.token})
        row = self._by_action("tenant.switch")[0]
        self.assertEqual(row.target, str(self.ws2))
        self.assertEqual(json.loads(row.after_state), {"ws_id": self.ws2})
        self.assertIn("ws_id", json.loads(row.before_state))

    def test_mention_hide_is_logged(self):
        connection = self.app.db_operator()
        connection.execute(
            """INSERT INTO item(id,workspace_id,surface,source,source_kind,external_id,url,
               outlet,title,body,lang_guess,raw_json,collected_at,content_hash)
               VALUES(9001,1,'news','googlenews_rss','public','a1','https://x/a1','O','t','b',
               'en','{}','now','h1')""")
        connection.execute(
            "INSERT INTO brand(id,workspace_id,name,is_focus) VALUES(9001,1,'B',1) "
            "ON CONFLICT DO NOTHING")
        connection.execute(
            "INSERT INTO mention(id,workspace_id,item_id,brand_id,rule) "
            "VALUES(9001,1,9001,9001,'exact_name')")
        connection.commit()
        connection.close()

        self._login("admin", "admin123")
        resp = self.client.post("/api/v1/mentions/9001/hide",
                                headers={"X-CSRF-Token": self.token})
        self.assertEqual(resp.status_code, 200)
        row = self._by_action("mention.hide")[0]
        self.assertEqual(row.target, "9001")

    def test_csv_export_is_logged_as_data_export(self):
        self._login("admin", "admin123")
        self.client.get("/api/v1/mentions/export.csv")
        row = self._by_action("data.export")[0]
        self.assertEqual(row.target, "mentions.csv")

    def test_brand_rule_edit_records_after_state(self):
        self._login("admin", "admin123")
        resp = self.client.post("/api/v1/admin/brands",
                                json={"name": "New Brand", "safe_patterns": ["new brand"]},
                                headers={"X-CSRF-Token": self.token})
        self.assertEqual(resp.status_code, 200)
        row = self._by_action("brand.rule_edit")[0]
        self.assertEqual(row.target, "New Brand")
        self.assertIn("new brand", row.after_state)

    def test_user_create_is_logged(self):
        self._login("admin", "admin123")
        self.client.post("/api/v1/admin/users",
                         json={"username": "newbie", "password": "pw", "workspace_id": 1},
                         headers={"X-CSRF-Token": self.token})
        row = self._by_action("user.create")[0]
        self.assertEqual(row.target, "newbie")

    def test_plain_viewer_reads_are_not_audited(self):
        self._login("bank", "viewer123")
        self.client.get("/api/v1/overview?period=30d")
        self.client.get("/api/v1/mentions")
        # only the login row exists
        self.assertEqual(self._by_action("auth.login")[0].target, "bank")
        self.assertEqual(self._count(), 1)

    # --- immutability -------------------------------------------------------
    def test_audit_rows_cannot_be_updated_or_deleted_even_by_the_owner(self):
        self._login("admin", "admin123")            # writes one row
        with owner_engine.begin() as conn:
            with self.assertRaises(sa.exc.DBAPIError):
                conn.execute(sa.text("UPDATE audit_event SET action = 'tamper'"))
        with owner_engine.begin() as conn:
            with self.assertRaises(sa.exc.DBAPIError):
                conn.execute(sa.text("DELETE FROM audit_event"))
        self.assertGreaterEqual(self._count(), 1)
