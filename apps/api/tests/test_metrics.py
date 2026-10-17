"""P4.2 — the metric layer over the metric_fact warehouse."""
import unittest
from datetime import date

from core import metrics
from db import repositories as repo

from ._db import ApiTestCase, DbTestCase


def _fact(day, metric, value, *, num=None, den=None, dims=None, eref="self",
          etype="page"):
    return {"source": "meta", "entity_type": etype, "entity_ref": eref,
            "metric": metric, "day": day, "value": value,
            "numerator": num, "denominator": den, "dims": dims or {}}


class MetricLayerTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.commit()
        self.s = self.db.session
        facts = []
        # current window 2026-06-10 .. 2026-06-12, previous 06-07 .. 06-09
        for d in (7, 8, 9, 10, 11, 12):
            day = date(2026, 6, d)
            facts.append(_fact(day, "impressions", 100.0 + d))
            facts.append(_fact(day, "engagement_rate", None, num=5.0 + d, den=100.0 + d,
                               etype="page"))
            for mt, v in (("video", 30.0), ("image", 12.0)):
                facts.append(_fact(day, "post_impressions", v, dims={"media_type": mt},
                                   etype="post", eref=f"{day}-{mt}"))
        repo.metric_fact.upsert_many(self.s, 1, facts)
        self.db.commit()

    def _report(self, **kw):
        base = dict(source="meta", start=date(2026, 6, 10), end=date(2026, 6, 12))
        base.update(kw)
        return metrics.report(self.s, 1, **base)

    def test_count_measure_rolls_up_as_a_sum(self):
        r = self._report(metric="impressions")
        self.assertEqual(r["measure"]["kind"], "count")
        self.assertEqual(r["measure"]["value"], 110 + 111 + 112)
        self.assertEqual(len(r["series"]), 3)

    def test_proportion_measure_is_wilson_scored(self):
        r = self._report(metric="engagement_rate")
        m = r["measure"]
        self.assertEqual(m["kind"], "proportion")
        self.assertAlmostEqual(m["value"], m["numerator"] / m["denominator"], places=9)
        lo, hi = m["wilson"]
        self.assertLessEqual(lo, m["value"])
        self.assertGreaterEqual(hi, m["value"])

    def test_period_comparison_uses_the_preceding_equal_window(self):
        r = self._report(metric="impressions")
        c = r["comparison"]
        self.assertEqual(c["window"], {"start": "2026-06-07", "end": "2026-06-09",
                                       "days": 3})
        self.assertEqual(c["previous"], 107 + 108 + 109)
        self.assertAlmostEqual(c["absolute"], (110 + 111 + 112) - (107 + 108 + 109))

    def test_group_by_a_dims_key(self):
        r = self._report(metric="post_impressions", entity_type="post",
                         group_by="media_type")
        keys = {g["key"]: g["value"] for g in r["groups"]}
        self.assertEqual(keys["video"], 90.0)   # 30 * 3 days
        self.assertEqual(keys["image"], 36.0)

    def test_empty_window_yields_null_not_zero(self):
        r = self._report(metric="impressions", start=date(2026, 1, 1),
                         end=date(2026, 1, 3))
        self.assertIsNone(r["measure"]["value"])

    def test_unknown_group_by_is_a_400(self):
        with self.assertRaises(metrics.MetricError):
            self._report(metric="impressions", group_by="nonsense")

    def test_catalog_lists_metrics_and_flags_proportions(self):
        cat = metrics.catalog(self.s, 1)
        by = {(m["source"], m["metric"]): m for m in cat["metrics"]}
        self.assertFalse(by[("meta", "impressions")]["is_proportion"])
        self.assertTrue(by[("meta", "engagement_rate")]["is_proportion"])
        self.assertIn("media_type", by[("meta", "post_impressions")]["dims"])
        self.assertIn("media_type", cat["groupable"])


class MetricApiTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        token = self.client.get("/api/v1/csrf").get_json()["token"]
        self.client.post("/api/v1/auth/login",
                         json={"username": "admin", "password": "admin123"},
                         headers={"X-CSRF-Token": token})
        conn = self.app.db_operator()
        try:
            ws = conn.execute("SELECT id FROM workspace ORDER BY id LIMIT 1").fetchone()[0]
            repo.metric_fact.upsert_many(conn.session, ws, [
                _fact(date(2026, 6, 11), "impressions", 500.0),
                _fact(date(2026, 6, 12), "impressions", 600.0),
            ])
            conn.commit()
        finally:
            conn.close()

    def test_metrics_query_and_catalog(self):
        r = self.client.get("/api/v1/reports/metrics"
                            "?source=meta&metric=impressions"
                            "&start=2026-06-10&end=2026-06-12&compare=false")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["measure"]["value"], 1100.0)

        cat = self.client.get("/api/v1/reports/metrics/catalog").get_json()
        self.assertTrue(any(m["metric"] == "impressions" for m in cat["metrics"]))

    def test_bad_dates_are_rejected(self):
        r = self.client.get("/api/v1/reports/metrics"
                            "?source=meta&metric=impressions&start=nope&end=2026-06-12")
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
