"""P3.6 — knowledge base + templates.

Exit criterion: an agent (holds only templates:view) cannot create a template
via the API, not just via the UI.
"""
import unittest

from werkzeug.security import generate_password_hash

from db import repositories as repo

from ._db import ApiTestCase


class KnowledgeApiTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        conn = self.app.db_operator()
        try:
            repo.users.create(conn.session, username="u_agent",
                              password_hash=generate_password_hash("pw"),
                              role="agent", created_at=self.app.now())
            uid = conn.execute('SELECT id FROM "user" WHERE username=?',
                               ("u_agent",)).fetchone()[0]
            repo.rbac.set_user_roles(conn.session, uid, ["agent"])
            conn.commit()
        finally:
            conn.close()

    def _login(self, user, pw):
        token = self.client.get("/api/v1/csrf").get_json()["token"]
        self.client.post("/api/v1/auth/login", json={"username": user, "password": pw},
                         headers={"X-CSRF-Token": token})
        with self.client.session_transaction() as s:
            self.csrf = s.get("csrf_token", "")

    def _post(self, path, body):
        return self.client.post(path, json=body, headers={"X-CSRF-Token": self.csrf})

    # --- knowledge base --------------------------------------------
    def test_article_crud_and_search(self):
        self._login("admin", "admin123")
        aid = self._post("/api/v1/kb/articles",
                         {"title": "Blocked card recovery",
                          "body": "Steps to unblock a debit card after fraud lock.",
                          "tags": "card fraud"}).get_json()["id"]
        self.assertEqual(
            self.client.put(f"/api/v1/kb/articles/{aid}", json={"tags": "card fraud unblock"},
                            headers={"X-CSRF-Token": self.csrf}).status_code, 200)
        self._post(f"/api/v1/kb/articles/{aid}/attachments",
                   {"filename": "flow.pdf", "url": "https://x/flow.pdf"})

        hit = self.client.get("/api/v1/kb/articles?q=unblock+debit").get_json()
        self.assertIn(aid, [a["id"] for a in hit["articles"]])
        detail = self.client.get(f"/api/v1/kb/articles/{aid}").get_json()
        self.assertEqual(len(detail["attachments"]), 1)

        self.assertEqual(
            self.client.delete(f"/api/v1/kb/articles/{aid}",
                               headers={"X-CSRF-Token": self.csrf}).status_code, 200)

    # --- templates ------------------------------------------------
    def test_agent_can_read_templates_but_not_create_one(self):
        self._login("admin", "admin123")
        tid = self._post("/api/v1/templates",
                         {"name": "ack", "category": "greeting",
                          "body": "Thanks for reaching out — we're on it."}).get_json()["id"]

        self._login("u_agent", "pw")
        listed = self.client.get("/api/v1/templates").get_json()["templates"]
        self.assertIn(tid, [t["id"] for t in listed])              # can read

        self.assertEqual(
            self._post("/api/v1/templates",
                       {"name": "x", "body": "y"}).status_code, 403)  # cannot create
        self.assertEqual(
            self.client.put(f"/api/v1/templates/{tid}", json={"body": "z"},
                            headers={"X-CSRF-Token": self.csrf}).status_code, 403)
        self.assertEqual(
            self.client.delete(f"/api/v1/templates/{tid}",
                               headers={"X-CSRF-Token": self.csrf}).status_code, 403)

    def test_admin_full_template_lifecycle(self):
        self._login("admin", "admin123")
        tid = self._post("/api/v1/templates",
                         {"name": "t1", "body": "b1"}).get_json()["id"]
        self.assertEqual(
            self.client.put(f"/api/v1/templates/{tid}", json={"body": "b2"},
                            headers={"X-CSRF-Token": self.csrf}).status_code, 200)
        self.assertEqual(
            self.client.delete(f"/api/v1/templates/{tid}",
                               headers={"X-CSRF-Token": self.csrf}).status_code, 200)

    def test_bank_viewer_has_no_kb_access(self):
        self._login("bank", "viewer123")
        self.assertEqual(self.client.get("/api/v1/kb/articles").status_code, 403)
        self.assertEqual(self.client.get("/api/v1/templates").status_code, 403)


if __name__ == "__main__":
    unittest.main()
