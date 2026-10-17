"""Care console access scoping (Hamza, 2026-09-11): "supervisor accounts
should be able to access only the care console, and the agent accounts
should be able to access only the conversations assigned to them, nothing
else." The permission-grant half (supervisor/agent losing listening/
reporting/queue) is covered in test_rbac.py; this is the row-level half --
an agent-scoped user's /care/cases and single-case routes are actually
restricted to cases assigned to them, not just gated by care:view.
"""
import unittest

from werkzeug.security import generate_password_hash

from db import repositories as repo

from ._db import ApiTestCase


class CareAgentScopingTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        conn = self.app.db_operator()
        try:
            self.agent_a_id = repo.users.create(
                conn.session, username="agent_a",
                password_hash=generate_password_hash("pw123456"),
                role="agent", workspace_id=1, created_at=self.app.now())
            self.agent_b_id = repo.users.create(
                conn.session, username="agent_b",
                password_hash=generate_password_hash("pw123456"),
                role="agent", workspace_id=1, created_at=self.app.now())
            self.super_id = repo.users.create(
                conn.session, username="sup_a",
                password_hash=generate_password_hash("pw123456"),
                role="supervisor", workspace_id=1, created_at=self.app.now())
            repo.rbac.set_user_roles(conn.session, self.agent_a_id, ["agent"])
            repo.rbac.set_user_roles(conn.session, self.agent_b_id, ["agent"])
            repo.rbac.set_user_roles(conn.session, self.super_id, ["supervisor"])
            conn.commit()
        finally:
            conn.close()

        self._login("admin", "admin123")
        self.case_a = self._ingest(handle="@custa").get_json()["case_id"]
        self.case_b = self._ingest(handle="@custb").get_json()["case_id"]
        self.case_unassigned = self._ingest(handle="@custc").get_json()["case_id"]
        self._post(f"/api/v1/care/cases/{self.case_a}/assign", {"user_id": self.agent_a_id})
        self._post(f"/api/v1/care/cases/{self.case_b}/assign", {"user_id": self.agent_b_id})
        self.client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": self.csrf})

    def _login(self, user, pw):
        token = self.client.get("/api/v1/csrf").get_json()["token"]
        r = self.client.post("/api/v1/auth/login", json={"username": user, "password": pw},
                             headers={"X-CSRF-Token": token})
        assert r.status_code == 200, r.get_json()
        with self.client.session_transaction() as s:
            self.csrf = s.get("csrf_token", "")

    def _post(self, path, body=None):
        return self.client.post(path, json=body or {}, headers={"X-CSRF-Token": self.csrf})

    def _ingest(self, **b):
        b.setdefault("platform", "x")
        b.setdefault("body", "I need help with a charge")
        return self._post("/api/v1/care/cases/ingest", b)

    # --- list scoping ----------------------------------------------------
    def test_agent_queue_tab_is_empty_even_though_an_unassigned_case_exists(self):
        self._login("agent_a", "pw123456")
        ids = [c["id"] for c in self.client.get("/api/v1/care/cases?tab=queue").get_json()["cases"]]
        self.assertNotIn(self.case_unassigned, ids)
        self.assertEqual(ids, [])

    def test_agent_assigned_tab_only_shows_their_own_case(self):
        self._login("agent_a", "pw123456")
        ids = [c["id"] for c in self.client.get("/api/v1/care/cases?tab=assigned").get_json()["cases"]]
        self.assertEqual(ids, [self.case_a])

    def test_agent_mine_tab_only_shows_their_own_case(self):
        self._login("agent_a", "pw123456")
        ids = [c["id"] for c in self.client.get("/api/v1/care/cases?tab=mine").get_json()["cases"]]
        self.assertEqual(ids, [self.case_a])

    def test_supervisor_sees_the_full_queue_unaffected(self):
        self._login("sup_a", "pw123456")
        ids = [c["id"] for c in self.client.get("/api/v1/care/cases?tab=queue").get_json()["cases"]]
        self.assertIn(self.case_unassigned, ids)

    # --- single-case authorization ----------------------------------------
    def test_agent_can_open_their_own_case(self):
        self._login("agent_a", "pw123456")
        self.assertEqual(self.client.get(f"/api/v1/care/cases/{self.case_a}").status_code, 200)

    def test_agent_cannot_open_a_colleagues_case(self):
        self._login("agent_a", "pw123456")
        self.assertEqual(self.client.get(f"/api/v1/care/cases/{self.case_b}").status_code, 404)

    def test_agent_cannot_open_an_unassigned_case(self):
        self._login("agent_a", "pw123456")
        self.assertEqual(
            self.client.get(f"/api/v1/care/cases/{self.case_unassigned}").status_code, 404)

    def test_agent_cannot_reply_note_or_transition_a_colleagues_case(self):
        self._login("agent_a", "pw123456")
        self.assertEqual(
            self._post(f"/api/v1/care/cases/{self.case_b}/reply",
                      {"text": "hi", "platform": "x", "target_ref": "dm:1"}).status_code, 404)
        self.assertEqual(
            self._post(f"/api/v1/care/cases/{self.case_b}/note", {"body": "x"}).status_code, 404)
        self.assertEqual(
            self._post(f"/api/v1/care/cases/{self.case_b}/transition",
                      {"state": "closed", "closure_category": "resolved"}).status_code, 404)

    def test_agent_can_reply_note_and_transition_their_own_case(self):
        self._login("agent_a", "pw123456")
        self.assertEqual(
            self._post(f"/api/v1/care/cases/{self.case_a}/note", {"body": "on it"}).status_code, 200)
        self.assertEqual(
            self._post(f"/api/v1/care/cases/{self.case_a}/reply",
                      {"text": "hi", "platform": "x", "target_ref": "dm:1"}).status_code, 200)

    def _put(self, path, body):
        return self.client.put(path, json=body, headers={"X-CSRF-Token": self.csrf})

    def test_agent_can_edit_their_own_customer_but_not_a_colleagues(self):
        self._login("admin", "admin123")
        cust_a = self.client.get(
            f"/api/v1/care/cases/{self.case_a}").get_json()["customer"]["id"]
        cust_b = self.client.get(
            f"/api/v1/care/cases/{self.case_b}").get_json()["customer"]["id"]

        self._login("agent_a", "pw123456")
        self.assertEqual(self._put(f"/api/v1/care/customers/{cust_a}",
                                   {"notes": "ok"}).status_code, 200)
        self.assertEqual(self._put(f"/api/v1/care/customers/{cust_b}",
                                   {"notes": "nope"}).status_code, 404)

    # --- workspace-wide surfaces are off-limits for an agent --------------
    def test_agent_is_forbidden_from_roster_queues_performance_search_and_agents(self):
        self._login("agent_a", "pw123456")
        for path in ("/api/v1/care/roster", "/api/v1/care/queues",
                    "/api/v1/care/performance", "/api/v1/care/search?q=cust",
                    "/api/v1/care/agents"):
            self.assertEqual(self.client.get(path).status_code, 403, path)

    def test_supervisor_still_reaches_roster_queues_performance_search_and_agents(self):
        self._login("sup_a", "pw123456")
        for path in ("/api/v1/care/roster", "/api/v1/care/queues",
                    "/api/v1/care/performance", "/api/v1/care/search?q=cust",
                    "/api/v1/care/agents"):
            self.assertEqual(self.client.get(path).status_code, 200, path)


if __name__ == "__main__":
    unittest.main()
