"""P3.5 — supervisor interface (backend).

Exit criterion: a supervisor edits a pending reply and the edited text is what
the platform receives.
"""
import unittest

from ._db import ApiTestCase


class SupervisorApiTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self._login("admin", "admin123")   # admin holds every care perm
        conn = self.app.db_operator()
        try:
            conn.execute("INSERT INTO care_agent(workspace_id,user_id,capacity,available) "
                         "SELECT w.id, u.id, 5, 1 FROM workspace w, \"user\" u "
                         "WHERE u.username='admin' LIMIT 1")
            conn.commit()
        finally:
            conn.close()

    def _login(self, user, pw):
        token = self.client.get("/api/v1/csrf").get_json()["token"]
        self.client.post("/api/v1/auth/login", json={"username": user, "password": pw},
                         headers={"X-CSRF-Token": token})
        with self.client.session_transaction() as s:
            self.csrf = s.get("csrf_token", "")

    def _post(self, path, body=None):
        return self.client.post(path, json=body or {}, headers={"X-CSRF-Token": self.csrf})

    def _put(self, path, body):
        return self.client.put(path, json=body, headers={"X-CSRF-Token": self.csrf})

    def _open_case(self):
        return self._post("/api/v1/care/cases/ingest",
                          {"platform": "x", "handle": "@c1", "body": "help"}
                          ).get_json()["case_id"]

    def test_heartbeat_and_roster(self):
        self.assertEqual(self._post("/api/v1/care/heartbeat").status_code, 200)
        roster = self.client.get("/api/v1/care/roster").get_json()
        self.assertTrue(roster["agents"])
        self.assertIn("presence", roster["agents"][0])

    def test_status_override(self):
        agent_id = self.client.get("/api/v1/care/agents").get_json()["agents"][0]["user_id"]
        self.assertEqual(
            self._post(f"/api/v1/care/agents/{agent_id}/status", {"available": False}
                       ).status_code, 200)
        row = next(a for a in self.client.get("/api/v1/care/agents").get_json()["agents"]
                   if a["user_id"] == agent_id)
        self.assertEqual(row["available"], 0)

    def test_queues_and_performance(self):
        self._open_case()
        q = self.client.get("/api/v1/care/queues").get_json()["queues"]
        self.assertTrue(any(row["channel"] == "x" for row in q))
        perf = self.client.get("/api/v1/care/performance").get_json()
        self.assertIn("agents", perf)

    def test_supervisor_edits_a_pending_reply_before_it_sends(self):
        cid = self._open_case()
        held = self._post(f"/api/v1/care/cases/{cid}/reply",
                          {"text": "draft reply", "platform": "x",
                           "target_ref": "dm:1", "hold": True}).get_json()
        self.assertEqual(held["state"], "pending")
        aid = held["outbound_action_id"]

        # it is in the pending list and no case_message exists yet
        pend = self.client.get("/api/v1/care/pending").get_json()["pending"]
        self.assertEqual([p["id"] for p in pend], [aid])
        detail = self.client.get(f"/api/v1/care/cases/{cid}").get_json()
        self.assertEqual(len(detail["messages"]), 1)   # the inbound only

        # supervisor rewrites it, then approves
        self.assertEqual(self._put(f"/api/v1/care/outbound/{aid}",
                                   {"text": "Corrected, on-brand reply"}).status_code, 200)
        approved = self._post(f"/api/v1/care/outbound/{aid}/approve").get_json()
        self.assertEqual(approved["state"], "sent")

        # the platform received the EDITED text; the case now has the outbound msg
        conn = self.app.db_operator()
        try:
            resp = conn.execute(
                "SELECT response, state FROM outbound_action WHERE id=?", (aid,)).fetchone()
        finally:
            conn.close()
        self.assertEqual(resp[1], "sent")
        self.assertEqual(resp[0]["sent"]["text"], "Corrected, on-brand reply")

        detail = self.client.get(f"/api/v1/care/cases/{cid}").get_json()
        outbound = [m for m in detail["messages"] if m["direction"] == "outbound"]
        self.assertEqual(outbound[-1]["body"], "Corrected, on-brand reply")

    def test_edit_or_approve_a_non_pending_action_is_404(self):
        self.assertEqual(self._put("/api/v1/care/outbound/999999", {"text": "x"}).status_code, 404)
        self.assertEqual(self._post("/api/v1/care/outbound/999999/approve").status_code, 404)


if __name__ == "__main__":
    unittest.main()
