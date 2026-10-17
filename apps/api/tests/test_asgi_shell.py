"""P1.10 — the FastAPI shell.

FastAPI is the outer ASGI app; ``/api/v1`` is now FastAPI-native and the Flask
app is mounted only as the fallback for ``/favicon.ico`` and the obs probes.
These tests drive the app through Starlette's ASGI test client (httpx).
"""
import unittest

from starlette.testclient import TestClient

from asgi import app as asgi_app

from ._db import ApiTestCase


class AsgiShellTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.asgi = TestClient(asgi_app)

    def test_health_probe_passes_through_to_flask(self):
        resp = self.asgi.get("/healthz")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ok")

    def test_readyz_passes_through(self):
        body = self.asgi.get("/readyz").json()
        self.assertEqual(body["checks"]["database"], "ok")

    def test_csrf_endpoint_answers(self):
        resp = self.asgi.get("/api/v1/csrf")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("token", resp.json())

    def test_swagger_uses_the_canonical_contract(self):
        docs = self.asgi.get("/docs")
        self.assertEqual(docs.status_code, 200)
        self.assertIn('url: \'/openapi.yaml\'', docs.text)

        contract = self.asgi.get("/openapi.yaml")
        self.assertEqual(contract.status_code, 200)
        self.assertIn("application/yaml", contract.headers["content-type"])
        self.assertTrue(contract.text.startswith("openapi: 3.1.0"))
        self.assertIn("servers:", contract.text)
        self.assertIn("  - url: /api/v1", contract.text)

    def test_auth_required_json_is_preserved(self):
        resp = self.asgi.get("/api/v1/overview")
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["error"], "authentication required")

    def test_login_flow_works_end_to_end_through_asgi(self):
        token = self.asgi.get("/api/v1/csrf").json()["token"]
        resp = self.asgi.post("/api/v1/auth/login",
                              json={"username": "admin", "password": "admin123"},
                              headers={"X-CSRF-Token": token})
        self.assertEqual(resp.status_code, 200)
        # session cookie set by Flask-Session round-trips through the ASGI client
        me = self.asgi.get("/api/v1/auth/me")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["user"]["role"], "admin")

    def test_metrics_exposition_passes_through(self):
        body = self.asgi.get("/metrics").text
        self.assertIn("guru_http_requests_total", body)


if __name__ == "__main__":
    unittest.main()
