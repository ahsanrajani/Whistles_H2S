"""core/owned_posts.py -- the cross-platform "recent posts" feed."""
import unittest

import sqlalchemy as sa

from core import owned_posts

from ._db import DbTestCase


class OwnedPostsTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.commit()
        self.s = self.db.session

    def _item(self, iid, *, source, external_id, body, url, published_at,
              raw, author="Chase Securities"):
        self.s.execute(sa.text("""
            INSERT INTO item(id,workspace_id,surface,source,source_kind,external_id,
                             url,author,published_at,body,raw_json,collected_at,content_hash)
            VALUES (:id,1,'x',:source,'public',:ext,:url,:author,:pub,:body,
                    :raw,'now',:ext)
        """), {
            "id": iid, "source": source, "ext": external_id, "url": url,
            "author": author, "pub": published_at, "body": body, "raw": raw})

    def test_a_meta_post_is_included_but_a_comment_on_it_is_not(self):
        self._item(1, source="meta_facebook", external_id="fb:p1", body="our new rates",
                   url="https://fb.com/p1", published_at="2026-09-01T00:00:00Z",
                   raw='{"kind":"post","metrics":{"likes":5}}')
        self._item(2, source="meta_facebook", external_id="fb:c1", body="a comment",
                   url="https://fb.com/p1", published_at="2026-09-01T01:00:00Z",
                   raw='{"kind":"comment"}')
        self.db.commit()
        out = owned_posts.recent(self.s, 1)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["platform"], "facebook")
        self.assertEqual(out[0]["metrics"], {"likes": 5})

    def test_ordered_newest_first_across_platforms(self):
        self._item(1, source="meta_facebook", external_id="fb:p1", body="a",
                   url="https://fb.com/1", published_at="2026-09-01T00:00:00Z",
                   raw='{"kind":"post"}')
        self._item(2, source="youtube_owned_videos", external_id="video:v1", body="b",
                   url="https://youtube.com/1", published_at="2026-09-03T00:00:00Z",
                   raw='{"kind":"post"}')
        self._item(3, source="x_owned_posts", external_id="t1", body="c",
                   url="https://x.com/1", published_at="2026-09-02T00:00:00Z",
                   raw='{"kind":"post"}')
        self.db.commit()
        out = owned_posts.recent(self.s, 1)
        self.assertEqual([o["platform"] for o in out], ["youtube", "x", "facebook"])

    def test_platform_filter_narrows_the_source_set(self):
        self._item(1, source="meta_facebook", external_id="fb:p1", body="a",
                   url="https://fb.com/1", published_at="2026-09-01T00:00:00Z",
                   raw='{"kind":"post"}')
        self._item(2, source="youtube_owned_videos", external_id="video:v1", body="b",
                   url="https://youtube.com/1", published_at="2026-09-01T00:00:00Z",
                   raw='{"kind":"post"}')
        self.db.commit()
        out = owned_posts.recent(self.s, 1, platform="youtube")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["platform"], "youtube")

    def test_a_posts_media_is_surfaced_for_real_feed_rendering(self):
        self._item(1, source="meta_instagram", external_id="ig:m1", body="a reel",
                   url="https://instagram.com/m1", published_at="2026-09-01T00:00:00Z",
                   raw='{"kind":"post","media":{"type":"video","video":"https://x/m1.mp4",'
                       '"image":"https://x/m1-thumb.jpg"}}')
        self.db.commit()
        out = owned_posts.recent(self.s, 1)
        self.assertEqual(out[0]["media"],
                         {"type": "video", "video": "https://x/m1.mp4", "image": "https://x/m1-thumb.jpg"})

    def test_a_post_with_no_media_field_reports_none(self):
        self._item(1, source="meta_facebook", external_id="fb:p1", body="text only",
                   url="https://fb.com/p1", published_at="2026-09-01T00:00:00Z",
                   raw='{"kind":"post"}')
        self.db.commit()
        out = owned_posts.recent(self.s, 1)
        self.assertIsNone(out[0]["media"])

    def test_a_post_with_no_metrics_field_reports_none_not_zero(self):
        self._item(1, source="brightdata_linkedin_posts", external_id="li:1", body="a",
                   url="https://linkedin.com/1", published_at="2026-09-01T00:00:00Z",
                   raw='{"kind":"post"}')
        self.db.commit()
        out = owned_posts.recent(self.s, 1)
        self.assertIsNone(out[0]["metrics"])

    def test_real_comment_count_overrides_a_stale_zero_from_first_capture(self):
        # the post's own metrics.comments is frozen at first-fetch (0, here)
        # -- item rows are insert-only, so it never reflects comments
        # collected on a later run. recent() should show the real count.
        self._item(1, source="meta_facebook", external_id="fb:p1", body="our new rates",
                   url="https://fb.com/p1", published_at="2026-09-01T00:00:00Z",
                   raw='{"kind":"post","metrics":{"likes":5,"comments":0}}')
        self._item(2, source="meta_facebook", external_id="fb:c1", body="a real comment",
                   url="https://fb.com/c1", published_at="2026-09-02T00:00:00Z",
                   raw='{"kind":"comment","parent_id":"fb:p1"}')
        self._item(3, source="meta_facebook", external_id="fb:r1", body="a real reply",
                   url="https://fb.com/r1", published_at="2026-09-02T01:00:00Z",
                   raw='{"kind":"reply","parent_id":"fb:c1"}')
        self.db.commit()
        out = owned_posts.recent(self.s, 1)
        self.assertEqual(out[0]["metrics"]["comments"], 2)
        self.assertEqual(out[0]["metrics"]["likes"], 5)   # untouched

    def test_a_post_with_no_collected_comments_keeps_its_original_metrics(self):
        self._item(1, source="meta_facebook", external_id="fb:p1", body="our new rates",
                   url="https://fb.com/p1", published_at="2026-09-01T00:00:00Z",
                   raw='{"kind":"post","metrics":{"likes":5,"comments":0}}')
        self.db.commit()
        out = owned_posts.recent(self.s, 1)
        self.assertEqual(out[0]["metrics"]["comments"], 0)

    def test_comments_for_nests_a_comment_and_its_reply_under_the_post(self):
        self._item(1, source="meta_facebook", external_id="fb:p1", body="our post",
                   url="https://fb.com/p1", published_at="2026-09-01T00:00:00Z",
                   raw='{"kind":"post"}')
        self._item(2, source="meta_facebook", external_id="fb:c1", body="a complaint",
                   url="https://fb.com/c1", published_at="2026-09-01T01:00:00Z",
                   raw='{"kind":"comment","parent_id":"fb:p1"}')
        self._item(3, source="meta_facebook", external_id="fb:r1", body="our reply",
                   url="https://fb.com/r1", published_at="2026-09-01T02:00:00Z",
                   raw='{"kind":"reply","parent_id":"fb:c1"}')
        # a comment on a *different* post must not show up here
        self._item(4, source="meta_facebook", external_id="fb:c2", body="unrelated",
                   url="https://fb.com/c2", published_at="2026-09-01T01:00:00Z",
                   raw='{"kind":"comment","parent_id":"fb:p2"}')
        self.db.commit()
        out = owned_posts.comments_for(self.s, 1, source="meta_facebook",
                                       post_external_id="fb:p1")
        self.assertEqual([o["external_id"] for o in out], ["fb:c1", "fb:r1"])
        self.assertEqual(out[1]["parent_id"], "fb:c1")

    def test_workspaces_are_isolated(self):
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (2,'WS2','PK','now')")
        self.db.commit()
        self._item(1, source="meta_facebook", external_id="fb:p1", body="a",
                   url="https://fb.com/1", published_at="2026-09-01T00:00:00Z",
                   raw='{"kind":"post"}')
        self.db.commit()
        self.assertEqual(owned_posts.recent(self.s, 2), [])


if __name__ == "__main__":
    unittest.main()
