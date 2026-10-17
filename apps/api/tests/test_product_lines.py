import unittest

from ._db import DbTestCase
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core import product_lines as pl

ROOT = Path(__file__).resolve().parents[1]


def _day(offset):
    return (datetime.now(timezone.utc) - timedelta(days=offset)).strftime("%Y-%m-%dT09:00:00Z")


class ClassifyTextTests(unittest.TestCase):
    def test_multi_line_tagging(self):
        keys = pl.classify_text("my credit card was declined on the banking app")
        self.assertEqual(set(keys), {"cards", "app"})

    def test_star_suffix_matches_inflections(self):
        self.assertIn("auto", pl.classify_text("applied for car financing last week"))
        self.assertIn("remittance", pl.classify_text("the remittances took three days"))

    def test_word_boundaries(self):
        # "cards" without a real keyword shouldn't tag; "discard" must not hit "card"
        self.assertEqual(pl.classify_text("please discard this message"), [])

    def test_unmatched_text_is_empty(self):
        self.assertEqual(pl.classify_text("the staff were polite and helpful"), [])


class ScanTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.execute(
            "INSERT INTO brand(id,workspace_id,name,is_focus) VALUES (1,1,'Focus Bank',1)")
        self.db.execute(
            "INSERT INTO brand(id,workspace_id,name,is_focus) VALUES (2,1,'Rival',0)")
        self._iid = self._mid = 0


    def _mention(self, body, *, brand_id=1, sentiment=None, published=None):
        self._iid += 1
        self._mid += 1
        self.db.execute(
            """INSERT INTO item(id,workspace_id,surface,source,source_kind,external_id,
                                url,outlet,published_at,body,raw_json,collected_at,content_hash)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (self._iid, 1, "x", "x_recent", "licensed", f"e{self._iid}",
             f"https://x/{self._iid}", "Wire", published or _day(1), body, "{}", "now",
             f"h{self._iid}"))
        self.db.execute(
            "INSERT INTO mention(id,item_id,brand_id,rule) VALUES (?,?,?,?)",
            (self._mid, self._iid, brand_id, "x_search"))
        if sentiment:
            self.db.execute(
                """INSERT INTO sentiment(mention_id,label,model_id,scored_lang,scored_at)
                   VALUES (?,?,?,?,?)""", (self._mid, sentiment, "lexicon", "en", "now"))
        self.db.commit()

    def test_share_counts_sentiment_and_other(self):
        self._mention("credit card declined again", sentiment="neg")
        self._mention("annual fee on my visa is too high", sentiment="neg")
        self._mention("love the banking app update", sentiment="pos")
        self._mention("branch staff were friendly")            # unclassified... "branch" IS a keyword
        self._mention("nothing specific to report here")       # truly unclassified
        self._mention("card declined on the banking app", sentiment="neu")  # multi-line

        report = pl.scan(self.db, 1)
        lines = {line["key"]: line for line in report["lines"]}

        self.assertEqual(report["coverage"]["total"], 6)
        self.assertEqual(report["coverage"]["multi_line"], 1)
        self.assertEqual(report["other"]["n"], 1)
        self.assertEqual(lines["cards"]["n"], 3)
        self.assertEqual(lines["cards"]["neg"], 2)
        self.assertEqual(lines["app"]["n"], 2)
        # share is of the tag total (cards 3 + app 2 + branch 1 = 6)
        self.assertEqual(lines["cards"]["share"], round(100 * 3 / 6, 1))
        self.assertIsNotNone(lines["cards"]["neg_lo"])
        self.assertEqual(report["lines"][0]["key"], "cards")     # sorted by n desc

    def test_only_focus_brand(self):
        self._mention("credit card issue", brand_id=2)
        report = pl.scan(self.db, 1)
        self.assertEqual(report["coverage"]["total"], 0)

    def test_period_filter(self):
        self._mention("credit card declined", published=_day(2))
        self._mention("credit card declined", published=_day(60))
        report = pl.scan(self.db, 1, days=7)
        self.assertEqual(report["coverage"]["total"], 1)

    def test_no_focus_brand_returns_shape(self):
        self.db.execute("UPDATE brand SET is_focus=0 WHERE id=1")
        self.db.commit()
        report = pl.scan(self.db, 1)
        self.assertEqual(report["coverage"]["total"], 0)
        self.assertEqual(len(report["lines"]), len(pl.PRODUCT_LINES))
        self.assertIn("lines", report["policy"])


if __name__ == "__main__":
    unittest.main()
