"""X v2 write transport for XWriteClient."""
import io
import json
import unittest
from unittest.mock import patch

import sqlalchemy as sa

from integrations import write
from integrations.write import x_transport as xt

from ._db import DbTestCase

CREDS = {"X_WRITE_TOKEN": "utok"}


class BuildRequestTests(unittest.TestCase):
    def _b(self, action, ref=None, req=None, src=None):
        return xt.build_request(action, ref, req or {}, source_user_id=src)

    def test_publish_and_reply(self):
        self.assertEqual(self._b("publish", req={"text": "hi"}),
                         ("POST", f"{xt.API}/tweets", {"text": "hi"}))
        m, url, body = self._b("reply_public", "12345", {"text": "yo"})
        self.assertEqual((m, url), ("POST", f"{xt.API}/tweets"))
        self.assertEqual(body, {"text": "yo", "reply": {"in_reply_to_tweet_id": "12345"}})

    def test_reply_dm_strips_the_prefix(self):
        m, url, _b = self._b("reply_dm", "dm:99", {"text": "sorry"})
        self.assertEqual((m, url), ("POST", f"{xt.API}/dm_conversations/with/99/messages"))

    def test_delete(self):
        self.assertEqual(self._b("delete_reply", "77")[:2], ("DELETE", f"{xt.API}/tweets/77"))

    def test_block_and_unblock_need_the_source_id(self):
        with self.assertRaises(write.WriteError):
            self._b("block", "u2")
        self.assertEqual(self._b("block", "u2", src="me1")[:2],
                         ("POST", f"{xt.API}/users/me1/blocking"))
        self.assertEqual(self._b("unblock", "u2", src="me1")[:2],
                         ("DELETE", f"{xt.API}/users/me1/blocking/u2"))

    def test_missing_target_raises(self):
        with self.assertRaises(write.WriteError):
            self._b("reply_public", None, {"text": "x"})


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

    def test_live_reply_posts_a_tweet_and_records_the_id(self):
        seen = {}

        def fake(req, timeout=None):
            seen["url"] = req.full_url
            seen["auth"] = req.get_header("Authorization")
            seen["body"] = json.loads(req.data)
            return _Resp(b'{"data": {"id": "T99", "text": "yo"}}')

        c = write.XWriteClient({**CREDS, "GURU_WRITE_LIVE": "1"})
        self.assertTrue(c.is_live())
        with patch("integrations.write.x_transport.urllib.request.urlopen", fake):
            r = c.reply_public(self.s, 1, target_ref="12345", text="yo")
        self.db.commit()
        self.assertEqual(seen["url"], f"{xt.API}/tweets")
        self.assertEqual(seen["auth"], "Bearer utok")
        self.assertEqual(seen["body"]["reply"], {"in_reply_to_tweet_id": "12345"})
        self.assertEqual(r.state, "sent")
        self.assertEqual(r.external_id, "T99")

    def test_api_error_is_failed(self):
        import urllib.error

        def boom(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 403, "no", {},
                                         io.BytesIO(b'{"detail":"Not permitted"}'))

        c = write.XWriteClient({**CREDS, "GURU_WRITE_LIVE": "1"})
        with patch("integrations.write.x_transport.urllib.request.urlopen", boom):
            r = c.reply_public(self.s, 1, target_ref="1", text="x")
        self.db.commit()
        self.assertEqual(r.state, "failed")
        self.assertIn("Not permitted", self._row(r.action_id)["error"])

    def test_dry_run_records_the_endpoint(self):
        c = write.XWriteClient(CREDS)                          # no live flag
        r = c.reply_public(self.s, 1, target_ref="1", text="x")
        self.db.commit()
        row = self._row(r.action_id)
        self.assertEqual(row["state"], "dry_run")

    def test_block_resolves_me_when_no_owned_id(self):
        calls = []

        def fake(req, timeout=None):
            calls.append((req.get_method(), req.full_url))
            if req.full_url.endswith("/users/me"):
                return _Resp(b'{"data": {"id": "ME"}}')
            return _Resp(b'{"data": {"blocking": true}}')

        c = write.XWriteClient({**CREDS, "GURU_WRITE_LIVE": "1"})
        with patch("integrations.write.x_transport.urllib.request.urlopen", fake):
            r = c.block(self.s, 1, target_ref="u2")
        self.db.commit()
        self.assertEqual(r.state, "sent")
        self.assertEqual(calls[0], ("GET", f"{xt.API}/users/me"))
        self.assertEqual(calls[1], ("POST", f"{xt.API}/users/ME/blocking"))


if __name__ == "__main__":
    unittest.main()
