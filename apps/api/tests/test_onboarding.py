import os
import tempfile
import unittest

import app
from core import entity

from ._db import ApiTestCase


class OnboardingWizardTests(ApiTestCase):
    def setUp(self):
        handle, self.env = tempfile.mkstemp(suffix=".env")
        os.close(handle)
        self._env = app.ENV_PATH
        app.ENV_PATH = self.env
        super().setUp()
        self.c = self.client

    def tearDown(self):
        super().tearDown()
        app.ENV_PATH = self._env
        try:
            os.remove(self.env)
        except FileNotFoundError:
            pass

    def _login(self, username, password):
        token = self.c.get("/api/v1/csrf").get_json()["token"]
        self.c.post("/api/v1/auth/login",
                    json={"username": username, "password": password},
                    headers={"X-CSRF-Token": token})
        with self.c.session_transaction() as session:
            self.token = session["csrf_token"]

    def _patch(self, step, body):
        return self.c.patch(f"/api/v1/onboarding/{step}", json=body,
                            headers={"X-CSRF-Token": self.token})

    def test_viewer_cannot_open_the_wizard(self):
        self._login("bank", "viewer123")
        self.assertEqual(self.c.get("/api/v1/onboarding/state").status_code, 403)

    def test_brand_patterns_matches_the_plain_name(self):
        patterns = app.brand_patterns("Faysal Bank")
        self.assertTrue(patterns["safe"])
        matches = entity.classify("Faysal Bank raised its rates today",
                                  [{"id": 1, "name": "Faysal Bank", **patterns}])
        self.assertEqual(matches[0][0], 1)

    def test_full_happy_path(self):
        self._login("admin", "admin123")
        connection = app.db_operator()

        created = self._patch(1, {"name": "Acme Bank", "market": "PK",
                                  "volume_scenario": "mid"})
        self.assertEqual(created.status_code, 200)
        workspace_id, step, slug = connection.execute(
            "SELECT id,onboarding_step,slug FROM workspace WHERE name='Acme Bank'").fetchone()
        self.assertEqual((step, slug), (2, "acme-bank"))
        with self.c.session_transaction() as session:
            self.assertEqual(session["ws_id"], workspace_id)

        self.assertEqual(self._patch(2, {"focus": "Acme Bank",
                                         "competitors": ["Beta Bank", "Gamma Bank"]}).status_code, 200)
        brands = connection.execute(
            "SELECT name,is_focus FROM brand WHERE workspace_id=? ORDER BY is_focus DESC",
            (workspace_id,)).fetchall()
        self.assertEqual(len(brands), 3)
        self.assertEqual(brands[0], ("Acme Bank", 1))

        self.assertEqual(self._patch(3, {"context_text": "account\nbranch",
                                         "exclude_text": "acme mosque — landmark"}).status_code, 200)
        context, excludes = connection.execute(
            "SELECT context_patterns,exclude_patterns FROM brand WHERE workspace_id=? AND is_focus=1",
            (workspace_id,)).fetchone()
        self.assertIn("account", context)
        self.assertIn("landmark", excludes)

        self.assertEqual(self._patch(4, {"X_BEARER_TOKEN": "acme-x"}).status_code, 200)
        self.assertEqual(app.keys(workspace_id)["X_BEARER_TOKEN"], "acme-x")

        finished = self._patch(5, {"run_now": False})
        self.assertEqual(finished.status_code, 200)
        self.assertEqual(finished.get_json()["step"], 0)
        self.assertEqual(
            connection.execute("SELECT onboarding_step FROM workspace WHERE id=?",
                               (workspace_id,)).fetchone()[0], 0)
        connection.close()


if __name__ == "__main__":
    unittest.main()
