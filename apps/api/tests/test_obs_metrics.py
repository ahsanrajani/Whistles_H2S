"""P1.9b — Prometheus /metrics plus the /healthz and /readyz probes."""
import unittest

from prometheus_client import REGISTRY

from obs.metrics import record_job

from ._db import ApiTestCase


class HealthProbeTests(ApiTestCase):
    def test_healthz_is_open_and_ok(self):
        resp = self.client.get("/healthz")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["status"], "ok")

    def test_readyz_reports_each_dependency(self):
        resp = self.client.get("/readyz")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["checks"]["database"], "ok")
        self.assertEqual(body["checks"]["redis"], "ok")

    def test_probes_need_no_auth(self):
        # no login in this test — deny-by-default must not apply to the probes
        self.assertEqual(self.client.get("/healthz").status_code, 200)
        self.assertEqual(self.client.get("/metrics").status_code, 200)


class MetricsEndpointTests(ApiTestCase):
    def _scrape(self):
        resp = self.client.get("/metrics")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/plain", resp.headers["Content-Type"])
        return resp.get_data(as_text=True)

    def test_exposition_lists_every_metric_family(self):
        body = self._scrape()
        for name in ("guru_http_requests_total",
                     "guru_http_request_duration_seconds",
                     "guru_jobs_total",
                     "guru_job_queue_depth",
                     "guru_scheduled_tasks_due",
                     "guru_collection_calls"):
            self.assertIn(name, body)

    def test_http_counter_increments_with_templated_route_label(self):
        before = REGISTRY.get_sample_value(
            "guru_http_requests_total",
            {"method": "GET", "route": "/api/v1/csrf", "status": "200"}) or 0.0
        self.client.get("/api/v1/csrf")
        after = REGISTRY.get_sample_value(
            "guru_http_requests_total",
            {"method": "GET", "route": "/api/v1/csrf", "status": "200"})
        self.assertEqual(after, before + 1)

    def test_route_label_is_the_rule_not_the_raw_path(self):
        # unauthenticated -> 401, but the label still uses the route template
        # (FastAPI-native since P1.10h, so `{job_id}` not Werkzeug's `<job_id>`)
        self.client.get("/api/v1/jobs/abc123")
        value = REGISTRY.get_sample_value(
            "guru_http_requests_total",
            {"method": "GET", "route": "/api/v1/jobs/{job_id}", "status": "401"})
        self.assertIsNotNone(value)

    def test_metrics_path_is_not_self_counted(self):
        self.client.get("/metrics")
        self.assertIsNone(REGISTRY.get_sample_value(
            "guru_http_requests_total",
            {"method": "GET", "route": "/metrics", "status": "200"}))

    def test_record_job_bumps_the_jobs_counter(self):
        before = REGISTRY.get_sample_value(
            "guru_jobs_total", {"kind": "collection", "outcome": "done"}) or 0.0
        record_job("collection", "done")
        after = REGISTRY.get_sample_value(
            "guru_jobs_total", {"kind": "collection", "outcome": "done"})
        self.assertEqual(after, before + 1)

    def test_queue_depth_gauge_reflects_the_job_table(self):
        conn = self.app.db_operator()
        try:
            conn.execute("INSERT INTO job (kind, state) VALUES (?, ?)",
                         ("collection", "queued"))
            conn.commit()
        finally:
            conn.close()
        body = self._scrape()
        self.assertRegex(body, r'guru_job_queue_depth\{state="queued"\}\s+1')


if __name__ == "__main__":
    unittest.main()
