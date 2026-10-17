import os
import tempfile
import unittest

import app
from werkzeug.security import generate_password_hash

from ._db import ApiTestCase


class AuthTests(ApiTestCase):
    """Session auth, CSRF, tenant scoping — all over the /api/v1 surface."""

    def setUp(self):
        handle, self.env_path = tempfile.mkstemp(suffix=".env")
        os.close(handle)
        self.original_env_path = app.ENV_PATH
        self.original_x_token = os.environ.get("X_BEARER_TOKEN")
        app.ENV_PATH = self.env_path
        super().setUp()

    def tearDown(self):
        super().tearDown()
        app.ENV_PATH = self.original_env_path
        if self.original_x_token is None:
            os.environ.pop("X_BEARER_TOKEN", None)
        else:
            os.environ["X_BEARER_TOKEN"] = self.original_x_token
        try:
            os.remove(self.env_path)
        except FileNotFoundError:
            pass

    def _csrf(self):
        return self.client.get("/api/v1/csrf").get_json()["token"]

    def login(self, username, password):
        response = self.client.post(
            "/api/v1/auth/login", json={"username": username, "password": password},
            headers={"X-CSRF-Token": self._csrf()})
        with self.client.session_transaction() as session:
            self.token = session.get("csrf_token")
        return response

    def test_unauthenticated_api_calls_are_rejected(self):
        self.assertEqual(self.client.get("/api/v1/overview").status_code, 401)
        self.assertEqual(self.client.get("/api/v1/stats").status_code, 401)
        self.assertEqual(self.client.get("/api/v1/auth/me").get_json()["user"], None)

    def test_viewer_reaches_client_views_but_not_admin_or_calibration(self):
        self.assertEqual(self.login("bank", "viewer123").status_code, 200)
        for path in ("/api/v1/overview", "/api/v1/mentions", "/api/v1/sentiment",
                     "/api/v1/competitors", "/api/v1/reviews", "/api/v1/themes"):
            self.assertEqual(self.client.get(path).status_code, 200, path)
        self.assertEqual(self.client.get("/api/v1/admin/cost").status_code, 403)
        self.assertEqual(self.client.get("/api/v1/review").status_code, 403)
        self.assertEqual(self.client.get("/api/v1/onboarding/state").status_code, 403)

    def test_admin_reaches_configuration(self):
        self.assertEqual(self.login("admin", "admin123").status_code, 200)
        keys = self.client.get("/api/v1/admin/keys")
        self.assertEqual(keys.status_code, 200)
        self.assertIn("X_BEARER_TOKEN",
                      [row["env_var"] for row in keys.get_json()["shared"]])

    def test_mutation_requires_a_csrf_header(self):
        self.login("admin", "admin123")
        self.assertEqual(
            self.client.post("/api/v1/admin/keys",
                             json={"env_var": "X_BEARER_TOKEN", "value": "x"}).status_code,
            400)
        self.assertEqual(
            self.client.post("/api/v1/admin/keys",
                             json={"env_var": "X_BEARER_TOKEN", "value": "x"},
                             headers={"X-CSRF-Token": self.token}).status_code,
            200)

    def _second_workspace_with_viewer(self):
        connection = app.db_operator()
        connection.execute(
            """INSERT INTO workspace(name,slug,market,volume_scenario,sentiment_langs,
               onboarding_step,created_at) VALUES('Acme','acme','PK','mid','en',0,'now')""")
        workspace_id = connection.execute(
            "SELECT id FROM workspace WHERE name='Acme'").fetchone()[0]
        connection.execute(
            "INSERT INTO brand(workspace_id,name,is_focus,safe_patterns) VALUES(?,?,1,?)",
            (workspace_id, "Acme Corp", '["acme corp"]'))
        connection.execute(
            'INSERT INTO "user"(username,password_hash,role,workspace_id,created_at) '
            "VALUES('acme',?, 'bank_viewer', ?, 'now')",
            (generate_password_hash("acme123"), workspace_id))
        connection.commit()
        connection.close()
        return workspace_id

    def test_viewer_is_pinned_to_its_own_workspace(self):
        self._second_workspace_with_viewer()
        self.login("acme", "acme123")
        workspaces = self.client.get("/api/v1/workspaces").get_json()
        self.assertEqual(workspaces["active"]["name"], "Acme")
        self.assertFalse(workspaces["can_switch"])
        self.assertEqual(workspaces["list"], [])

    def test_admin_can_switch_workspace(self):
        workspace_id = self._second_workspace_with_viewer()
        self.login("admin", "admin123")
        switched = self.client.post("/api/v1/workspace/switch",
                                    json={"ws_id": workspace_id},
                                    headers={"X-CSRF-Token": self.token})
        self.assertEqual(switched.status_code, 200)
        self.assertEqual(
            self.client.get("/api/v1/workspaces").get_json()["active"]["name"], "Acme")

    def test_api_credentials_are_per_workspace_with_shared_fallback(self):
        for var in ("X_BEARER_TOKEN", "YOUTUBE_API_KEY"):
            saved = os.environ.pop(var, None)
            if saved is not None:
                self.addCleanup(os.environ.__setitem__, var, saved)
        workspace_id = self._second_workspace_with_viewer()
        app.persist_key(0, "X_BEARER_TOKEN", "shared-tok")
        app.persist_key(workspace_id, "X_BEARER_TOKEN", "acme-tok")
        app.persist_key(0, "YOUTUBE_API_KEY", "shared-yt")
        self.assertEqual(app.keys(workspace_id)["X_BEARER_TOKEN"], "acme-tok")
        self.assertEqual(app.keys(workspace_id)["YOUTUBE_API_KEY"], "shared-yt")
        self.assertEqual(app.keys(1).get("X_BEARER_TOKEN"), "shared-tok")

    def test_admin_key_write_mirrors_to_env_and_shows_as_local(self):
        self.login("admin", "admin123")
        response = self.client.post(
            "/api/v1/admin/keys",
            json={"env_var": "X_BEARER_TOKEN", "value": "test-token", "workspace_id": 0},
            headers={"X-CSRF-Token": self.token})
        self.assertEqual(response.status_code, 200)
        with open(self.env_path, encoding="utf-8") as env_file:
            self.assertIn("X_BEARER_TOKEN=test-token", env_file.read())
        shared = {row["env_var"]: row for row in
                  self.client.get("/api/v1/admin/keys").get_json()["shared"]}
        self.assertEqual(shared["X_BEARER_TOKEN"]["value"], "test-token")
        self.assertTrue(shared["X_BEARER_TOKEN"]["from_env"])


if __name__ == "__main__":
    unittest.main()
