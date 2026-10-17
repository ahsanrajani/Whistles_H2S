"""P1.4b — Google sign-in (mock mode) and the account-linking rule.

The suite forces mock mode (``tests/__init__`` blanks the Google creds), so
``/auth/oauth/google/start`` bounces straight to the callback carrying an
email and no network is touched.
"""
from db import repositories as repo

from ._db import ApiTestCase


class GoogleSignInTests(ApiTestCase):
    KNOWN = "owner@example.com"

    def setUp(self):
        super().setUp()
        connection = self.app.db_operator()
        connection.execute('UPDATE "user" SET email=? WHERE username=?',
                           (self.KNOWN, "admin"))
        connection.commit()
        connection.close()

    def _callback(self, email):
        return self.client.get(
            f"/api/v1/auth/oauth/google/callback?mock=1&email={email}")

    def _me(self):
        return self.client.get("/api/v1/auth/me").get_json()["user"]

    def _identities(self, username):
        connection = self.app.db_operator()
        try:
            uid = connection.execute(
                'SELECT id FROM "user" WHERE username=?', (username,)).fetchone()[0]
            return repo.identity.for_user(connection.session, uid)
        finally:
            connection.close()

    def test_start_bounces_to_the_callback_in_mock_mode(self):
        resp = self.client.get("/api/v1/auth/oauth/google/start?as=x@example.com")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/api/v1/auth/oauth/google/callback", resp.headers["Location"])
        self.assertIn("email=x@example.com", resp.headers["Location"])

    def test_known_email_links_an_identity_and_signs_in(self):
        resp = self._callback(self.KNOWN)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("auth=ok", resp.headers["Location"])
        user = self._me()
        self.assertEqual(user["name"], "admin")
        self.assertEqual(user["role"], "admin")
        linked = self._identities("admin")
        self.assertEqual([row[0] for row in linked], ["google"])
        self.assertEqual(linked[0][1], self.KNOWN)

    def test_second_sign_in_reuses_the_identity(self):
        self._callback(self.KNOWN)
        first = self._identities("admin")[0]
        self.client.post("/api/v1/auth/logout",
                         headers={"X-CSRF-Token": self._csrf_after_login()})
        resp = self._callback(self.KNOWN)
        self.assertEqual(resp.status_code, 302)
        again = self._identities("admin")
        self.assertEqual(len(again), 1)                     # no duplicate link
        self.assertGreaterEqual(again[0][2], first[2])      # last_login_at advanced

    def test_unknown_email_is_refused(self):
        resp = self._callback("stranger@example.com")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("auth_error=", resp.headers["Location"])
        self.assertIsNone(self._me())
        self.assertEqual(self._identities("admin"), [])

    def test_native_login_still_works(self):
        token = self.client.get("/api/v1/csrf").get_json()["token"]
        resp = self.client.post("/api/v1/auth/login",
                                json={"username": "admin", "password": "admin123"},
                                headers={"X-CSRF-Token": token})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._me()["name"], "admin")

    def _csrf_after_login(self):
        with self.client.session_transaction() as s:
            return s.get("csrf_token", "")
