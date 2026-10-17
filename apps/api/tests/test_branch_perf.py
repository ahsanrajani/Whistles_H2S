import json
import unittest

from ._db import DbTestCase
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core import branch_perf

ROOT = Path(__file__).resolve().parents[1]


def _day(offset):
    return (datetime.now(timezone.utc) - timedelta(days=offset)).strftime("%Y-%m-%dT09:00:00Z")


class ScanTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.execute(
            "INSERT INTO brand(id,workspace_id,name,is_focus) VALUES (1,1,'Bank Alfalah',1)")
        self._iid = self._mid = 0


    def _item(self, *, surface, source, text, rating, offset, branch_key=None,
              sentiment=None, category=None):
        self._iid += 1
        self._mid += 1
        raw = {"branch_key": branch_key} if branch_key else {"kind": "comment"}
        self.db.execute(
            """INSERT INTO item(id,workspace_id,surface,source,source_kind,external_id,
                                url,outlet,published_at,body,rating,raw_json,collected_at,
                                content_hash)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (self._iid, 1, surface, source, "licensed", f"e{self._iid}",
             f"https://x/{self._iid}", "Google Maps" if surface == "branch_review" else "Facebook",
             _day(offset), text, rating, json.dumps(raw), "now", f"h{self._iid}"))
        self.db.execute(
            "INSERT INTO mention(id,item_id,brand_id,rule) VALUES (?,?,1,'branch_seed')",
            (self._mid, self._iid))
        if sentiment:
            self.db.execute(
                """INSERT INTO sentiment(mention_id,label,model_id,scored_lang,scored_at)
                   VALUES (?,?,?,?,?)""", (self._mid, sentiment, "seed", "en", "now"))
        if category:
            self.db.execute(
                """INSERT INTO mention_class(mention_id,category,model_id,classified_at)
                   VALUES (?,?,?,?)""", (self._mid, category, "seed", "now"))
        self.db.commit()

    def test_bad_branch_flags_with_its_top_issue(self):
        # a run of low ratings on the same branch, recent ones worse (falling delta)
        for i in range(6):
            self._item(surface="branch_review", source="google_maps_reviews",
                       text="ATM out of cash yet again. Unauthorized transaction on my "
                            "account and the money was not reversed.",
                       rating=1, offset=5 + i, branch_key="sargodha",
                       sentiment="neg", category="complaint")
        for i in range(4):
            self._item(surface="branch_review", source="google_maps_reviews",
                       text="decent branch, staff were fine", rating=4, offset=80 + i,
                       branch_key="sargodha", sentiment="pos")
        # a Facebook comment that names the branch by area
        self._item(surface="facebook", source="brightdata_facebook_comments",
                   text="the ATM at your Main Sargodha branch has been out of order all week",
                   rating=None, offset=3, sentiment="neg", category="complaint")
        # a healthy branch
        for i in range(5):
            self._item(surface="branch_review", source="google_maps_reviews",
                       text="quick service, polite staff, no issues", rating=5,
                       offset=10 + i, branch_key="f8-markaz-isb", sentiment="pos")

        report = branch_perf.scan(self.db, 1)
        by_key = {b["key"]: b for b in report["branches"]}

        sgd = by_key["sargodha"]
        self.assertEqual(sgd["band"], "high")
        self.assertEqual(sgd["top_issue"], "atm_cash")
        self.assertGreaterEqual(sgd["complaints"], 6)
        self.assertGreaterEqual(sgd["critical"], 1)
        self.assertLess(sgd["mean_rating"], 3)
        self.assertIsNotNone(sgd["rating_delta"])
        self.assertLess(sgd["rating_delta"], 0)
        self.assertEqual(sgd["social"], 1)

        f8 = by_key["f8-markaz-isb"]
        self.assertEqual(f8["band"], "none")
        self.assertEqual(f8["issues"], [])

        self.assertEqual(report["branches"][0]["key"], "sargodha")   # worst first
        self.assertEqual(report["coverage"]["reviews"], 15)
        self.assertEqual(report["coverage"]["social_matched"], 1)
        self.assertGreaterEqual(report["summary"]["branches_flagged"], 1)

    def test_unresolved_social_is_counted_not_dropped(self):
        self._item(surface="facebook", source="brightdata_facebook_comments",
                   text="Bank Alfalah app keeps crashing, terrible", rating=None,
                   offset=2, sentiment="neg", category="complaint")
        report = branch_perf.scan(self.db, 1)
        self.assertEqual(report["coverage"]["social_matched"], 0)
        self.assertEqual(report["coverage"]["unresolved_social"], 1)

    def test_no_focus_brand_returns_shape(self):
        self.db.execute("UPDATE brand SET is_focus=0 WHERE id=1")
        self.db.commit()
        report = branch_perf.scan(self.db, 1)
        self.assertEqual(report["branches"], [])
        self.assertIn("issues", report["policy"])
        self.assertEqual(report["coverage"]["focus_brand"], None)


if __name__ == "__main__":
    unittest.main()


class BranchItemsTests(ScanTests):
    def test_items_page_and_issue_filter_match_card_counts(self):
        from core import branch_items
        for i in range(3):
            self._item(surface="branch_review", source="google_maps_reviews",
                       text="ATM out of cash again", rating=1, offset=2 + i,
                       branch_key="sargodha", sentiment="neg", category="complaint")
        self._item(surface="branch_review", source="google_maps_reviews",
                   text="lovely branch", rating=5, offset=1, branch_key="sargodha",
                   sentiment="pos")
        self._item(surface="facebook", source="brightdata_facebook_comments",
                   text="ATM out of cash at your Main Sargodha branch all week",
                   rating=None, offset=6, sentiment="neg", category="complaint")

        page = branch_items.items(self.db, 1, "sargodha", limit=2)
        self.assertEqual(page["total"], 5)
        self.assertEqual(len(page["items"]), 2)
        self.assertEqual(page["items"][0]["text"], "lovely branch")    # newest first

        card = {b["key"]: b for b in branch_perf.scan(self.db, 1)["branches"]}["sargodha"]
        n = next(i["n"] for i in card["issues"] if i["key"] == "atm_cash")
        themed = branch_items.items(self.db, 1, "sargodha", issue="atm_cash", limit=100)
        self.assertEqual(themed["total"], n)
        self.assertIn("facebook", {r["surface"] for r in themed["items"]})

    def test_unknown_branch_returns_empty_shape(self):
        from core import branch_items
        page = branch_items.items(self.db, 1, "no-such-branch")
        self.assertIsNone(page["branch"])
        self.assertEqual(page["items"], [])
