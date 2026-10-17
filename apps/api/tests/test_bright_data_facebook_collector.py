import json
import unittest

from ._db import DbTestCase
from pathlib import Path
from unittest.mock import patch

from core import collector
from core.bright_data import BrightDataResult


ROOT = Path(__file__).resolve().parents[1]
POSTS = [
    {
        "post_id": "p1",
        "url": "https://www.facebook.com/BankAlfalahOfficial/posts/1",
        "page_name": "Bank Alfalah",
        "user_username_raw": "BankAlfalahOfficial",
        "content": "Alfa app service update",
        "date_posted": "2026-09-01T09:00:00Z",
        "num_comments": 4,
        "likes": 20,
    },
    {
        "post_id": "p2",
        "url": "https://www.facebook.com/BankAlfalahOfficial/posts/2",
        "page_name": "Bank Alfalah",
        "content": "Cards maintenance notice",
        "date_posted": "2026-09-01T10:00:00Z",
    },
]


def keys(**overrides):
    values = {
        "BRIGHT_DATA_API_KEY": "token",
        "BRIGHT_DATA_FACEBOOK_PAGE_USERNAME": "BankAlfalahOfficial",
        "BRIGHT_DATA_FACEBOOK_PER_RUN_LIMIT": "5",
        "BRIGHT_DATA_FACEBOOK_MONTHLY_RECORD_CAP": "100",
        "BRIGHT_DATA_COST_PER_RECORD_USD": "0.002",
        "BRIGHT_DATA_MONTHLY_CAP_USD": "1.00",
        "_BRIGHT_DATA_MONTHLY_RECORDS_USED": 0,
        "_BRIGHT_DATA_MONTHLY_SPEND_USD": 0,
    }
    values.update(overrides)
    return values


class BrightDataFacebookAdapterTests(unittest.TestCase):
    @patch("core.collector.bright_data.BrightDataClient.discover_facebook_page_posts")
    def test_maps_posts_and_logs_returned_record_cost(self, discover):
        discover.return_value = BrightDataResult(POSTS, "snap_posts")
        counts = []
        logs = []
        adapter = collector.BrightDataFacebookPosts(
            keys(), logs.append, lambda *args, **kwargs: counts.append((args, kwargs))
        )

        rows = list(adapter.fetch(["Bank Alfalah", "HBL", "UBL"]))

        discover.assert_called_once_with("BankAlfalahOfficial", 5)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["external_id"], "bd-fb-post:p1")
        self.assertEqual(rows[0]["raw"]["snapshot_id"], "snap_posts")
        self.assertEqual(rows[0]["raw"]["provider_record"]["num_comments"], 4)
        self.assertEqual(counts, [
            (("brightdata_facebook_posts",),
             {"calls": 1, "units": 2, "unit_cost": 0.002})
        ])
        self.assertTrue(any("focus page only" in line for line in logs))

    @patch("core.collector.bright_data.BrightDataClient")
    def test_monthly_record_cap_stops_before_client_or_request(self, client):
        adapter = collector.BrightDataFacebookPosts(
            keys(_BRIGHT_DATA_MONTHLY_RECORDS_USED=100), lambda _line: None,
            lambda *args, **kwargs: None,
        )
        with self.assertRaises(collector.QuotaExceeded):
            list(adapter.fetch([]))
        client.assert_not_called()

    @patch("core.collector.bright_data.BrightDataClient.discover_facebook_page_posts")
    def test_remaining_monthly_records_reduce_provider_limit(self, discover):
        discover.return_value = BrightDataResult([], "snap_empty")
        adapter = collector.BrightDataFacebookPosts(
            keys(_BRIGHT_DATA_MONTHLY_RECORDS_USED=98), lambda _line: None,
            lambda *args, **kwargs: None,
        )
        list(adapter.fetch([]))
        discover.assert_called_once_with("BankAlfalahOfficial", 2)


COMMENTS = [
    {
        "comment_id": "c1",
        "post_url": "https://www.facebook.com/BankAlfalahOfficial/posts/1",
        "comment_text": "Card blocked. Message on WhatsApp 0300-1234567 please",
        "date_created": "2026-09-01T09:30:00Z",
        "user_id": "u_100",
        "user_url": "https://www.facebook.com/people/x/100",
        "user_name": "Ali",
        "parent_comment_id": None,
    },
    {
        "comment_id": "c2",
        "post_url": "https://www.facebook.com/BankAlfalahOfficial/posts/1",
        "comment_text": "Great update",
        "date_created": "2026-09-01T09:45:00Z",
        "user_id": "u_101",
    },
]
POST_URLS = [POSTS[0]["url"], POSTS[1]["url"]]


class BrightDataFacebookCommentsAdapterTests(unittest.TestCase):
    @patch("core.collector.bright_data.BrightDataClient.collect_facebook_post_comments")
    def test_maps_comments_hashes_actor_and_logs_cost(self, collect):
        collect.return_value = BrightDataResult(COMMENTS, "snap_comments")
        counts = []
        adapter = collector.BrightDataFacebookComments(
            keys(_BRIGHT_DATA_FACEBOOK_POST_URLS=POST_URLS),
            lambda *_a: None, lambda *args, **kwargs: counts.append((args, kwargs)),
        )

        rows = list(adapter.fetch([]))

        collect.assert_called_once_with(POST_URLS, 50)
        self.assertEqual([r["external_id"] for r in rows],
                         ["bd-fb-comment:c1", "bd-fb-comment:c2"])
        self.assertEqual(rows[0]["raw"]["kind"], "comment")
        self.assertEqual(rows[0]["raw"]["post_url"], POSTS[0]["url"])
        self.assertEqual(rows[0]["raw"]["provider_record"]["comment_id"], "c1")
        # actor identity is stored one-way hashed, never as the raw handle
        self.assertTrue(rows[0]["raw"]["actor_hash"])
        self.assertNotIn(rows[0]["raw"]["actor_hash"], COMMENTS[0]["user_url"])
        self.assertNotEqual(rows[0]["raw"]["actor_hash"], rows[1]["raw"]["actor_hash"])
        self.assertEqual(counts, [
            (("brightdata_facebook_comments",),
             {"calls": 1, "units": 2, "unit_cost": 0.002})
        ])

    @patch("core.collector.bright_data.BrightDataClient")
    def test_skips_when_no_posts_collected_yet(self, client):
        adapter = collector.BrightDataFacebookComments(
            keys(), lambda *_a: None, lambda *args, **kwargs: None,
        )
        self.assertEqual(list(adapter.fetch([])), [])
        client.assert_not_called()

    @patch("core.collector.bright_data.BrightDataClient")
    def test_monthly_cap_stops_comments_before_request(self, client):
        adapter = collector.BrightDataFacebookComments(
            keys(_BRIGHT_DATA_MONTHLY_RECORDS_USED=100,
                 _BRIGHT_DATA_FACEBOOK_POST_URLS=POST_URLS),
            lambda *_a: None, lambda *args, **kwargs: None,
        )
        with self.assertRaises(collector.QuotaExceeded):
            list(adapter.fetch([]))
        client.assert_not_called()

    @patch("core.collector.bright_data.BrightDataClient.collect_facebook_post_comments")
    def test_remaining_budget_limits_posts_processed(self, collect):
        collect.return_value = BrightDataResult([], "snap_empty")
        adapter = collector.BrightDataFacebookComments(
            keys(_BRIGHT_DATA_MONTHLY_RECORDS_USED=60,          # 40 records left
                 BRIGHT_DATA_FACEBOOK_COMMENTS_PER_POST="20",   # 40 // 20 -> 2 posts
                 _BRIGHT_DATA_FACEBOOK_POST_URLS=[*POST_URLS, "https://www.facebook.com/x/posts/3"]),
            lambda *_a: None, lambda *args, **kwargs: None,
        )
        list(adapter.fetch([]))
        collect.assert_called_once_with(POST_URLS, 20)

    @patch("core.collector.bright_data.BrightDataClient.collect_facebook_post_comments")
    def test_per_post_cap_is_reapplied_to_returned_rows(self, collect):
        flood = [
            {"comment_id": f"c{n}", "post_url": POSTS[0]["url"],
             "comment_text": "x", "user_id": f"u{n}"}
            for n in range(6)
        ]
        collect.return_value = BrightDataResult(flood, "snap_flood")
        adapter = collector.BrightDataFacebookComments(
            keys(BRIGHT_DATA_FACEBOOK_COMMENTS_PER_POST="3",
                 _BRIGHT_DATA_FACEBOOK_POST_URLS=[POSTS[0]["url"]]),
            lambda *_a: None, lambda *args, **kwargs: None,
        )
        rows = list(adapter.fetch([]))
        self.assertEqual(len(rows), 3)


class BrightDataFacebookPipelineTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'Bank Alfalah','PK','now')"
        )
        self.db.execute(
            "INSERT INTO brand(id,workspace_id,name,is_focus) VALUES (1,1,'Bank Alfalah',1)"
        )
        self.db.execute(
            "INSERT INTO brand(id,workspace_id,name,is_focus) VALUES (2,1,'HBL',0)"
        )
        self.db.commit()


    @patch("core.collector.sentiment.score_pending", return_value={})
    @patch("core.collector.REGISTRY", [collector.BrightDataFacebookPosts])
    @patch("core.collector.bright_data.BrightDataClient.discover_facebook_page_posts")
    def test_pipeline_persists_provenance_and_mentions_only_focus_brand(
        self, discover, _sentiment
    ):
        discover.return_value = BrightDataResult([POSTS[0]], "snap_pipeline")

        new = collector.run_collection(
            self.db, 1, "run-bd", keys(), lambda _line: None
        )

        self.assertEqual(new, 1)
        item = self.db.execute(
            "SELECT source,source_kind,url,raw_json FROM item"
        ).fetchone()
        self.assertEqual(item[:3], (
            "brightdata_facebook_posts", "licensed", POSTS[0]["url"]
        ))
        raw = json.loads(item[3])
        self.assertEqual(raw["snapshot_id"], "snap_pipeline")
        self.assertEqual(raw["provider_record"]["post_id"], "p1")
        mentions = self.db.execute("SELECT brand_id,rule FROM mention").fetchall()
        self.assertEqual(mentions, [(1, "brightdata_owned_channel")])
        call = self.db.execute(
            "SELECT calls,units,unit_cost_usd,ok FROM call_log"
        ).fetchone()
        self.assertEqual(call, (1, 1, 0.002, 1))


    @patch("core.collector.sentiment.score_pending", return_value={})
    @patch("core.collector.REGISTRY", [collector.BrightDataFacebookComments])
    @patch("core.collector.bright_data.BrightDataClient.collect_facebook_post_comments")
    def test_pipeline_collects_comments_for_prior_posts_only(self, collect, _sentiment):
        self.db.execute(
            """INSERT INTO item(workspace_id,surface,source,source_kind,external_id,url,
                                raw_json,collected_at,content_hash)
               VALUES (1,'facebook','brightdata_facebook_posts','licensed',
                       'bd-fb-post:p1',?,'{}','now','seedhash')""",
            (POSTS[0]["url"],),
        )
        self.db.commit()
        collect.return_value = BrightDataResult([COMMENTS[0]], "snap_pipe_c")

        new = collector.run_collection(
            self.db, 1, "run-bd-c", keys(), lambda _line: None
        )

        self.assertEqual(new, 1)
        collect.assert_called_once_with([POSTS[0]["url"]], 50)
        row = self.db.execute(
            "SELECT source,source_kind,raw_json FROM item WHERE source='brightdata_facebook_comments'"
        ).fetchone()
        self.assertEqual(row[:2], ("brightdata_facebook_comments", "licensed"))
        raw = json.loads(row[2])
        self.assertEqual(raw["kind"], "comment")
        self.assertTrue(raw["actor_hash"])
        self.assertEqual(raw["provider_record"]["comment_id"], "c1")
        mentions = self.db.execute(
            """SELECT m.brand_id, m.rule FROM mention m
               JOIN item i ON i.id = m.item_id
               WHERE i.source='brightdata_facebook_comments'"""
        ).fetchall()
        self.assertEqual(mentions, [(1, "brightdata_owned_channel")])
        call = self.db.execute(
            "SELECT calls,units,unit_cost_usd,ok FROM call_log WHERE source='brightdata_facebook_comments'"
        ).fetchone()
        self.assertEqual(call, (1, 1, 0.002, 1))


if __name__ == "__main__":
    unittest.main()
