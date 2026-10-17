"""P2.3 — source health bands + the silence alert.

Exit criterion: a source shows unhealthy within one cadence of it breaking
(build plan: "silent beyond 3x its cadence").
"""
import unittest
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa

from core import alerts, source_health, sources

from ._db import DbTestCase
from ._db import ApiTestCase

_GN = "googlenews_rss"                       # cadence 3600, no credentials
_CADENCE = sources.SOURCES[_GN]["cadence"]


class SourceHealthSummaryTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.commit()
        self.now = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)

    def _state(self, **cols):
        keys = ", ".join(cols)
        vals = ", ".join(f":{k}" for k in cols)
        self.db.session.execute(sa.text(
            f"INSERT INTO source_state(workspace_id, source, {keys}) "
            f"VALUES (1, :_src, {vals})"), {"_src": _GN, **cols})
        self.db.commit()

    def _band(self):
        row = next(r for r in source_health.summary(self.db.session, 1, now=self.now)["sources"]
                   if r["source"] == _GN)
        return row["health"]

    def test_never_run_is_unknown(self):
        self.assertEqual(self._band(), "unknown")

    def test_recent_success_is_ok(self):
        self._state(last_success_at=self.now - timedelta(seconds=2 * _CADENCE),
                    circuit_state="closed", consecutive_failures=0)
        self.assertEqual(self._band(), "ok")

    def test_silent_beyond_three_cadences_is_stale(self):
        self._state(last_success_at=self.now - timedelta(seconds=3 * _CADENCE + 60),
                    circuit_state="closed")
        self.assertEqual(self._band(), "stale")

    def test_just_under_three_cadences_is_still_ok(self):
        self._state(last_success_at=self.now - timedelta(seconds=3 * _CADENCE - 60),
                    circuit_state="closed")
        self.assertEqual(self._band(), "ok")

    def test_open_circuit_is_down(self):
        self._state(circuit_state="open", consecutive_failures=5,
                    opened_at=self.now, last_success_at=self.now - timedelta(hours=1))
        self.assertEqual(self._band(), "down")

    def test_recent_failures_with_closed_circuit_is_failing(self):
        self._state(last_success_at=self.now - timedelta(minutes=30),
                    circuit_state="closed", consecutive_failures=2)
        self.assertEqual(self._band(), "failing")

    def test_inference_services_are_not_listed(self):
        listed = {r["source"] for r in
                  source_health.summary(self.db.session, 1, now=self.now)["sources"]}
        self.assertNotIn("huggingface_sentiment", listed)
        self.assertIn(_GN, listed)

    def test_counts_add_up(self):
        self._state(circuit_state="open", opened_at=self.now)
        out = source_health.summary(self.db.session, 1, now=self.now)
        self.assertEqual(out["counts"]["total"], len(out["sources"]))
        self.assertEqual(out["counts"]["down"], 1)
        self.assertEqual(len(out["unhealthy"]), 1)


class SilenceAlertTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.execute(
            "INSERT INTO brand(id,workspace_id,name,is_focus) VALUES (1,1,'Acme',1)")
        self.db.commit()

    def _alert(self):
        ev = alerts.evaluate(self.db, 1)
        return next(a for a in ev["alerts"] if a["key"] == "source_silent")

    def test_rule_present_and_quiet_when_all_healthy(self):
        # nothing in source_state -> every source is 'unknown', not unhealthy
        self.assertFalse(self._alert()["fired"])

    def test_fires_for_a_down_source(self):
        self.db.execute(
            "INSERT INTO source_state(workspace_id, source, circuit_state, opened_at) "
            "VALUES (1, 'googlenews_rss', 'open', now())")
        self.db.commit()
        alert = self._alert()
        self.assertTrue(alert["fired"])
        self.assertEqual(alert["severity"], "critical")
        self.assertIn("Google News", alert["detail"])


class AdminSourceHealthEndpointTests(ApiTestCase):
    def _login(self, user, pw):
        token = self.client.get("/api/v1/csrf").get_json()["token"]
        self.client.post("/api/v1/auth/login", json={"username": user, "password": pw},
                         headers={"X-CSRF-Token": token})

    def test_admin_gets_the_summary(self):
        self._login("admin", "admin123")
        resp = self.client.get("/api/v1/admin/sources/health")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertIn("sources", body)
        self.assertIn("counts", body)
        self.assertTrue(any(r["source"] == "googlenews_rss" for r in body["sources"]))

    def test_viewer_is_forbidden(self):
        self._login("bank", "viewer123")
        self.assertEqual(
            self.client.get("/api/v1/admin/sources/health").status_code, 403)


if __name__ == "__main__":
    unittest.main()
