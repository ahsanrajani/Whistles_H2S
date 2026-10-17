"""P1.5b — every route is gated, and the permission decides allow/deny.

Two checks:

* ``test_every_api_route_is_gated`` walks the URL map and asserts each
  ``api_v1.*`` endpoint either declares ``@requires`` or is on the auth
  whitelist — the "no route unprotected" guarantee (deny-by-default does the
  rest at request time).
* ``test_permission_matrix`` logs in as each of the six roles and hits one
  route per permission that has routes today, asserting 403 exactly when the
  role lacks the permission.
"""
from werkzeug.security import generate_password_hash

from api.v1.common import required_permission
from db import repositories as repo

from ._db import ApiTestCase

_WHITELIST = {
    "api_v1.csrf", "api_v1.auth_login", "api_v1.auth_logout", "api_v1.auth_me",
    "api_v1.oauth_google_start", "api_v1.oauth_google_callback",
}

# (label, method, path, area:verb) — one representative route per permission
# that is wired to a route in the current app.
_ROUTES = [
    ("overview",        "GET",  "/api/v1/overview",            "listening:view"),
    ("mention hide",    "POST", "/api/v1/mentions/1/hide",     "listening:edit"),
    ("report pdf",      "GET",  "/api/v1/report",              "reporting:export"),
    ("review queue",    "GET",  "/api/v1/review",              "reporting:approve"),
    ("job poll",        "GET",  "/api/v1/jobs/none",           "queue:view"),
    ("job score",       "POST", "/api/v1/jobs/score",          "queue:create"),
    ("admin runs",      "GET",  "/api/v1/admin/runs",          "admin:view"),
    ("admin rematch",   "POST", "/api/v1/admin/rematch",       "admin:edit"),
    ("admin ws create", "POST", "/api/v1/admin/workspaces",    "admin:create"),
]

_ALL_ROLES = ["admin", "team_lead", "supervisor", "senior_agent", "agent", "bank_viewer"]


class RbacEnforcementTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        connection = self.app.db_operator()
        try:
            for key in ("team_lead", "supervisor", "senior_agent", "agent"):
                repo.users.create(
                    connection.session, username=f"u_{key}",
                    password_hash=generate_password_hash("pw"), role=key,
                    created_at=self.app.now())
                uid = connection.execute(
                    'SELECT id FROM "user" WHERE username=?', (f"u_{key}",)).fetchone()[0]
                repo.rbac.set_user_roles(connection.session, uid, [key])
            connection.commit()
        finally:
            connection.close()

    def _login(self, username, password):
        self.client.post("/api/v1/auth/login",
                         json={"username": username, "password": password},
                         headers={"X-CSRF-Token": self.client.get("/api/v1/csrf").get_json()["token"]})
        with self.client.session_transaction() as s:
            return s.get("csrf_token", ""), set(s.get("perms") or ())

    def _creds(self, role):
        return ("admin", "admin123") if role == "admin" else \
               ("bank", "viewer123") if role == "bank_viewer" else (f"u_{role}", "pw")

    def test_every_api_route_is_gated(self):
        ungated = []
        for rule in self.app.app.url_map.iter_rules():
            if not rule.endpoint.startswith("api_v1."):
                continue
            if rule.endpoint in _WHITELIST:
                continue
            if required_permission(rule.endpoint) is None:
                ungated.append(rule.endpoint)
        self.assertEqual(ungated, [], f"routes with no @requires: {ungated}")

    def test_permission_matrix(self):
        failures = []
        for role in _ALL_ROLES:
            username, password = self._creds(role)
            token, perms = self._login(username, password)
            for label, method, path, needed in _ROUTES:
                allowed = needed in perms
                if method == "GET":
                    status = self.client.get(path).status_code
                else:
                    status = self.client.post(
                        path, json={"name": "x"},
                        headers={"X-CSRF-Token": token}).status_code
                denied = status == 403
                if allowed and denied:
                    failures.append(f"{role} SHOULD reach {label} ({needed}) — got 403")
                if not allowed and not denied:
                    failures.append(
                        f"{role} should NOT reach {label} ({needed}) — got {status}")
            self.client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": token})
        self.assertEqual(failures, [], "\n".join(failures))

    def test_bank_viewer_is_read_only(self):
        token, _ = self._login("bank", "viewer123")
        self.assertEqual(self.client.get("/api/v1/overview").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/admin/runs").status_code, 403)
        self.assertEqual(
            self.client.post("/api/v1/mentions/1/hide",
                             headers={"X-CSRF-Token": token}).status_code, 403)
