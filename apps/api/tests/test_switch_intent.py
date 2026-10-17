import unittest

from ._db import DbTestCase
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core import switch_intent as si

ROOT = Path(__file__).resolve().parents[1]


def _day(offset):
    return (datetime.now(timezone.utc) - timedelta(days=offset)).strftime("%Y-%m-%dT09:00:00Z")


class ScoreRowTests(unittest.TestCase):
    def test_closure_plus_context_weights(self):
        score, hits = si.score_row(
            "Closing my account after this. Worst bank, switching banks tomorrow.",
            category="complaint", sentiment="neg")
        self.assertEqual(set(hits),
                         {"closure", "switch_verb", "complaint_type", "negative"})
        self.assertEqual(score, 4 + 3 + 1 + 1)

    def test_clean_mention_scores_zero(self):
        self.assertEqual(si.score_row("The new app update looks nice"), (0, []))

    def test_rival_pattern_needs_a_move_verb_near_the_name(self):
        rx = si.competitor_pattern(["Meezan Bank", "HBL"])
        self.assertIsNotNone(rx)
        hit, keys = si.score_row("thinking of moving my account to Meezan Bank", rival_rx=rx)
        self.assertIn("to_competitor", keys)
        # rival named with no move verb nearby -> no signal
        _score, keys2 = si.score_row("Meezan Bank has a nice building downtown", rival_rx=rx)
        self.assertNotIn("to_competitor", keys2)

    def test_competitor_pattern_none_without_rivals(self):
        self.assertIsNone(si.competitor_pattern([]))

    def test_bands(self):
        self.assertEqual(si.band_of(0), "none")
        self.assertEqual(si.band_of(2), "watch")
        self.assertEqual(si.band_of(4), "likely")
        self.assertEqual(si.band_of(7), "high")


class ScanTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'Bank Alfalah','PK','now')")
        self.db.execute(
            "INSERT INTO brand(id,workspace_id,name,is_focus) VALUES (1,1,'Bank Alfalah',1)")
        self.db.execute(
            "INSERT INTO brand(id,workspace_id,name,is_focus) VALUES (2,1,'Meezan Bank',0)")
        self._iid = self._mid = 0


    def _mention(self, *, brand_id=1, body, category=None, sentiment=None,
                 published=None, hidden=0, excluded=0):
        self._iid += 1
        self._mid += 1
        self.db.execute(
            """INSERT INTO item(id,workspace_id,surface,source,source_kind,external_id,
                                url,published_at,body,raw_json,collected_at,content_hash)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (self._iid, 1, "x", "x_recent", "licensed", f"e{self._iid}",
             f"https://x/{self._iid}", published or _day(1), body, "{}", "now",
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

    def test_only_focus_brand_and_ranking(self):
        self._mention(body="Bank Alfalah app is great")                       # scanned, score 0
        self._mention(body="switching banks, done with this bank", sentiment="neg")
        self._mention(body="closing my account and moving my salary to Meezan Bank",
                      category="complaint", sentiment="neg")
        self._mention(brand_id=2, body="closing my account, switching banks now")  # competitor, ignored

        report = si.scan(self.db, 1)

        self.assertEqual(report["summary"]["scanned"], 3)
        self.assertEqual(report["coverage"]["competitors"], ["Meezan Bank"])
        top = report["queue"][0]
        self.assertTrue(top["competitor_named"])
        self.assertEqual(top["band"], "high")
        self.assertGreater(top["score"], report["queue"][1]["score"])
        self.assertEqual(report["policy"]["max_score"], si._MAX_SCORE)

    def test_flag_threshold_is_two(self):
        self._mention(body="not recommend this bank")  # warn_others = 2 -> flagged (watch)
        self._mention(body="the queue was long today", sentiment="neg")  # negative = 1 -> not flagged
        report = si.scan(self.db, 1)
        self.assertEqual(report["summary"]["scanned"], 2)
        self.assertEqual(report["summary"]["flagged"], 1)
        self.assertEqual(report["queue"][0]["band"], "watch")

    def test_no_focus_brand_returns_empty_shape(self):
        self.db.execute("UPDATE brand SET is_focus=0 WHERE id=1")
        self.db.commit()
        report = si.scan(self.db, 1)
        self.assertEqual(report["summary"]["scanned"], 0)
        self.assertEqual(report["queue"], [])
        self.assertIn("signals", report)
        self.assertEqual(report["policy"]["max_score"], si._MAX_SCORE)

    def test_period_filter(self):
        self._mention(body="switching banks", published=_day(2))
        self._mention(body="switching banks", published=_day(40))
        report = si.scan(self.db, 1, days=7)
        self.assertEqual(report["summary"]["scanned"], 1)


if __name__ == "__main__":
    unittest.main()
