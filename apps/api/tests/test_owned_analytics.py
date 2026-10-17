"""P4.1 — owned-analytics ingestion into the metric warehouse."""
import unittest
from datetime import date

import sqlalchemy as sa

from core import owned_analytics
from db import repositories as repo
from integrations import owned

from ._db import ApiTestCase, DbTestCase


class MetricWarehouseTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.commit()
        self.s = self.db.session

    def _count(self):
        return self.s.execute(sa.text(
            "SELECT count(*) FROM metric_fact WHERE workspace_id = 1")).scalar()

    # --- ingestion -------------------------------------------------
    def test_ingest_writes_facts_for_every_provider(self):
        out = owned_analytics.ingest(self.s, 1, days=3)
        self.db.commit()
        self.assertEqual(set(out["platforms"]), set(owned.PROVIDERS))
        self.assertGreater(out["facts"], 0)
        got = {r[0] for r in self.s.execute(sa.text(
            "SELECT DISTINCT source FROM metric_fact WHERE workspace_id = 1")).all()}
        self.assertEqual(got, {"meta", "instagram", "x", "linkedin"})

    def test_a_live_provider_error_is_recorded_and_the_rest_still_ingest(self):
        from unittest.mock import patch
        keys = {"META_ACCESS_TOKEN": "t", "META_PAGE_ID": "p", "GURU_WRITE_LIVE": "1"}

        def boom(self, ws, day):
            raise owned.OwnedAnalyticsError("meta insights 400: bad metric")

        with patch.object(owned.MetaInsights, "_live", boom):
            out = owned_analytics.ingest(self.s, 1, days=1, keys=keys)
        self.db.commit()
        self.assertIn("bad metric", out["platforms"]["meta"]["error"])
        self.assertEqual(out["platforms"]["meta"]["facts"], 0)
        # instagram/x/linkedin lack their creds here -> mock, still wrote facts
        self.assertGreater(out["platforms"]["x"]["facts"], 0)

    def test_proportions_carry_their_raw_counts(self):
        owned_analytics.ingest(self.s, 1, days=1)
        self.db.commit()
        rows = self.s.execute(sa.text(
            "SELECT numerator, denominator, value FROM metric_fact "
            "WHERE workspace_id = 1 AND metric = 'engagement_rate'")).all()
        self.assertTrue(rows)
        for num, den, val in rows:
            self.assertIsNotNone(num)
            self.assertIsNotNone(den)
            self.assertAlmostEqual(val, num / den, places=6)

    def test_reingest_is_idempotent(self):
        owned_analytics.ingest(self.s, 1, days=2)
        self.db.commit()
        first = self._count()
        owned_analytics.ingest(self.s, 1, days=2)
        self.db.commit()
        self.assertEqual(self._count(), first)

    # --- non-social sources (Vantage requirement, build plan §7) ----
    def test_warehouse_accepts_a_non_social_source(self):
        d = date(2026, 9, 1)
        repo.metric_fact.upsert_many(self.s, 1, [{
            "source": "rank", "entity_type": "keyword", "entity_ref": "home loan",
            "metric": "position", "day": d, "value": 7.0}])
        self.db.commit()
        self.assertEqual(self._count(), 1)
        # same grain overwrites, does not duplicate
        repo.metric_fact.upsert_many(self.s, 1, [{
            "source": "rank", "entity_type": "keyword", "entity_ref": "home loan",
            "metric": "position", "day": d, "value": 3.0}])
        self.db.commit()
        self.assertEqual(self._count(), 1)
        self.assertEqual(self.s.execute(sa.text(
            "SELECT value FROM metric_fact WHERE source = 'rank'")).scalar(), 3.0)

    def test_dims_are_part_of_the_grain(self):
        d = date(2026, 9, 1)
        repo.metric_fact.upsert_many(self.s, 1, [
            {"source": "meta", "entity_type": "post", "entity_ref": "p1",
             "metric": "impressions", "day": d, "value": 10.0,
             "dims": {"media_type": "video"}},
            {"source": "meta", "entity_type": "post", "entity_ref": "p1",
             "metric": "impressions", "day": d, "value": 20.0,
             "dims": {"media_type": "image"}},
        ])
        self.db.commit()
        self.assertEqual(self._count(), 2)

    def test_mock_fetch_is_deterministic(self):
        d = date(2026, 9, 2)
        self.assertEqual(owned.MetaInsights().fetch(1, d),
                         owned.MetaInsights().fetch(1, d))


class OwnedAnalyticsApiTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        token = self.client.get("/api/v1/csrf").get_json()["token"]
        self.client.post("/api/v1/auth/login",
                         json={"username": "admin", "password": "admin123"},
                         headers={"X-CSRF-Token": token})
        with self.client.session_transaction() as s:
            self.csrf = s.get("csrf_token", "")

    def test_ingest_endpoint_queues_a_job_that_fills_the_warehouse(self):
        r = self.client.post("/api/v1/admin/owned-analytics/ingest",
                             json={"days": 2}, headers={"X-CSRF-Token": self.csrf})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["queued"])

        from jobs import worker
        for _ in range(4):
            if not worker.run_one(kinds=["owned_analytics"]):
                break

        status = self.client.get("/api/v1/admin/owned-analytics").get_json()
        sources = {row["source"] for row in status["sources"]}
        self.assertEqual(sources, {"meta", "instagram", "x", "linkedin"})
        self.assertEqual({p["platform"] for p in status["providers"]},
                         {"meta", "instagram", "x", "linkedin"})

    def test_ensure_workspace_schedule_registers_a_daily_cron_once(self):
        conn = self.app.db_operator()
        try:
            ws = conn.execute("SELECT id FROM workspace ORDER BY id LIMIT 1").fetchone()[0]
            owned_analytics.ensure_workspace_schedule(conn.session, ws)
            owned_analytics.ensure_workspace_schedule(conn.session, ws)   # idempotent
            conn.commit()
            rows = conn.execute(
                "SELECT name, cron, once FROM scheduled_task "
                "WHERE kind = 'owned_analytics' AND name = ?",
                (f"owned-analytics:{ws}",)).fetchall()
        finally:
            conn.close()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][1], "20 3 * * *")
        self.assertIn(rows[0][2], (0, None))   # recurring, not a one-shot


if __name__ == "__main__":
    unittest.main()
