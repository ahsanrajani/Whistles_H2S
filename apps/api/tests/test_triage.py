import unittest

from ._db import DbTestCase
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core import triage

ROOT = Path(__file__).resolve().parents[1]


def _day(offset):
    return (datetime.now(timezone.utc) - timedelta(days=offset)).strftime("%Y-%m-%dT09:00:00Z")


class ScoreRowTests(unittest.TestCase):
    def test_text_and_context_weights_add_once_each(self):
        score, hits = triage.score_row(
            "Unauthorized transaction, money deducted. Complaining to the SBP and my lawyer.",
            category="fraud", rating=1, sentiment="neg")
        self.assertEqual(set(hits),
                         {"regulator", "legal", "financial_loss",
                          "fraud_type", "one_star", "negative"})
        self.assertEqual(score, 4 + 3 + 3 + 2 + 2 + 1)

    def test_clean_complaint_scores_zero(self):
        self.assertEqual(triage.score_row("App was slow this morning"), (0, []))

    def test_two_star_review_contributes_less_than_one_star(self):
        s1, _ = triage.score_row("bad", rating=1)
        s2, _ = triage.score_row("bad", rating=2)
        self.assertEqual((s1, s2), (2, 1))

    def test_bands_are_inclusive_lower_bounds(self):
        self.assertEqual(triage.band_of(0), "routine")
        self.assertEqual(triage.band_of(1), "watch")
        self.assertEqual(triage.band_of(3), "elevated")
        self.assertEqual(triage.band_of(5), "high")
        self.assertEqual(triage.band_of(8), "critical")


class ScanTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'Bank Alfalah','PK','now')")
        self.db.execute(
            "INSERT INTO brand(id,workspace_id,name,is_focus) VALUES (1,1,'Bank Alfalah',1)")
        self.db.execute(
            "INSERT INTO brand(id,workspace_id,name,is_focus) VALUES (2,1,'HBL',0)")
        self._iid = 0
        self._mid = 0


    def _mention(self, *, brand_id=1, body, category=None, sentiment=None, rating=None,
                 published=None, surface="x", excluded=0, hidden=0):
        self._iid += 1
        self._mid += 1
        self.db.execute(
            """INSERT INTO item(id,workspace_id,surface,source,source_kind,external_id,
                                url,published_at,body,rating,raw_json,collected_at,content_hash)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (self._iid, 1, surface, "x_recent", "licensed", f"e{self._iid}",
             f"https://x/{self._iid}", published or _day(1), body, rating, "{}", "now",
             f"h{self._iid}"))
        self.db.execute(
            "INSERT INTO mention(id,item_id,brand_id,rule,excluded,hidden) VALUES (?,?,?,?,?,?)",
            (self._mid, self._iid, brand_id, "x_search", excluded, hidden))
        if sentiment:
            self.db.execute(
                """INSERT INTO sentiment(mention_id,label,model_id,scored_lang,scored_at)
                   VALUES (?,?,?,?,?)""", (self._mid, sentiment, "lexicon", "en", "now"))
        if category:
            self.db.execute(
                """INSERT INTO mention_class(mention_id,category,model_id,classified_at)
                   VALUES (?,?,?,?)""", (self._mid, category, "rules", "now"))
        self.db.commit()
        return self._iid

    def test_ranks_by_score_and_excludes_non_complaints(self):
        self._mention(body="Great staff at Gulberg branch", sentiment="pos")  # not in corpus
        self._mention(body="app keeps crashing", sentiment="neg")             # in corpus, score 1
        self._mention(
            body="Account blocked for a week now, complaint number 8821, escalating to Banking Mohtasib",
            category="complaint", sentiment="neg")

        report = triage.scan(self.db, 1)

        self.assertEqual(report["summary"]["scanned"], 2)
        self.assertIn("regulator", report["queue"][0]["signals"])
        self.assertEqual(report["queue"][0]["band"], "critical")
        self.assertGreater(report["queue"][0]["score"], report["queue"][1]["score"])
        self.assertEqual(report["policy"]["max_score"], triage._MAX_SCORE)

    def test_one_row_per_item_prefers_the_focus_brand(self):
        iid = self._mention(body="unauthorized transaction, money deducted",
                            category="complaint", sentiment="neg", brand_id=1)
        # same story also matched to a competitor
        self._mid += 1
        self.db.execute(
            "INSERT INTO mention(id,item_id,brand_id,rule) VALUES (?,?,?,?)",
            (self._mid, iid, 2, "x_search"))
        self.db.commit()

        report = triage.scan(self.db, 1)
        self.assertEqual(report["summary"]["scanned"], 1)
        self.assertEqual(report["queue"][0]["brand"], "Bank Alfalah")
        self.assertTrue(report["queue"][0]["focus"])

    def test_hidden_and_excluded_mentions_are_skipped(self):
        self._mention(body="lawyer legal notice unauthorized transaction",
                      category="complaint", hidden=1)
        self._mention(body="lawyer legal notice unauthorized transaction",
                      category="complaint", excluded=1)
        report = triage.scan(self.db, 1)
        self.assertEqual(report["summary"]["scanned"], 0)

    def test_period_filter_excludes_old_rows(self):
        self._mention(body="account frozen, no response for weeks", category="complaint",
                      sentiment="neg", published=_day(2))
        self._mention(body="account frozen, no response for weeks", category="complaint",
                      sentiment="neg", published=_day(90))
        report = triage.scan(self.db, 1, days=7)
        self.assertEqual(report["summary"]["scanned"], 1)


if __name__ == "__main__":
    unittest.main()
