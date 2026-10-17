"""YouTube Data API v3 write transport."""
import io
import json
import unittest
from unittest.mock import patch

import sqlalchemy as sa

from integrations import write
from integrations.write import youtube_write_transport as yt

from ._db import DbTestCase

CREDS = {"YOUTUBE_OAUTH_TOKEN": "ytok"}


class BuildRequestTests(unittest.TestCase):
    def test_reply_public_is_a_child_comment(self):
        m, url, body = yt.build_request("reply_public", "CMT_1", {"text": "thanks"})
        self.assertEqual((m, url), ("POST", f"{yt.API}/comments?part=snippet"))
        self.assertEqual(body["snippet"],
                         {"parentId": "CMT_1", "textOriginal": "thanks"})

    def test_publish_is_a_top_level_comment_thread(self):
        m, url, body = yt.build_request("publish", "VID9", {"text": "hi"})
        self.assertEqual((m, url), ("POST", f"{yt.API}/commentThreads?part=snippet"))
        self.assertEqual(body["snippet"]["videoId"], "VID9")

    def test_delete_reply_targets_the_comment_id(self):
        m, url, _b = yt.build_request("delete_reply", "CMT_2", {})
        self.assertEqual((m, url), ("DELETE", f"{yt.API}/comments?id=CMT_2"))

    def test_missing_target_raises(self):
        with self.assertRaises(write.WriteError):
            yt.build_request("reply_public", None, {"text": "x"})


class _Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


class LiveTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.commit()
        self.s = self.db.session

    def _row(self, aid):
        return self.s.execute(sa.text(
            "SELECT state, external_id, error FROM outbound_action WHERE id=:i"),
            {"i": aid}).mappings().first()

    def test_live_reply_records_the_new_comment_id(self):
        seen = {}

        def fake(req, timeout=None):
            seen["url"] = req.full_url
            seen["auth"] = req.get_header("Authorization")
            return _Resp(b'{"id": "NEWCMT", "snippet": {"textOriginal": "thanks"}}')

        c = write.YouTubeWriteClient({**CREDS, "GURU_WRITE_LIVE": "1"})
        with patch("integrations.write.youtube_write_transport.urllib.request.urlopen", fake):
            r = c.reply_public(self.s, 1, target_ref="CMT_1", text="thanks")
        self.db.commit()
        self.assertEqual(seen["auth"], "Bearer ytok")
        self.assertEqual(r.state, "sent")
        self.assertEqual(r.external_id, "NEWCMT")

    def test_api_error_is_failed(self):
        import urllib.error

        def boom(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 403, "no", {},
                                         io.BytesIO(b'{"error":{"message":"insufficientPermissions"}}'))

        c = write.YouTubeWriteClient({**CREDS, "GURU_WRITE_LIVE": "1"})
        with patch("integrations.write.youtube_write_transport.urllib.request.urlopen", boom):
            r = c.reply_public(self.s, 1, target_ref="CMT_1", text="x")
        self.db.commit()
        self.assertEqual(r.state, "failed")
        self.assertIn("insufficientPermissions", self._row(r.action_id)["error"])

    def test_dry_run_by_default(self):
        c = write.YouTubeWriteClient(CREDS)
        r = c.reply_public(self.s, 1, target_ref="CMT_1", text="x")
        self.db.commit()
        self.assertEqual(self._row(r.action_id)["state"], "dry_run")

    def test_an_oauth_refresh_triple_is_live_even_without_a_static_token(self):
        refresh_keys = {"GOOGLE_OAUTH2_CLIENT_ID": "cid",
                        "GOOGLE_OAUTH2_CLIENT_SECRET": "sec",
                        "GOOGLE_OAUTH2_REFRESH_TOKEN": "rt", "GURU_WRITE_LIVE": "1"}
        c = write.YouTubeWriteClient(refresh_keys)
        self.assertFalse(c.is_mock())

        def fake_call(req, timeout=None):
            self.assertEqual(req.get_header("Authorization"), "Bearer minted-token")
            return _Resp(b'{"id": "NEWCMT", "snippet": {"textOriginal": "thanks"}}')

        with patch("integrations.write.platforms.google_oauth.mint_access_token",
                   return_value="minted-token"), \
             patch("integrations.write.youtube_write_transport.urllib.request.urlopen", fake_call):
            r = c.reply_public(self.s, 1, target_ref="CMT_1", text="thanks")
        self.db.commit()
        self.assertEqual(r.state, "sent")


if __name__ == "__main__":
    unittest.main()
