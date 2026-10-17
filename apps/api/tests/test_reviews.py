import json
import unittest

from ._db import DbTestCase
from pathlib import Path
from unittest.mock import patch

from core import collector, insights, review_store
from core.review_store import refresh as refresh_store_stats, review_context
from db.analytics import kpis as kpi_queries, reviews as review_queries
from db.repositories import metric_fact as mf_repo

ROOT = Path(__file__).resolve().parents[1]

FEED = json.dumps({"feed": {"entry": [
    {"im:name": {"label": "Bank Alfalah"}},                 # app metadata, skipped
    {"id": {"label": "111"}, "im:rating": {"label": "1"},
     "title": {"label": "Broken"}, "content": {"label": "App will not open"},
     "author": {"name": {"label": "Ali"}},
     "updated": {"label": "2026-08-20T10:00:00-07:00"},
     "im:version": {"label": "9.1"}},
    {"id": {"label": "222"}, "im:rating": {"label": "5"},
     "title": {"label": "Great"}, "content": {"label": "Fast transfers"},
     "author": {"name": {"label": "Sana"}},
     "updated": {"label": "2026-08-19T09:00:00-07:00"},
     "im:version": {"label": "9.1"}},
]}})


class AppStoreAdapterTests(unittest.TestCase):
    def test_fetch_skips_metadata_and_parses_rating(self):
        calls = []
        a = collector.AppStoreReviews(
            {"APPSTORE_APP_ID": "555", "APPSTORE_COUNTRY": "pk"},
            lambda _m: None, lambda *x, **k: calls.append(x))
        # page 1 has reviews, pages 2-10 don't -- an empty page must not stop
        # the loop early (Apple's RSS pages aren't reliably contiguous).
        with patch("integrations.adapters.app_meta.appstore", return_value={}),              patch("core.collector._get",
                   side_effect=[FEED.encode()] + [b'{"feed": {}}'] * 9):
            rows = list(a.fetch([]))
        self.assertEqual(len(rows), 2)
        self.assertEqual({r["rating"] for r in rows}, {1, 5})
        self.assertEqual(rows[0]["outlet"], "App Store")
        self.assertTrue(rows[0]["external_id"].startswith("as:"))


class MultiAppTests(unittest.TestCase):
    def test_parse_ids(self):
        from integrations.adapters import app_meta
        self.assertEqual(app_meta.parse_ids("a.b, c.d  a.b;e"), ["a.b", "c.d", "e"])
        self.assertEqual(app_meta.parse_ids(None), [])

    def test_each_app_is_fetched_and_tagged(self):
        a = collector.AppStoreReviews(
            {"APPSTORE_APP_ID": "555 666", "APPSTORE_COUNTRY": "pk"},
            lambda _m: None, lambda *x, **k: None)
        with patch("integrations.adapters.app_meta.appstore",
                   side_effect=lambda i, cc: {"name": f"App {i}", "icon": f"https://x/{i}.png"}),              patch("core.collector._get", side_effect=([FEED.encode()] + [b'{"feed": {}}'] * 9) * 2):
            rows = list(a.fetch([]))
        self.assertEqual(len(rows), 4)
        self.assertEqual({r["raw"]["app_id"] for r in rows}, {"555", "666"})
        self.assertEqual({r["raw"]["app_icon"] for r in rows},
                         {"https://x/555.png", "https://x/666.png"})

    def test_failed_meta_lookup_still_collects_without_icon(self):
        a = collector.AppStoreReviews({"APPSTORE_APP_ID": "555"},
                                      lambda _m: None, lambda *x, **k: None)
        with patch("integrations.adapters.app_meta.appstore", return_value={}),              patch("core.collector._get", side_effect=[FEED.encode()] + [b'{"feed": {}}'] * 9):
            rows = list(a.fetch([]))
        self.assertEqual(len(rows), 2)
        self.assertIsNone(rows[0]["raw"]["app_icon"])

    def test_insight_app_field_rejects_non_https_icons(self):
        app = insights.reviews._app(json.dumps(
            {"app_id": "x", "app_name": "X", "app_icon": "javascript:alert(1)"}))
        self.assertIsNone(app["icon"])
        self.assertIsNone(insights.reviews._app("{}"))


class ReviewInsightTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'Bank Alfalah','PK','now')")
        self.db.execute(
            "INSERT INTO brand(id,workspace_id,name,is_focus) VALUES (1,1,'Bank Alfalah',1)")
        for iid, rating in ((1, 5), (2, 4), (3, 1), (4, 5), (5, 2)):
            self.db.execute(
                """INSERT INTO item(id,workspace_id,surface,source,source_kind,external_id,
                   url,outlet,published_at,body,rating,raw_json,collected_at,content_hash)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (iid, 1, "app_reviews", "appstore_reviews", "public", f"as:{iid}",
                 f"https://apps/{iid}", "App Store", f"2026-08-2{iid}",
                 f"review {iid}", rating, "{}", "now", str(iid)))
            self.db.execute(
                "INSERT INTO mention(id,item_id,brand_id,rule) VALUES (?,?,1,'app_review')",
                (iid, iid))
        self.db.commit()


    def test_histogram_average_and_wilson_band(self):
        r = insights.app_reviews(self.db, 1)
        self.assertEqual(r["overall_n"], 5)
        self.assertEqual(r["dist"], [1, 1, 0, 1, 2])       # 1..5 stars
        self.assertAlmostEqual(r["overall_avg"], 3.4)
        self.assertEqual(r["stores"][0]["store"], "App Store")
        self.assertLess(r["good_lo"], r["good_share"])
        self.assertGreater(r["good_hi"], r["good_share"])

    def test_reviews_feed_the_app_rating_kpi(self):
        sov = insights.share_of_voice(self.db, 1)
        senti = insights.sentiment_breakdown(self.db, 1)
        tiles = insights.kpis(self.db, 1, sov, senti,
                              reviews=insights.app_reviews(self.db, 1))
        rating = next((t for t in tiles if t["key"] == "rating"), None)
        self.assertIsNotNone(rating)
        self.assertIn("3.4", rating["value"])

    def test_sample_excludes_competitors_other_surfaces_and_hidden_records(self):
        self.db.execute("INSERT INTO brand(id,workspace_id,name,is_focus) VALUES (2,1,'Other bank',0)")
        self.db.execute("UPDATE mention SET brand_id=2 WHERE item_id=2")
        self.db.execute("UPDATE item SET surface='branch_reviews' WHERE id=3")
        self.db.execute("UPDATE mention SET hidden=1 WHERE item_id=4")
        self.db.execute("UPDATE item SET source_kind='private' WHERE id=5")
        result = insights.app_reviews(self.db, 1)
        self.assertEqual(result["overall_n"], 1)
        self.assertEqual(result["overall_avg"], 5)
        self.assertEqual(review_queries.rating_rows(self.db.session, 1),
                         kpi_queries.rating_dates(self.db.session, 1))
        self.assertEqual(len(review_queries.rating_rows(self.db.session, 1)), 1)

    def test_each_review_counts_once_and_known_duplicates_are_excluded(self):
        self.db.execute("INSERT INTO brand(id,workspace_id,name,is_focus) VALUES (2,1,'Other bank',0)")
        self.db.execute("INSERT INTO mention(id,item_id,brand_id,rule) VALUES (6,1,2,'test')")
        self.db.execute("INSERT INTO dupe_edge(item_id,canonical_id,method) VALUES (4,1,'test')")
        result = insights.app_reviews(self.db, 1)
        self.assertEqual(result["overall_n"], 4)
        self.assertEqual(result["overall_avg"], 3)

    def test_item_workspace_must_match_brand_workspace(self):
        self.db.execute("INSERT INTO workspace(id,name,market,created_at) VALUES (2,'Other','PK','now')")
        self.db.execute("UPDATE item SET workspace_id=2 WHERE id=5")
        self.assertEqual(insights.app_reviews(self.db, 1)["overall_n"], 4)
        self.assertIsNone(insights.app_reviews(self.db, 2))

    def test_store_stats_are_null_until_refreshed(self):
        before = insights.app_reviews(self.db, 1)
        context = review_context(self.db.session, 1)
        self.assertEqual(context["focus_brand_id"], 1)
        self.assertIsNone(context["store_stats"])
        self.assertEqual(insights.app_reviews(self.db, 1), before)
        self.assertEqual(review_context(self.db.session, 999),
                         {"focus_brand_id": None, "store_stats": None})

    def test_store_stats_read_back_the_latest_written_facts(self):
        mf_repo.upsert_many(self.db.session, 1, [
            {"source": "appstore", "entity_type": "app", "entity_ref": "555",
             "metric": "rating_avg", "day": "2026-09-14", "value": 4.6375},
            {"source": "appstore", "entity_type": "app", "entity_ref": "555",
             "metric": "rating_count", "day": "2026-09-14", "value": 63846},
            {"source": "playstore", "entity_type": "app", "entity_ref": "com.x",
             "metric": "rating_avg", "day": "2026-09-14", "value": 4.7},
            {"source": "playstore", "entity_type": "app", "entity_ref": "com.x",
             "metric": "rating_count", "day": "2026-09-14", "value": 377574},
            {"source": "playstore", "entity_type": "app", "entity_ref": "com.x",
             "metric": "rating_histogram", "day": "2026-09-14",
             "dims": {"1": 14737, "2": 3968, "3": 11455, "4": 29207, "5": 318204}},
        ])
        self.db.commit()
        stats = review_context(self.db.session, 1)["store_stats"]
        self.assertEqual(stats["app_store"]["rating"], 4.6375)
        self.assertEqual(stats["app_store"]["count"], 63846)
        # No app-store rating_histogram fact was written above -- omitted, not guessed.
        self.assertNotIn("histogram", stats["app_store"])
        self.assertEqual(stats["play_store"]["rating"], 4.7)
        self.assertEqual(stats["play_store"]["count"], 377574)
        self.assertEqual(stats["play_store"]["histogram"],
                         {"1": 14737, "2": 3968, "3": 11455, "4": 29207, "5": 318204})
        # combined: count-weighted, and since only Play Store has a histogram
        # here, combined's histogram is just Play Store's.
        combined = stats["combined"]
        self.assertAlmostEqual(combined["rating"],
                               (4.6375 * 63846 + 4.7 * 377574) / (63846 + 377574), places=2)
        self.assertEqual(combined["count"], 63846 + 377574)
        self.assertEqual(combined["histogram"],
                         {"1": 14737, "2": 3968, "3": 11455, "4": 29207, "5": 318204})
        # >=4-star share of the merged histogram, with its Wilson band --
        # statistical honesty rule (project rules 0.4) applies to this derived
        # figure too, not just to the per-item scorers.
        total = 14737 + 3968 + 11455 + 29207 + 318204
        good = 29207 + 318204
        self.assertAlmostEqual(combined["good_share"], good / total, places=6)
        self.assertLess(combined["good_lo"], combined["good_share"])
        self.assertGreater(combined["good_hi"], combined["good_share"])


class StoreStatsRefreshTests(DbTestCase):
    """core/review_store.py — real, live-fetching side. Every network call is
    mocked; these tests only check that real response shapes (captured live
    against Bank Alfalah's actual app ids on 2026-09-14) get parsed and
    written correctly, and that a missing key or a failed/unrecognised
    response never fabricates a figure."""
    APPLE_OK = json.dumps({"results": [
        {"averageUserRating": 4.6375, "userRatingCount": 63846}]}).encode()
    # Synthetic but shaped like Apple's real star-mix bar markup
    # (`<li aria-label="5 stars, 74 percent, of ratings are 5 stars">`).
    APPSTORE_HTML = (
        b'<li aria-label="5 stars, 74 percent, of ratings are 5 stars">'
        b'<li aria-label="4 stars, 14 percent, of ratings are 4 stars">'
        b'<li aria-label="3 stars, 5 percent, of ratings are 3 stars">'
        b'<li aria-label="2 stars, 3 percent, of ratings are 2 stars">'
        b'<li aria-label="1 star, 4 percent, of ratings are 1 star">'
    )
    DFS_POSTED = json.dumps({"tasks": [{"id": "t1"}]}).encode()
    DFS_RESULT = json.dumps({"tasks": [{"result": [{"items": [
        {"rating": {"value": 4.7}, "reviews_count": 377574}]}]}]}).encode()
    # The live block (total 377,574, matching DataForSEO's concurrent count)
    # comes first and a stale decoy block (total 15) comes last, so a test
    # asserting the live numbers win only passes if the code prefers the
    # `expected_total` match over "last match wins".
    PLAY_HTML = (
        'junk [["4.7",4.674],[null,["14,737",14737],["3,968",3968],["11,455",11455],'
        '["29,207",29207],["318,204",318204]],["377,574",377574],'
        '["66,233",66233]] more junk '
        '[["4.6",4.6],[null,["1",1],["2",2],["3",3],["4",4],["5",5]],'
        '["15",15],["15",15]] tail'
    ).encode()

    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'Bank Alfalah','PK','now')")
        self.db.commit()

    def test_refresh_writes_both_stores_and_the_matching_histogram_block(self):
        keys = {"APPSTORE_APP_ID": "1050684372", "APPSTORE_COUNTRY": "pk",
                "PLAYSTORE_APP_ID": "com.base.bankalfalah",
                "DATAFORSEO_LOGIN": "l", "DATAFORSEO_PASSWORD": "p"}
        with patch("core.review_store._get_retry",
                   side_effect=[self.APPLE_OK, self.APPSTORE_HTML, self.DFS_POSTED, self.PLAY_HTML]), \
             patch("core.review_store.collector._get", return_value=self.DFS_RESULT), \
             patch("core.review_store.time.sleep"),              patch("integrations.adapters.app_meta.appstore", return_value={}),              patch("integrations.adapters.app_meta.playstore", return_value={}):
            out = refresh_store_stats(self.db.session, 1, keys)
        self.db.commit()
        self.assertEqual(out, {"appstore": True, "playstore": True})
        stats = review_context(self.db.session, 1)["store_stats"]
        self.assertEqual(stats["app_store"]["rating"], 4.6375)
        self.assertEqual(stats["app_store"]["count"], 63846)
        # Percentages (74/14/5/3/4) times the real total (63846), rounded.
        self.assertEqual(stats["app_store"]["histogram"],
                         {"1": 2554, "2": 1915, "3": 3192, "4": 8938, "5": 47246})
        self.assertEqual(stats["play_store"]["rating"], 4.7)
        self.assertEqual(stats["play_store"]["count"], 377574)
        # The 15-review decoy block matches nothing real; the live block
        # (total 377,574) must win because it matches the DataForSEO count.
        self.assertEqual(stats["play_store"]["histogram"],
                         {"1": 14737, "2": 3968, "3": 11455, "4": 29207, "5": 318204})
        # combined: count-weighted average of the two real store averages,
        # plus their histograms summed star by star.
        combined = stats["combined"]
        self.assertAlmostEqual(combined["rating"],
                               (4.6375 * 63846 + 4.7 * 377574) / (63846 + 377574), places=2)
        self.assertEqual(combined["count"], 63846 + 377574)
        self.assertEqual(combined["histogram"]["5"], 47246 + 318204)

    def test_every_configured_app_gets_its_own_row_and_icon(self):
        keys = {"APPSTORE_APP_ID": "111 222", "PLAYSTORE_APP_ID": "",
                "DATAFORSEO_LOGIN": "l", "DATAFORSEO_PASSWORD": "p"}
        meta = {"111": {"name": "One", "icon": "https://x/1.png"},
                "222": {"name": "Two", "icon": "http://insecure/2.png"}}
        with patch("core.review_store._get_retry", side_effect=[self.APPLE_OK, self.APPSTORE_HTML] * 2),              patch("integrations.adapters.app_meta.appstore", side_effect=lambda i, c: meta[i]):
            refresh_store_stats(self.db.session, 1, keys)
        self.db.commit()
        stats = review_context(self.db.session, 1)["store_stats"]
        apps = {a["app_id"]: a for a in stats["apps"]}
        self.assertEqual(set(apps), {"111", "222"})
        self.assertEqual(apps["111"]["name"], "One")
        self.assertEqual(apps["111"]["icon"], "https://x/1.png")
        self.assertIsNone(apps["222"]["icon"])            # non-https rejected
        self.assertEqual(apps["111"]["store"], "app_store")
        # the store headline is the count-weighted roll-up of both apps
        self.assertEqual(stats["app_store"]["count"], 2 * 63846)

    def test_missing_keys_write_nothing_and_stay_null(self):
        with patch("core.review_store._get_retry") as get:
            out = refresh_store_stats(self.db.session, 1, {})
        get.assert_not_called()
        self.db.commit()
        self.assertEqual(out, {"appstore": False, "playstore": False})
        self.assertIsNone(review_context(self.db.session, 1)["store_stats"])

    def test_histogram_parser_returns_none_on_unrecognised_page(self):
        self.assertIsNone(review_store._HIST_RE.search(b"<html>no state here</html>".decode()))

    def test_appstore_histogram_needs_a_total_to_convert_percentages_into_counts(self):
        with patch("core.review_store._get_retry") as get:
            result = review_store.fetch_appstore_histogram("1050684372", expected_total=None)
        get.assert_not_called()
        self.assertIsNone(result)

    def test_appstore_histogram_returns_none_on_unrecognised_page(self):
        with patch("core.review_store._get_retry", return_value=b"<html>no bars here</html>"):
            result = review_store.fetch_appstore_histogram("1050684372", expected_total=63846)
        self.assertIsNone(result)


class BrandImplicitMentionTests(DbTestCase):
    @patch("core.collector.REGISTRY", [collector.AppStoreReviews])
    @patch("core.collector.sentiment.score_pending", return_value={})
    @patch("integrations.adapters.app_meta.appstore", return_value={})
    @patch("core.collector._get")
    def test_app_review_item_gets_a_focus_brand_mention(self, get, _meta, _score):
        db = self.db
        db.execute("INSERT INTO workspace(id,name,market,created_at) VALUES (1,'Bank Alfalah','PK','now')")
        db.execute("INSERT INTO brand(id,workspace_id,name,is_focus,safe_patterns) "
                   "VALUES (1,1,'Bank Alfalah',1,'[\"bank alfalah\"]')")
        db.execute("INSERT INTO run(id,workspace_id,started_at,state) VALUES ('r1',1,'now','running')")
        get.side_effect = [FEED.encode()] + [b'{"feed": {}}'] * 9
        keys = {"APPSTORE_APP_ID": "555", "APPSTORE_COUNTRY": "pk"}
        collector.run_collection(db, 1, "r1", keys, lambda _m: None)
        rows = db.execute(
            """SELECT COUNT(*) FROM mention m JOIN item i ON i.id=m.item_id
               WHERE i.source='appstore_reviews' AND m.brand_id=1 AND m.rule='app_review'"""
        ).fetchone()[0]
        self.assertEqual(rows, 2)


if __name__ == "__main__":
    unittest.main()
