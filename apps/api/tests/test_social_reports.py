"""P4.5 — social reports over the owned-analytics warehouse."""
import unittest
from datetime import date

from core import social_reports
from db import repositories as repo

from ._db import ApiTestCase, DbTestCase

D0, D1 = date(2026, 6, 10), date(2026, 6, 12)


def _f(day, etype, eref, metric, value, *, num=None, den=None, mt=None):
    return {"source": "meta", "entity_type": etype, "entity_ref": eref,
            "metric": metric, "day": day, "value": value,
            "numerator": num, "denominator": den,
            "dims": {"media_type": mt} if mt else {}}


class SocialReportTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.commit()
        self.s = self.db.session
        facts = []
        for d in (10, 11, 12):
            day = date(2026, 6, d)
            facts += [
                _f(day, "page", "self", "impressions", 1000.0),
                _f(day, "page", "self", "followers", 50_000.0),
                _f(day, "page", "self", "engagement_rate", 0.05, num=50.0, den=1000.0),
                _f(day, "post", "vid-1", "impressions", 800.0, mt="video"),
                _f(day, "post", "vid-1", "engagements", 120.0, mt="video"),
                _f(day, "post", "vid-1", "engagement_rate", 0.15, num=120.0, den=800.0, mt="video"),
                _f(day, "post", "img-1", "impressions", 400.0, mt="image"),
                _f(day, "post", "img-1", "engagement_rate", 0.05, num=20.0, den=400.0, mt="image"),
                _f(day, "post", "reel-1", "impressions", 600.0, mt="reel"),
                _f(day, "post", "reel-1", "engagement_rate", 0.20, num=120.0, den=600.0, mt="reel"),
            ]
        # a prior window so the account comparison has something to diff
        for d in (7, 8, 9):
            facts.append(_f(date(2026, 6, d), "page", "self", "impressions", 500.0))
        repo.metric_fact.upsert_many(self.s, 1, facts)
        self.db.commit()

    def _report(self):
        return social_reports.report(self.s, 1, source="meta", start=D0, end=D1)

    def test_account_summary_has_measures_and_deltas(self):
        acct = self._report()["account"]
        self.assertEqual(acct["impressions"]["measure"]["value"], 3000.0)
        self.assertEqual(acct["impressions"]["comparison"]["previous"], 1500.0)
        self.assertIn("wilson", acct["engagement_rate"]["measure"])

    def test_post_scorecard_is_reach_ranked(self):
        posts = self._report()["posts"]
        self.assertEqual([p["post"] for p in posts], ["vid-1", "reel-1", "img-1"])
        self.assertEqual(posts[0]["impressions"], 2400.0)
        self.assertIn("wilson", posts[0]["engagement_rate"])

    def test_video_and_reels_are_filtered_by_media_type(self):
        r = self._report()
        self.assertEqual([p["post"] for p in r["video"]], ["vid-1"])
        self.assertEqual([p["post"] for p in r["reels"]], ["reel-1"])

    def test_engagement_by_media_type_is_wilson_scored_per_group(self):
        groups = {g["media_type"]: g for g in
                  self._report()["engagement_by_media_type"]}
        self.assertEqual(set(groups), {"video", "image", "reel"})
        for g in groups.values():
            self.assertIn("wilson", g)
        self.assertGreater(groups["reel"]["value"], groups["image"]["value"])


class SocialReportApiTests(ApiTestCase):
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
                _f(date(2026, 6, 11), "post", "p1", "impressions", 10.0, mt="video"),
            ])
            conn.commit()
        finally:
            conn.close()

    def test_social_report_endpoint(self):
        r = self.client.get("/api/v1/reports/social"
                            "?source=meta&start=2026-06-01&end=2026-06-30")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["source"], "meta")
        self.assertTrue(any(p["post"] == "p1" for p in body["video"]))
        self.assertEqual(self.client.get("/api/v1/reports/social").status_code, 422)


if __name__ == "__main__":
    unittest.main()
