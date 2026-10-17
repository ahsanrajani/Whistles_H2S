import json
import unittest

from ._db import DbTestCase
from pathlib import Path
from unittest.mock import patch

from core import collector, insights

ROOT = Path(__file__).resolve().parents[1]

ACCOUNTS_PAYLOAD = json.dumps({"data": [
    {"id": "999", "name": "Chase Securities", "access_token": "page-scoped-token"},
]})

FB_PAYLOAD = json.dumps({"data": [
    {"id": "p1", "message": "New IBFT limits from Monday",
     "permalink_url": "https://fb.com/p1", "created_time": "2026-08-20T08:00:00+0000",
     "from": {"name": "Chase Securities"},
     "full_picture": "https://scontent.fb.com/p1.jpg",
     "attachments": {"data": [{"media_type": "photo"}]},
     "likes": {"summary": {"total_count": 42}},
     "comments": {"summary": {"total_count": 1}, "data": [
         {"id": "c1", "message": "my transfer is still stuck",
          "from": {"name": "A User"}, "created_time": "2026-08-20T09:00:00+0000",
          "comments": {"data": [
              {"id": "r1", "message": "DM us your reference number",
               "from": {"name": "Chase Securities"},
               "created_time": "2026-08-20T10:00:00+0000"},
          ]}},
     ]}, "shares": {"count": 3}},
]})


class MetaAdapterTests(unittest.TestCase):
    def test_facebook_fetch_yields_post_and_comment(self):
        a = collector.MetaFacebook(
            {"META_ACCESS_TOKEN": "t", "META_PAGE_ID": "999"},
            lambda _m: None, lambda *x, **k: None)
        calls = []

        def fake_get(url, **kw):
            calls.append(url)
            return (ACCOUNTS_PAYLOAD if "/me/accounts" in url else FB_PAYLOAD).encode()

        with patch("core.collector._get", side_effect=fake_get):
            rows = list(a.fetch([]))
        self.assertEqual(len(rows), 3)
        self.assertEqual({r["outlet"] for r in rows}, {"Facebook"})
        self.assertEqual({r["raw"]["kind"] for r in rows}, {"post", "comment", "reply"})
        self.assertTrue(all(r["external_id"].startswith("fb:") for r in rows))
        # the feed call used the page-scoped token, not the raw system-user one
        self.assertIn("page-scoped-token", calls[1])

        post = next(r for r in rows if r["raw"]["kind"] == "post")
        # the tenant's own Page name, not a hardcoded brand from another workspace
        self.assertEqual(post["author"], "Chase Securities")
        self.assertEqual(post["raw"]["metrics"], {"likes": 42, "comments": 1, "shares": 3})
        self.assertIsNone(post["raw"].get("parent_id"))
        self.assertEqual(post["raw"]["media"], {"type": "photo", "image": "https://scontent.fb.com/p1.jpg"})

        comment = next(r for r in rows if r["raw"]["kind"] == "comment")
        self.assertEqual(comment["raw"]["parent_id"], "fb:p1")
        reply = next(r for r in rows if r["raw"]["kind"] == "reply")
        self.assertEqual(reply["raw"]["parent_id"], "fb:c1")
        self.assertEqual(reply["body"], "DM us your reference number")

    def test_facebook_fetch_follows_pagination_past_the_first_page(self):
        # found live: a single unpaginated 50-item page meant a post older
        # than that (and any new comment landing on it) was never looked at
        # again, ever, once the account had more than ~50 posts on file.
        page1 = json.dumps({
            "data": [{"id": "p1", "message": "newer post",
                      "created_time": "2026-08-21T00:00:00+0000"}],
            "paging": {"next": "https://graph.facebook.com/v20.0/999/feed?after=CURSOR"},
        })
        page2 = json.dumps({"data": [{"id": "p2", "message": "older post",
                                      "created_time": "2026-08-20T00:00:00+0000"}]})
        calls = []

        def fake_get(url, **kw):
            calls.append(url)
            if "/me/accounts" in url:
                return ACCOUNTS_PAYLOAD.encode()
            if "after=CURSOR" in url:
                return page2.encode()
            return page1.encode()

        a = collector.MetaFacebook(
            {"META_ACCESS_TOKEN": "t", "META_PAGE_ID": "999"},
            lambda _m: None, lambda *x, **k: None)
        with patch("core.collector._get", side_effect=fake_get):
            rows = list(a.fetch([]))
        self.assertEqual({r["external_id"] for r in rows}, {"fb:p1", "fb:p2"})
        # one /me/accounts call + two feed pages
        self.assertEqual(len(calls), 3)

    def test_facebook_fetch_stops_at_the_page_bound_even_if_more_remain(self):
        pages = iter([
            json.dumps({"data": [{"id": f"p{i}", "message": "x",
                                  "created_time": "2026-08-20T00:00:00+0000"}],
                       "paging": {"next": f"https://graph.facebook.com/v20.0/999/feed?after={i}"}})
            for i in range(1, 10)
        ])

        def fake_get(url, **kw):
            if "/me/accounts" in url:
                return ACCOUNTS_PAYLOAD.encode()
            return next(pages).encode()

        a = collector.MetaFacebook(
            {"META_ACCESS_TOKEN": "t", "META_PAGE_ID": "999"},
            lambda _m: None, lambda *x, **k: None)
        with patch("core.collector._get", side_effect=fake_get):
            rows = list(a.fetch([]))
        self.assertEqual(len({r["external_id"] for r in rows}), 4)   # max_pages default

    def test_facebook_fetch_logs_and_yields_nothing_if_page_not_in_accounts(self):
        a = collector.MetaFacebook(
            {"META_ACCESS_TOKEN": "t", "META_PAGE_ID": "999"},
            lambda _m: None, lambda *x, **k: None)
        with patch("core.collector._get", return_value=json.dumps({"data": []}).encode()):
            rows = list(a.fetch([]))
        self.assertEqual(rows, [])


class MetaFlowsIntoListeningTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'Bank Alfalah','PK','now')")
        self.db.execute(
            "INSERT INTO brand(id,workspace_id,name,is_focus) VALUES (1,1,'Bank Alfalah',1)")
        for iid, surface in ((1, "facebook"), (2, "instagram"), (3, "news")):
            self.db.execute(
                """INSERT INTO item(id,workspace_id,surface,source,source_kind,external_id,
                   url,outlet,body,lang_guess,raw_json,collected_at,content_hash)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (iid, 1, surface, "meta_" + surface if surface != "news" else "googlenews_rss",
                 "public", f"x{iid}", f"https://s/{iid}", surface.title(),
                 f"body {iid}", "en", "{}", "now", str(iid)))
            self.db.execute(
                "INSERT INTO mention(id,item_id,brand_id,rule) VALUES (?,?,1,'meta_mention')",
                (iid, iid))
        self.db.commit()


    def test_meta_items_are_not_excluded_from_listening(self):
        sov = insights.share_of_voice(self.db, 1)
        self.assertEqual(sov[0]["n"], 3)                     # all three counted
        feed_all = insights.feed(self.db, 1)
        self.assertEqual(len(feed_all), 3)

    def test_channel_filter_narrows_to_instagram(self):
        sov_ig = insights.share_of_voice(self.db, 1, "instagram")
        self.assertEqual(sov_ig[0]["n"], 1)
        feed_ig = insights.feed(self.db, 1, surface="instagram")
        self.assertEqual([r[1] for r in feed_ig], ["instagram"])


IG_PAYLOAD = json.dumps({"data": [
    {"id": "m1", "caption": "New branch opening", "permalink": "https://instagram.com/m1",
     "timestamp": "2026-08-20T08:00:00+0000", "like_count": 10, "comments_count": 0,
     "media_type": "IMAGE", "media_url": "https://scontent.ig.com/m1.jpg"},
    {"id": "m2", "caption": "Behind the scenes", "permalink": "https://instagram.com/m2",
     "timestamp": "2026-08-21T08:00:00+0000", "like_count": 5, "comments_count": 0,
     "media_type": "VIDEO", "media_url": "https://scontent.ig.com/m2.mp4",
     "thumbnail_url": "https://scontent.ig.com/m2-thumb.jpg"},
]})


class MetaInstagramMediaTests(unittest.TestCase):
    def test_image_media_is_captured(self):
        a = collector.MetaInstagram(
            {"META_ACCESS_TOKEN": "t", "META_IG_USER_ID": "IG1"},
            lambda _m: None, lambda *x, **k: None)
        with patch("core.collector._get", return_value=IG_PAYLOAD.encode()):
            rows = list(a.fetch([]))
        post1 = next(r for r in rows if r["external_id"] == "ig:m1")
        self.assertEqual(post1["raw"]["media"],
                         {"type": "photo", "image": "https://scontent.ig.com/m1.jpg"})

    def test_video_media_carries_a_real_playable_url_and_poster(self):
        a = collector.MetaInstagram(
            {"META_ACCESS_TOKEN": "t", "META_IG_USER_ID": "IG1"},
            lambda _m: None, lambda *x, **k: None)
        with patch("core.collector._get", return_value=IG_PAYLOAD.encode()):
            rows = list(a.fetch([]))
        post2 = next(r for r in rows if r["external_id"] == "ig:m2")
        self.assertEqual(post2["raw"]["media"], {
            "type": "video", "video": "https://scontent.ig.com/m2.mp4",
            "image": "https://scontent.ig.com/m2-thumb.jpg"})

    def test_instagram_fetch_follows_pagination_past_the_first_page(self):
        page1 = json.dumps({
            "data": [{"id": "m1", "caption": "newer", "timestamp": "2026-08-21T00:00:00+0000"}],
            "paging": {"next": "https://graph.facebook.com/v20.0/IG1/media?after=CURSOR"},
        })
        page2 = json.dumps({"data": [{"id": "m2", "caption": "older",
                                      "timestamp": "2026-08-20T00:00:00+0000"}]})

        def fake_get(url, **kw):
            return (page2 if "after=CURSOR" in url else page1).encode()

        a = collector.MetaInstagram(
            {"META_ACCESS_TOKEN": "t", "META_IG_USER_ID": "IG1"},
            lambda _m: None, lambda *x, **k: None)
        with patch("core.collector._get", side_effect=fake_get):
            rows = list(a.fetch([]))
        self.assertEqual({r["external_id"] for r in rows}, {"ig:m1", "ig:m2"})


if __name__ == "__main__":
    unittest.main()
