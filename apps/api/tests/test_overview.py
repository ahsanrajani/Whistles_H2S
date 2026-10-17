import unittest

from ._db import DbTestCase
from pathlib import Path

from core import insights

ROOT = Path(__file__).resolve().parents[1]


class DayBucketTests(unittest.TestCase):
    def test_parses_rfc822_and_iso_and_rejects_junk(self):
        self.assertEqual(insights._day_bucket("Fri, 01 Aug 2025 07:00:00 GMT"), "2025-08-01")
        self.assertEqual(insights._day_bucket("2015-03-07T22:51:38Z"), "2015-03-07")
        self.assertIsNone(insights._day_bucket("nonsense"))
        self.assertIsNone(insights._day_bucket(None))


class OverviewTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'Bank Alfalah','PK','now')")
        self.db.execute(
            """INSERT INTO brand(id,workspace_id,name,is_focus,safe_patterns)
               VALUES (1,1,'Bank Alfalah',1,'[\"\\\\bbank\\\\s*alfalah\\\\b\"]')""")
        self.db.execute(
            "INSERT INTO brand(id,workspace_id,name,is_focus) VALUES (2,1,'Meezan Bank',0)")
        rows = (
            (1, "googlenews_rss", "Fri, 01 Aug 2025 07:00:00 GMT",
             "Bank Alfalah car leasing scheme for used vehicles explained"),
            (2, "googlenews_rss", "Sat, 02 Aug 2025 07:00:00 GMT",
             "Bank Alfalah adds a cash deposit machine at every branch"),
            (3, "googlenews_rss", "Sat, 02 Aug 2025 09:00:00 GMT",
             "Used car leasing rates compared across banks"),
        )
        for iid, source, pub, body in rows:
            self.db.execute(
                """INSERT INTO item(id,workspace_id,surface,source,source_kind,external_id,
                   url,outlet,author,published_at,title,body,lang_guess,raw_json,collected_at,content_hash)
                   VALUES (?,1,'news',?,'public',?,?,?,?,?,?,?,'en','{}','now',?)""",
                (iid, source, str(iid), f"https://s/{iid}", "Dawn", "A. Writer",
                 pub, body, body, str(iid)))
            self.db.execute(
                "INSERT INTO mention(id,item_id,brand_id,rule) VALUES (?,?,1,'exact_name')",
                (iid, iid))
        self.db.commit()


    def test_press_volume_buckets_rfc822_dates(self):
        # Window is wide enough that the fixed Aug-2025 fixture dates stay
        # inside it regardless of the calendar date the suite runs on — a
        # narrower window silently drops the fixtures once enough real time
        # passes and the assertions below go to zero.
        window = 3000
        trend = insights.press_volume(self.db, 1, days=window)
        self.assertEqual(trend["raw_peak"], 2)      # two items dated 02 Aug (raw daily)
        self.assertGreater(trend["peak"], 0)        # smoothed peak is the plotted scale
        self.assertLessEqual(trend["peak"], 2)
        self.assertEqual(trend["peak_day"], "2025-08-02")
        focus = next(s for s in trend["series"] if s["focus"])
        self.assertEqual(focus["total"], 3)         # all three fixture mentions
        self.assertTrue(focus["points"])
        self.assertEqual(len(focus["smooth"]), window)

    def test_themes_drop_brand_and_stopwords_and_lean_negative(self):
        terms = {t["term"]: t for t in insights.themes(self.db, 1, 1, min_count=2)}
        self.assertNotIn("bank", terms)
        self.assertNotIn("alfalah", terms)
        self.assertIn("car leasing", terms)
        self.assertEqual(terms["car leasing"]["lean"], "unscored")

        self.db.execute(
            """INSERT INTO sentiment(mention_id,label,model_id,scored_lang,scored_at)
               VALUES (1,'neg','m','en','now')""")
        self.db.commit()
        rescored = {t["term"]: t
                    for t in insights.themes(self.db, 1, 1, min_count=2)}["car leasing"]
        self.assertEqual(rescored["lean"], "negative")

    def test_headline_and_cards_hide_operator_content_from_viewer(self):
        sov = insights.share_of_voice(self.db, 1)
        gaps, _r, _t = insights.outlet_gap(self.db, 1, "Bank Alfalah")
        langs = insights.language_mix(self.db, 1)
        senti = insights.sentiment_breakdown(self.db, 1)
        outlets = insights.top_outlets(self.db, 1)

        viewer = insights.headline(self.db, 1, sov, gaps, [], "bank_viewer", senti, outlets)
        self.assertNotIn("coverage", [h["kind"] for h in viewer])

        cards = insights.action_cards(self.db, 1, sov, gaps, [], langs, senti, "bank_viewer")
        for c in cards:
            if c["action"]:
                self.assertFalse(c["action"]["href"].startswith(("/admin", "/review")))


class DeltaAndDedupeTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute("INSERT INTO workspace(id,name,market,created_at) VALUES (1,'W','PK','now')")
        self.db.execute("INSERT INTO brand(id,workspace_id,name,is_focus) VALUES (1,1,'Focus',1)")


    def _item(self, iid, days_ago, dup_of=None):
        from datetime import datetime, timedelta, timezone
        pub = (datetime.now(timezone.utc).date() - timedelta(days=days_ago)).isoformat()
        self.db.execute(
            """INSERT INTO item(id,workspace_id,surface,source,source_kind,external_id,url,
               outlet,published_at,body,lang_guess,raw_json,collected_at,content_hash)
               VALUES (?,1,'news','googlenews_rss','public',?,?,?,?,?,'en','{}','now',?)""",
            (iid, str(iid), f"https://s/{iid}", "Dawn", pub, f"news item {iid}", str(iid)))
        self.db.execute("INSERT INTO mention(id,item_id,brand_id,rule) VALUES (?,?,1,'exact_name')",
                        (iid, iid))
        if dup_of:
            self.db.execute(
                "INSERT INTO dupe_edge(item_id,canonical_id,method) VALUES (?,?,'content_hash')",
                (iid, dup_of))
        self.db.commit()

    def test_period_split_buckets_by_age(self):
        cur = [("2000-01-01",)]                       # far in the past -> neither window
        self.assertEqual(insights._split_window([("nonsense",)] + cur, 30), (0, 0, 0, 0))

    def test_delta_pct_none_under_sample_guard(self):
        for i in range(3):
            self._item(10 + i, days_ago=5)
        d = insights.deltas(self.db, 1, 30)
        self.assertEqual(d["positive"]["pct"], None)   # no sentiment at all
        self.assertEqual(d["rating"]["pct"], None)     # no reviews

    def test_folded_duplicate_is_absent_from_feed(self):
        self._item(1, days_ago=2)
        self._item(2, days_ago=1, dup_of=1)            # folded
        rows = insights.feed(self.db, 1)
        self.assertEqual([r[11] for r in rows], [1])   # mention id 2's item is a dupe

    def test_norm_title_folds_a_recollected_story(self):
        from core import collector
        for iid, ext in ((10, "g-a"), (11, "g-b"), (12, "g-c")):
            title = ("Bank Alfalah posts record profit" if iid < 12
                     else "A different headline entirely")
            self.db.execute(
                """INSERT INTO item(id,workspace_id,surface,source,source_kind,external_id,
                   url,outlet,published_at,title,body,lang_guess,raw_json,collected_at,content_hash)
                   VALUES (?,1,'news','googlenews_rss','public',?,?,?,?,?,?,'en','{}','now',?)""",
                (iid, ext, f"https://s/{ext}", "Dawn", "2026-08-30", title,
                 f"body {iid}", f"h{iid}"))
        self.db.commit()
        collector.dedupe(self.db, 1, lambda _m: None)
        folded = self.db.execute(
            "SELECT item_id, canonical_id FROM dupe_edge WHERE method='norm_title'").fetchall()
        self.assertEqual(folded, [(11, 10)])           # 12 has its own title, not folded


if __name__ == "__main__":
    unittest.main()
