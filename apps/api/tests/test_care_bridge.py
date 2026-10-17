"""core/care_bridge.py -- real collected mentions -> real Care cases."""
import unittest

import sqlalchemy as sa

from core import care_bridge

from ._db import DbTestCase


class CareBridgeTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.execute(
            "INSERT INTO brand(id,workspace_id,name,is_focus) VALUES (1,1,'Chase Securities',1)")
        self.db.commit()
        self.s = self.db.session

    def _item(self, iid, *, source="youtube_v3", external_id, body,
              published_at="2026-09-01T00:00:00Z", author="A Customer"):
        self.s.execute(sa.text("""
            INSERT INTO item(id,workspace_id,surface,source,source_kind,external_id,
                             url,author,published_at,body,raw_json,collected_at,content_hash)
            VALUES (:id,1,'youtube',:source,'public',:ext,'https://x/'||:id,:author,
                    :pub,:body,'{}','now',:ext)
        """), {"id": iid, "source": source, "ext": external_id, "author": author,
               "pub": published_at, "body": body})

    def _mention(self, mid, item_id, *, category=None, sentiment=None,
                excluded=0, hidden=0):
        self.s.execute(sa.text(
            "INSERT INTO mention(id,workspace_id,item_id,brand_id,rule,excluded,hidden) "
            "VALUES (:id,1,:item,1,'exact_name',:ex,:hd)"),
            {"id": mid, "item": item_id, "ex": excluded, "hd": hidden})
        if category:
            self.s.execute(sa.text(
                "INSERT INTO mention_class(workspace_id,mention_id,category,model_id,classified_at) "
                "VALUES (1,:mid,:cat,'rule','now')"), {"mid": mid, "cat": category})
        if sentiment:
            self.s.execute(sa.text(
                "INSERT INTO sentiment(workspace_id,mention_id,label,model_id,scored_lang,scored_at) "
                "VALUES (1,:mid,:lbl,'rule','en','now')"), {"mid": mid, "lbl": sentiment})

    def test_a_complaint_mention_becomes_a_care_case(self):
        self._item(1, external_id="comment:c1", body="Terrible service at the branch.")
        self._mention(1, 1, category="complaint")
        self.db.commit()

        out = care_bridge.backfill(self.s, 1)
        self.db.commit()
        self.assertEqual(out, {"scanned": 1, "created": 1})

        row = self.s.execute(sa.text(
            "SELECT channel FROM case_message WHERE platform_ref='comment:c1'")).first()
        self.assertEqual(row[0], "youtube")

    def test_a_negative_sentiment_mention_with_no_category_still_qualifies(self):
        self._item(1, external_id="comment:c2", body="This is unacceptable.")
        self._mention(1, 1, sentiment="neg")
        self.db.commit()
        out = care_bridge.backfill(self.s, 1)
        self.assertEqual(out["created"], 1)

    def test_a_praise_mention_is_bridged_too(self):
        # No category/sentiment gate: every customer-authored, reply-able
        # comment reaches the queue -- an agent triages, not the bridge.
        self._item(1, external_id="comment:c3", body="Great service, thanks!")
        self._mention(1, 1, category="praise", sentiment="pos")
        self.db.commit()
        out = care_bridge.backfill(self.s, 1)
        self.assertEqual(out, {"scanned": 1, "created": 1})

    def test_an_unclassified_mention_with_no_category_or_sentiment_is_bridged(self):
        self._item(1, external_id="comment:c9", body="Just a regular comment.")
        self._mention(1, 1)
        self.db.commit()
        out = care_bridge.backfill(self.s, 1)
        self.assertEqual(out, {"scanned": 1, "created": 1})

    def test_an_excluded_or_hidden_mention_is_not_bridged(self):
        self._item(1, external_id="comment:c4", body="complaint text")
        self._mention(1, 1, category="complaint", excluded=1)
        self._item(2, external_id="comment:c5", body="complaint text 2")
        self._mention(2, 2, category="complaint", hidden=1)
        self.db.commit()
        out = care_bridge.backfill(self.s, 1)
        self.assertEqual(out["created"], 0)

    def test_a_youtube_video_item_is_never_bridged_even_if_classified_negative(self):
        # a video's own external_id has no "comment:" prefix -- it is the
        # brand's/a third party's content, not something a customer said.
        self._item(1, external_id="vid123", body="Market Crashes 5,000 Points!")
        self._mention(1, 1, category="complaint", sentiment="neg")
        self.db.commit()
        out = care_bridge.backfill(self.s, 1)
        self.assertEqual(out, {"scanned": 0, "created": 0})

    def test_a_facebook_post_is_skipped_but_a_facebook_comment_is_bridged(self):
        self.s.execute(sa.text("""
            INSERT INTO item(id,workspace_id,surface,source,source_kind,external_id,
                             url,author,published_at,body,raw_json,collected_at,content_hash)
            VALUES (1,1,'facebook','meta_facebook','public','fb:post1','https://x/1',
                    'Chase Securities','2026-09-01T00:00:00Z','our own post',
                    '{"kind":"post"}','now','h1'),
                   (2,1,'facebook','meta_facebook','public','fb:cmt1','https://x/2',
                    'A Customer','2026-09-01T00:00:00Z','Why is support so slow?',
                    '{"kind":"comment"}','now','h2')
        """))
        self._mention(1, 1, category="complaint")
        self._mention(2, 2, category="question")
        self.db.commit()
        out = care_bridge.backfill(self.s, 1)
        self.assertEqual(out, {"scanned": 1, "created": 1})
        row = self.s.execute(sa.text(
            "SELECT 1 FROM case_message WHERE platform_ref='fb:cmt1'")).first()
        self.assertIsNotNone(row)

    def test_a_source_care_cannot_reply_to_is_skipped(self):
        self._item(1, source="googlenews_rss", external_id="news:1",
                   body="a news article mentioning a complaint")
        self._mention(1, 1, category="complaint")
        self.db.commit()
        out = care_bridge.backfill(self.s, 1)
        self.assertEqual(out, {"scanned": 0, "created": 0})

    def test_a_second_run_does_not_duplicate_the_case(self):
        self._item(1, external_id="comment:c6", body="Terrible service.")
        self._mention(1, 1, category="complaint")
        self.db.commit()
        care_bridge.backfill(self.s, 1)
        self.db.commit()
        out = care_bridge.backfill(self.s, 1)
        self.assertEqual(out, {"scanned": 0, "created": 0})

    def test_facebook_and_instagram_get_distinct_channels_not_both_meta(self):
        # matches ChannelBadge's Channel union (primitives.tsx) and the
        # write-client _ALIASES that map both back to "meta" on reply --
        # care_bridge must not collapse them itself.
        self.s.execute(sa.text("""
            INSERT INTO item(id,workspace_id,surface,source,source_kind,external_id,
                             url,author,published_at,body,raw_json,collected_at,content_hash)
            VALUES (1,1,'facebook','meta_facebook','public','fb:c1','https://fb.com/c1',
                    'A Customer','2026-09-01T00:00:00Z','Why is support so slow?',
                    '{"kind":"comment"}','now','h1'),
                   (2,1,'instagram','meta_instagram','public','ig:c1','https://ig.com/c1',
                    'A Customer','2026-09-01T00:00:00Z','Why is support so slow?',
                    '{"kind":"comment"}','now','h2')
        """))
        self._mention(1, 1, category="complaint")
        self._mention(2, 2, category="complaint")
        self.db.commit()
        care_bridge.backfill(self.s, 1)
        self.db.commit()
        rows = dict(self.s.execute(sa.text(
            "SELECT platform_ref, channel FROM case_message "
            "WHERE platform_ref IN ('fb:c1','ig:c1')")).fetchall())
        self.assertEqual(rows["fb:c1"], "facebook")
        self.assertEqual(rows["ig:c1"], "instagram")

    def test_permalink_is_the_real_source_url_not_the_api_ref(self):
        self._item(1, external_id="comment:c8", body="Terrible service.")
        self._mention(1, 1, category="complaint")
        self.db.commit()
        care_bridge.backfill(self.s, 1)
        self.db.commit()
        row = self.s.execute(sa.text(
            "SELECT permalink FROM case_message WHERE platform_ref='comment:c8'")).scalar()
        self.assertEqual(row, "https://x/1")

    def test_platform_ref_lets_the_reply_target_the_right_comment(self):
        self._item(1, external_id="comment:c7", body="Terrible service.")
        self._mention(1, 1, category="complaint")
        self.db.commit()
        care_bridge.backfill(self.s, 1)
        self.db.commit()
        row = self.s.execute(sa.text(
            "SELECT direction, body FROM case_message WHERE platform_ref='comment:c7'")).first()
        self.assertEqual(row, ("inbound", "Terrible service."))


if __name__ == "__main__":
    unittest.main()
