"""core/owned_media_backfill.py -- fills in real media on Facebook/Instagram
posts collected before media capture shipped. Every Graph API call mocked;
nothing hits the network."""
import json
import unittest
from unittest.mock import patch

import sqlalchemy as sa

from core import collector, owned_media_backfill

from ._db import DbTestCase

KEYS = {"META_ACCESS_TOKEN": "user-token", "META_PAGE_ID": "999"}
ACCOUNTS_OK = json.dumps({"data": [{"id": "999", "access_token": "page-token"}]})
FB_POST_OK = json.dumps({"full_picture": "https://x/p1.jpg",
                         "attachments": {"data": [{"media_type": "photo"}]}})
FB_VIDEO_OK = json.dumps({"full_picture": "https://x/p2.jpg",
                          "attachments": {"data": [{"media_type": "video"}]}})
IG_IMAGE_OK = json.dumps({"media_type": "IMAGE", "media_url": "https://x/m1.jpg"})
IG_VIDEO_OK = json.dumps({"media_type": "VIDEO", "media_url": "https://x/m2.mp4",
                          "thumbnail_url": "https://x/m2-thumb.jpg"})


class OwnedMediaBackfillTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.commit()
        self.s = self.db.session

    def _item(self, iid, source, external_id, raw, published="2026-09-01T00:00:00Z"):
        self.s.execute(sa.text("""
            INSERT INTO item(id,workspace_id,surface,source,source_kind,external_id,
                             url,published_at,body,raw_json,collected_at,content_hash)
            VALUES (:id,1,'x',:source,'public',:ext,'https://s',:pub,'body',:raw,'now',:ext)
        """), {"id": iid, "source": source, "ext": external_id, "pub": published, "raw": raw})
        self.db.commit()

    def test_a_stale_facebook_post_is_backfilled_with_real_media(self):
        self._item(1, "meta_facebook", "fb:p1", '{"kind":"post","metrics":{"likes":1}}')
        with patch.object(collector, "_get", side_effect=[ACCOUNTS_OK, FB_POST_OK]):
            out = owned_media_backfill.backfill(self.s, 1, KEYS)
        self.db.commit()
        self.assertEqual(out, {"checked": 1, "updated": 1})
        raw = json.loads(self.s.execute(sa.text(
            "SELECT raw_json FROM item WHERE id = 1")).scalar())
        self.assertEqual(raw["media"], {"type": "photo", "image": "https://x/p1.jpg"})
        self.assertEqual(raw["metrics"], {"likes": 1})   # untouched

    def test_a_facebook_video_post_is_tagged_video(self):
        self._item(1, "meta_facebook", "fb:p2", '{"kind":"post"}')
        with patch.object(collector, "_get", side_effect=[ACCOUNTS_OK, FB_VIDEO_OK]):
            owned_media_backfill.backfill(self.s, 1, KEYS)
        self.db.commit()
        raw = json.loads(self.s.execute(sa.text(
            "SELECT raw_json FROM item WHERE id = 1")).scalar())
        self.assertEqual(raw["media"]["type"], "video")

    def test_an_instagram_video_gets_a_real_playable_url_and_poster(self):
        self._item(1, "meta_instagram", "ig:m2", '{"kind":"post"}')
        with patch.object(collector, "_get", return_value=IG_VIDEO_OK):
            owned_media_backfill.backfill(self.s, 1, KEYS)
        self.db.commit()
        raw = json.loads(self.s.execute(sa.text(
            "SELECT raw_json FROM item WHERE id = 1")).scalar())
        self.assertEqual(raw["media"], {"type": "video", "video": "https://x/m2.mp4",
                                        "image": "https://x/m2-thumb.jpg"})

    def test_a_post_that_already_has_media_is_left_alone(self):
        # filtered out in SQL -- never even examined, not just skipped.
        self._item(1, "meta_facebook", "fb:p1",
                  '{"kind":"post","media":{"type":"photo","image":"https://old/x.jpg"}}')
        with patch.object(collector, "_get") as get:
            out = owned_media_backfill.backfill(self.s, 1, KEYS)
        get.assert_not_called()
        self.assertEqual(out, {"checked": 0, "updated": 0})

    def test_a_comment_row_is_never_touched(self):
        # also filtered out in SQL: a naive ORDER BY ... LIMIT with no kind
        # filter let comment rows (which vastly outnumber posts) eat almost
        # the whole limit, so most real posts were never even examined.
        self._item(1, "meta_facebook", "fb:c1", '{"kind":"comment","parent_id":"fb:p1"}')
        with patch.object(collector, "_get") as get:
            out = owned_media_backfill.backfill(self.s, 1, KEYS)
        get.assert_not_called()
        self.assertEqual(out, {"checked": 0, "updated": 0})

    def test_a_youtube_post_is_backfilled_with_no_api_call(self):
        self._item(1, "youtube_owned_videos", "video:v1", '{"kind":"post","metrics":{"views":10}}')
        with patch.object(collector, "_get") as get:
            out = owned_media_backfill.backfill(self.s, 1, KEYS)
        get.assert_not_called()   # derivable from the id alone
        self.assertEqual(out, {"checked": 1, "updated": 1})
        raw = json.loads(self.s.execute(sa.text(
            "SELECT raw_json FROM item WHERE id = 1")).scalar())
        self.assertEqual(raw["media"], {"type": "youtube", "video_id": "v1",
                                        "image": "https://i.ytimg.com/vi/v1/hqdefault.jpg"})
        self.assertEqual(raw["metrics"], {"views": 10})   # untouched

    def test_a_failed_lookup_for_one_post_does_not_stop_the_rest(self):
        self._item(1, "meta_facebook", "fb:p1", '{"kind":"post"}',
                  published="2026-09-02T00:00:00Z")
        self._item(2, "meta_facebook", "fb:p2", '{"kind":"post"}',
                  published="2026-09-01T00:00:00Z")

        def boom(url, timeout=30):
            if "me/accounts" in url:
                return ACCOUNTS_OK
            if "p1" in url:
                raise RuntimeError("rate limited")
            return FB_POST_OK

        with patch.object(collector, "_get", side_effect=boom):
            out = owned_media_backfill.backfill(self.s, 1, KEYS)
        self.db.commit()
        self.assertEqual(out, {"checked": 2, "updated": 1})

    def test_comment_rows_do_not_crowd_a_real_post_out_of_a_small_limit(self):
        # the actual bug found live: an unfiltered ORDER BY ... LIMIT let a
        # page of recent comments consume the whole limit, so a real post
        # just outside that window was never even looked at.
        for i in range(1, 6):
            self._item(i, "meta_facebook", f"fb:c{i}", '{"kind":"comment","parent_id":"fb:p1"}',
                      published=f"2026-09-0{i+1}T00:00:00Z")
        self._item(6, "meta_facebook", "fb:p1", '{"kind":"post"}',
                  published="2026-09-01T00:00:00Z")   # oldest -> last in ORDER BY
        with patch.object(collector, "_get", side_effect=[ACCOUNTS_OK, FB_POST_OK]):
            out = owned_media_backfill.backfill(self.s, 1, KEYS, limit=3)
        self.db.commit()
        self.assertEqual(out, {"checked": 1, "updated": 1})
        raw = json.loads(self.s.execute(sa.text(
            "SELECT raw_json FROM item WHERE id = 6")).scalar())
        self.assertIn("media", raw)

    def test_workspaces_are_isolated(self):
        self._item(1, "meta_facebook", "fb:p1", '{"kind":"post"}')
        self.s.execute(sa.text(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (2,'WS2','PK','now')"))
        self.db.commit()
        with patch.object(collector, "_get") as get:
            out = owned_media_backfill.backfill(self.s, 2, KEYS)
        get.assert_not_called()
        self.assertEqual(out, {"checked": 0, "updated": 0})


if __name__ == "__main__":
    unittest.main()
