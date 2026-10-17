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
        "post_id": "ig1",
        "shortcode": "ABC123",
        "url": "https://www.instagram.com/p/ABC123/",
        "profile_name": "Bank Alfalah",
        "user_posted": "bankalfalah",
        "caption": "Alfa app service update",
        "date_posted": "2026-09-01T09:00:00Z",
        "num_comments": 4,
        "likes": 30,
    },
    {
        "post_id": "ig2",
        "url": "https://www.instagram.com/p/DEF456/",
        "profile_name": "Bank Alfalah",
        "caption": "Cards maintenance notice",
        "date_posted": "2026-09-01T10:00:00Z",
    },
    {"post_id": "ig3", "url": "https://www.instagram.com/p/GHI789/"},  # no caption -> skipped
]


COMMENTS = [
    {
        "comment_id": "igc1",
        "post_url": "https://www.instagram.com/p/ABC123/",
        "comment_text": "DM me on WhatsApp +92 300 1234567 for help",
        "date_created": "2026-09-01T09:30:00Z",
        "user_id": "u_200",
        "user_url": "https://www.instagram.com/u200/",
        "user_name": "sara",
        "parent_comment_id": None,
    },
    {
        "comment_id": "igc2",
        "post_url": "https://www.instagram.com/p/ABC123/",
        "comment_text": "love this",
        "date_created": "2026-09-01T09:40:00Z",
        "user_id": "u_201",
    },
]
IG_POST_URLS = [POSTS[0]["url"], POSTS[1]["url"]]


def keys(**overrides):
    values = {
        "BRIGHT_DATA_API_KEY": "token",
        "BRIGHT_DATA_INSTAGRAM_USERNAME": "bankalfalah",
        "BRIGHT_DATA_INSTAGRAM_PER_RUN_LIMIT": "5",
        "BRIGHT_DATA_FACEBOOK_MONTHLY_RECORD_CAP": "100",
        "BRIGHT_DATA_COST_PER_RECORD_USD": "0.002",
        "BRIGHT_DATA_MONTHLY_CAP_USD": "1.00",
        "_BRIGHT_DATA_MONTHLY_RECORDS_USED": 0,
        "_BRIGHT_DATA_MONTHLY_SPEND_USD": 0,
    }
    values.update(overrides)
    return values


class BrightDataInstagramAdapterTests(unittest.TestCase):
    @patch("core.collector.bright_data.BrightDataClient.discover_instagram_profile_posts")
    def test_maps_posts_and_logs_returned_record_cost(self, discover):
        discover.return_value = BrightDataResult(POSTS, "snap_ig")
        counts = []
        adapter = collector.BrightDataInstagramPosts(
            keys(), lambda *_a: None, lambda *args, **kwargs: counts.append((args, kwargs))
        )

        rows = list(adapter.fetch(["Bank Alfalah", "HBL"]))

        discover.assert_called_once_with("bankalfalah", 5)
        self.assertEqual([r["external_id"] for r in rows],
                         ["bd-ig-post:ig1", "bd-ig-post:ig2"])
        self.assertEqual(rows[0]["url"], "https://www.instagram.com/p/ABC123/")
        self.assertEqual(rows[0]["raw"]["snapshot_id"], "snap_ig")
        self.assertEqual(rows[0]["raw"]["provider_record"]["num_comments"], 4)
        self.assertEqual(counts, [
            (("brightdata_instagram_posts",),
             {"calls": 1, "units": 3, "unit_cost": 0.002})
        ])

    @patch("core.collector.bright_data.BrightDataClient")
    def test_monthly_cap_stops_before_client_or_request(self, client):
        adapter = collector.BrightDataInstagramPosts(
            keys(_BRIGHT_DATA_MONTHLY_RECORDS_USED=100), lambda *_a: None,
            lambda *args, **kwargs: None,
        )
        with self.assertRaises(collector.QuotaExceeded):
            list(adapter.fetch([]))
        client.assert_not_called()

    @patch("core.collector.bright_data.BrightDataClient.discover_instagram_profile_posts")
    def test_remaining_monthly_records_reduce_provider_limit(self, discover):
        discover.return_value = BrightDataResult([], "snap_empty")
        adapter = collector.BrightDataInstagramPosts(
            keys(_BRIGHT_DATA_MONTHLY_RECORDS_USED=98), lambda *_a: None,
            lambda *args, **kwargs: None,
        )
        list(adapter.fetch([]))
        discover.assert_called_once_with("bankalfalah", 2)


class BrightDataInstagramCommentsAdapterTests(unittest.TestCase):
    @patch("core.collector.bright_data.BrightDataClient.collect_instagram_post_comments")
    def test_maps_comments_hashes_actor_and_logs_cost(self, collect):
        collect.return_value = BrightDataResult(COMMENTS, "snap_ig_c")
        counts = []
        adapter = collector.BrightDataInstagramComments(
            keys(_BRIGHT_DATA_INSTAGRAM_POST_URLS=IG_POST_URLS),
            lambda *_a: None, lambda *args, **kwargs: counts.append((args, kwargs)),
        )

        rows = list(adapter.fetch([]))

        collect.assert_called_once_with(IG_POST_URLS, 50)
        self.assertEqual([r["external_id"] for r in rows],
                         ["bd-ig-comment:igc1", "bd-ig-comment:igc2"])
        self.assertEqual(rows[0]["outlet"], "Instagram")
        self.assertEqual(rows[0]["raw"]["kind"], "comment")
        self.assertTrue(rows[0]["raw"]["actor_hash"])
        self.assertNotEqual(rows[0]["raw"]["actor_hash"], rows[1]["raw"]["actor_hash"])
        self.assertEqual(counts, [
            (("brightdata_instagram_comments",),
             {"calls": 1, "units": 2, "unit_cost": 0.002})
        ])

    @patch("core.collector.bright_data.BrightDataClient")
    def test_skips_when_no_posts_collected_yet(self, client):
        adapter = collector.BrightDataInstagramComments(
            keys(), lambda *_a: None, lambda *args, **kwargs: None,
        )
        self.assertEqual(list(adapter.fetch([])), [])
        client.assert_not_called()

    @patch("core.collector.bright_data.BrightDataClient")
    def test_monthly_cap_stops_comments_before_request(self, client):
        adapter = collector.BrightDataInstagramComments(
            keys(_BRIGHT_DATA_MONTHLY_RECORDS_USED=100,
                 _BRIGHT_DATA_INSTAGRAM_POST_URLS=IG_POST_URLS),
            lambda *_a: None, lambda *args, **kwargs: None,
        )
        with self.assertRaises(collector.QuotaExceeded):
            list(adapter.fetch([]))
        client.assert_not_called()


class BrightDataInstagramPipelineTests(DbTestCase):
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
    @patch("core.collector.REGISTRY", [collector.BrightDataInstagramPosts])
    @patch("core.collector.bright_data.BrightDataClient.discover_instagram_profile_posts")
    def test_pipeline_persists_provenance_and_mentions_only_focus_brand(
        self, discover, _sentiment
    ):
        discover.return_value = BrightDataResult([POSTS[0]], "snap_ig_pipe")

        new = collector.run_collection(
            self.db, 1, "run-bd-ig", keys(), lambda _line: None
        )

        self.assertEqual(new, 1)
        item = self.db.execute(
            "SELECT surface,source,source_kind,url,raw_json FROM item"
        ).fetchone()
        self.assertEqual(item[:4], (
            "instagram", "brightdata_instagram_posts", "licensed", POSTS[0]["url"]
        ))
        raw = json.loads(item[4])
        self.assertEqual(raw["snapshot_id"], "snap_ig_pipe")
        self.assertEqual(raw["provider_record"]["post_id"], "ig1")
        mentions = self.db.execute("SELECT brand_id,rule FROM mention").fetchall()
        self.assertEqual(mentions, [(1, "brightdata_owned_channel")])
        call = self.db.execute(
            "SELECT calls,units,unit_cost_usd,ok FROM call_log"
        ).fetchone()
        self.assertEqual(call, (1, 1, 0.002, 1))


    @patch("core.collector.sentiment.score_pending", return_value={})
    @patch("core.collector.REGISTRY", [collector.BrightDataInstagramComments])
    @patch("core.collector.bright_data.BrightDataClient.collect_instagram_post_comments")
    def test_pipeline_collects_comments_for_prior_ig_posts_only(self, collect, _sentiment):
        self.db.execute(
            """INSERT INTO item(workspace_id,surface,source,source_kind,external_id,url,
                                raw_json,collected_at,content_hash)
               VALUES (1,'instagram','brightdata_instagram_posts','licensed',
                       'bd-ig-post:ig1',?,'{}','now','seedhash')""",
            (POSTS[0]["url"],),
        )
        self.db.commit()
        collect.return_value = BrightDataResult([COMMENTS[0]], "snap_ig_c_pipe")

        new = collector.run_collection(
            self.db, 1, "run-bd-ig-c", keys(), lambda _line: None
        )

        self.assertEqual(new, 1)
        collect.assert_called_once_with([POSTS[0]["url"]], 50)
        row = self.db.execute(
            "SELECT surface,source,source_kind,raw_json FROM item "
            "WHERE source='brightdata_instagram_comments'"
        ).fetchone()
        self.assertEqual(row[:3], ("instagram", "brightdata_instagram_comments", "licensed"))
        raw = json.loads(row[3])
        self.assertEqual(raw["kind"], "comment")
        self.assertTrue(raw["actor_hash"])
        mentions = self.db.execute(
            """SELECT m.brand_id, m.rule FROM mention m
               JOIN item i ON i.id = m.item_id
               WHERE i.source='brightdata_instagram_comments'"""
        ).fetchall()
        self.assertEqual(mentions, [(1, "brightdata_owned_channel")])


if __name__ == "__main__":
    unittest.main()
