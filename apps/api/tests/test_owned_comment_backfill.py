"""core/owned_comment_backfill.py -- patches parent_id onto Facebook/
Instagram comment/reply rows collected before nested-reply tracking
existed. Every Graph API call mocked; nothing hits the network."""
import json
import unittest
from unittest.mock import patch

import sqlalchemy as sa

from core import collector, owned_comment_backfill

from ._db import DbTestCase

KEYS = {"META_ACCESS_TOKEN": "user-token", "META_PAGE_ID": "999",
       "META_IG_USER_ID": "IG1"}
ACCOUNTS_OK = json.dumps({"data": [{"id": "999", "access_token": "page-token"}]})

FB_PAYLOAD = json.dumps({"data": [
    {"id": "p1", "message": "a post", "created_time": "2026-08-20T08:00:00+0000",
     "comments": {"data": [
         {"id": "c1", "message": "a real comment", "created_time": "2026-08-20T09:00:00+0000"},
     ]}},
]})
IG_PAYLOAD = json.dumps({"data": [
    {"id": "m1", "caption": "a reel", "timestamp": "2026-08-20T08:00:00+0000",
     "comments": {"data": [
         {"id": "cm1", "text": "nice", "timestamp": "2026-08-20T09:00:00+0000",
          "username": "someone"},
     ]}},
]})


class OwnedCommentBackfillTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.commit()
        self.s = self.db.session

    def _item(self, iid, source, external_id, raw):
        self.s.execute(sa.text("""
            INSERT INTO item(id,workspace_id,surface,source,source_kind,external_id,
                             url,published_at,body,raw_json,collected_at,content_hash)
            VALUES (:id,1,'x',:source,'public',:ext,'https://s','2026-08-20T09:00:00Z',
                    'body',:raw,'now',:ext)
        """), {"id": iid, "source": source, "ext": external_id, "raw": raw})
        self.db.commit()

    def test_a_facebook_comment_missing_parent_id_is_patched(self):
        self._item(1, "meta_facebook", "fb:c1", '{"kind":"comment"}')

        def fake_get(url, **kw):
            return (ACCOUNTS_OK if "/me/accounts" in url else FB_PAYLOAD).encode()

        with patch.object(collector, "_get", side_effect=fake_get):
            out = owned_comment_backfill.backfill(self.s, 1, KEYS)
        self.db.commit()
        self.assertEqual(out, {"checked": 1, "updated": 1})
        raw = json.loads(self.s.execute(sa.text(
            "SELECT raw_json FROM item WHERE id = 1")).scalar())
        self.assertEqual(raw["parent_id"], "fb:p1")

    def test_an_instagram_comment_missing_parent_id_is_patched(self):
        self._item(1, "meta_instagram", "ig:cm1", '{"kind":"comment"}')
        with patch.object(collector, "_get", return_value=IG_PAYLOAD.encode()):
            out = owned_comment_backfill.backfill(self.s, 1, KEYS)
        self.db.commit()
        self.assertEqual(out["updated"], 1)
        raw = json.loads(self.s.execute(sa.text(
            "SELECT raw_json FROM item WHERE id = 1")).scalar())
        self.assertEqual(raw["parent_id"], "ig:m1")

    def test_a_comment_that_already_has_a_parent_id_is_left_alone(self):
        self._item(1, "meta_facebook", "fb:c1", '{"kind":"comment","parent_id":"fb:other"}')

        def fake_get(url, **kw):
            return (ACCOUNTS_OK if "/me/accounts" in url else FB_PAYLOAD).encode()

        with patch.object(collector, "_get", side_effect=fake_get):
            owned_comment_backfill.backfill(self.s, 1, KEYS)
        self.db.commit()
        raw = json.loads(self.s.execute(sa.text(
            "SELECT raw_json FROM item WHERE id = 1")).scalar())
        self.assertEqual(raw["parent_id"], "fb:other")   # untouched, not overwritten

    def test_a_comment_not_on_file_at_all_is_skipped_not_inserted(self):
        # a normal collection run is what handles a genuinely new comment;
        # this backfill only patches rows that already exist.
        def fake_get(url, **kw):
            return (ACCOUNTS_OK if "/me/accounts" in url else FB_PAYLOAD).encode()

        with patch.object(collector, "_get", side_effect=fake_get):
            out = owned_comment_backfill.backfill(self.s, 1, KEYS)
        self.assertEqual(out["updated"], 0)
        count = self.s.execute(sa.text("SELECT count(*) FROM item")).scalar()
        self.assertEqual(count, 0)

    def test_a_failed_source_does_not_stop_the_other(self):
        self._item(1, "meta_instagram", "ig:cm1", '{"kind":"comment"}')

        def fake_get(url, **kw):
            if "me/accounts" in url:
                raise RuntimeError("boom")
            return IG_PAYLOAD.encode()

        with patch.object(collector, "_get", side_effect=fake_get):
            out = owned_comment_backfill.backfill(self.s, 1, KEYS)
        self.db.commit()
        self.assertEqual(out["updated"], 1)   # instagram still succeeded


if __name__ == "__main__":
    unittest.main()
