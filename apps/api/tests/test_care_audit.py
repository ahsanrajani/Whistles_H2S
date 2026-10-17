"""P3.10 — every care mutation produces an audit row.

Two halves:

* **coverage** — walk the care + knowledge routers and assert every mutating
  route (POST / PUT / DELETE) is registered in ``core.care_audit`` and that the
  seven BRD action classes are all covered.
* **behaviour** — drive a representative mutation for each class through the API
  and assert the mapped ``audit_event`` row lands.
"""
import unittest

from core import care_audit
from db import repositories as repo

from ._db import ApiTestCase

_MUTATING = {"POST", "PUT", "DELETE", "PATCH"}


def _mutating_endpoints(router):
    seen = {}
    for route in router.routes:
        methods = getattr(route, "methods", set()) & _MUTATING
        if methods:
            seen[route.endpoint.__name__] = methods
    return seen


class CareAuditCoverageTests(unittest.TestCase):
    def test_every_care_mutation_route_is_registered(self):
        from api_fastapi import care
        endpoints = _mutating_endpoints(care.router)
        registered = set(care_audit.CARE_MUTATIONS) | care_audit.NON_AUDITED
        missing = set(endpoints) - registered
        self.assertEqual(missing, set(),
                         f"unregistered care mutation endpoints: {sorted(missing)}")

    def test_every_template_mutation_route_is_registered(self):
        from api_fastapi import knowledge
        endpoints = _mutating_endpoints(knowledge.router)
        missing = set(endpoints) - set(care_audit.TEMPLATE_MUTATIONS)
        self.assertEqual(missing, set(),
                         f"unregistered template mutation endpoints: {sorted(missing)}")

    def test_every_macro_mutation_route_is_registered(self):
        from api_fastapi import macros
        endpoints = _mutating_endpoints(macros.router)
        registered = set(care_audit.MACRO_MUTATIONS) | care_audit.MACRO_NON_AUDITED
        self.assertEqual(set(endpoints) - registered, set(),
                         "unregistered macro mutation endpoints")

    def test_all_seven_brd_classes_are_covered(self):
        covered = set()
        for _action, classes in care_audit.CARE_MUTATIONS.values():
            covered |= set(classes)
        covered.add("template change")   # TEMPLATE_MUTATIONS
        self.assertEqual(covered, set(care_audit.BRD_CLASSES))


class CareAuditBehaviourTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        token = self.client.get("/api/v1/csrf").get_json()["token"]
        self.client.post("/api/v1/auth/login",
                         json={"username": "admin", "password": "admin123"},
                         headers={"X-CSRF-Token": token})
        with self.client.session_transaction() as s:
            self.csrf = s.get("csrf_token", "")
        conn = self.app.db_operator()
        try:
            conn.execute("INSERT INTO care_agent(workspace_id,user_id,capacity,available) "
                         "SELECT w.id, u.id, 5, 1 FROM workspace w, \"user\" u "
                         "WHERE u.username='admin' LIMIT 1")
            conn.commit()
            self.admin_id = conn.execute(
                "SELECT id FROM \"user\" WHERE username='admin'").fetchone()[0]
        finally:
            conn.close()

    def _post(self, path, body=None):
        return self.client.post(path, json=body or {}, headers={"X-CSRF-Token": self.csrf})

    def _put(self, path, body):
        return self.client.put(path, json=body, headers={"X-CSRF-Token": self.csrf})

    def _delete(self, path):
        return self.client.delete(path, headers={"X-CSRF-Token": self.csrf})

    def _audit_actions(self):
        conn = self.app.db_operator()
        try:
            rows = conn.execute("SELECT action FROM audit_event").fetchall()
        finally:
            conn.close()
        return [r[0] for r in rows]

    def _case(self):
        return self._post("/api/v1/care/cases/ingest",
                          {"platform": "x", "handle": "@c", "body": "help"}
                          ).get_json()["case_id"]

    def test_each_brd_class_lands_an_audit_row(self):
        cid = self._case()                                   # care.ingest
        self._post(f"/api/v1/care/cases/{cid}/assign", {"user_id": self.admin_id})
        self._post(f"/api/v1/care/cases/{cid}/reassign",
                   {"user_id": self.admin_id, "reason": "load balancing"})
        self._post(f"/api/v1/care/cases/{cid}/note", {"body": "context"})
        self._post(f"/api/v1/care/cases/{cid}/block",
                   {"target_ref": "u:1", "platform": "x",
                    "reason": "abuse", "category": "harassment"})
        self._post(f"/api/v1/care/cases/{cid}/unblock",
                   {"target_ref": "u:1", "platform": "x",
                    "reason": "appeal upheld", "category": "harassment"})
        self._post(f"/api/v1/care/agents/{self.admin_id}/status", {"available": False})
        self._post("/api/v1/templates",
                   {"name": "greeting", "body": "Hello from BAFL"})
        self._post(f"/api/v1/care/cases/{cid}/transition",
                   {"state": "closed", "closure_category": "resolved"})

        actions = self._audit_actions()
        for expected in ("care.ingest", "care.assign", "care.reassign", "care.note",
                         "care.block", "care.unblock", "care.agent_status",
                         "care.template_change", "care.state_change",
                         "care.case_closed"):
            self.assertIn(expected, actions, f"missing audit row: {expected}")

    def test_scheduled_message_is_audited(self):
        cid = self._case()
        self._post(f"/api/v1/care/cases/{cid}/schedule",
                   {"text": "Following up", "platform": "x", "target_ref": "dm:1",
                    "at": "2099-01-01T00:00:00+00:00"})
        self.assertIn("care.schedule", self._audit_actions())

    def test_reply_and_supervisor_actions_are_audited(self):
        cid = self._case()
        self._post(f"/api/v1/care/cases/{cid}/reply",
                   {"text": "on it", "platform": "x", "target_ref": "dm:1"})
        held = self._post(f"/api/v1/care/cases/{cid}/reply",
                          {"text": "draft", "platform": "x", "target_ref": "dm:2",
                           "hold": True}).get_json()
        aid = held["outbound_action_id"]
        self._put(f"/api/v1/care/outbound/{aid}", {"text": "edited"})
        self._post(f"/api/v1/care/outbound/{aid}/approve")
        actions = self._audit_actions()
        for expected in ("care.reply", "care.reply_edit", "care.reply_approve"):
            self.assertIn(expected, actions)

    def test_template_and_kb_changes_are_audited(self):
        tid = self._post("/api/v1/templates",
                         {"name": "t", "body": "b"}).get_json()["id"]
        self._put(f"/api/v1/templates/{tid}", {"body": "b2"})
        self._delete(f"/api/v1/templates/{tid}")
        aid = self._post("/api/v1/kb/articles",
                         {"title": "How to reset a PIN"}).get_json()["id"]
        self._put(f"/api/v1/kb/articles/{aid}", {"body": "steps"})
        self._post(f"/api/v1/kb/articles/{aid}/attachments",
                   {"filename": "f.pdf", "url": "https://x/f.pdf#a"})
        self._delete(f"/api/v1/kb/articles/{aid}")
        self.assertEqual(
            self._audit_actions().count("care.template_change"), 7)


if __name__ == "__main__":
    unittest.main()
