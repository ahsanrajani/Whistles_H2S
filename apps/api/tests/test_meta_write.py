"""§D.2 — Meta Graph write transport.

``build_request`` is pure; the live HTTP path is exercised with a stubbed
``urlopen`` so no call leaves the process.
"""
import contextlib
import io
import json
import unittest
from unittest.mock import patch

import sqlalchemy as sa

from integrations import write
from integrations.write import meta_transport as mt

from ._db import DbTestCase

CREDS = {"META_ACCESS_TOKEN": "tok", "META_PAGE_ID": "PAGE", "META_IG_USER_ID": "IG"}


class BuildRequestTests(unittest.TestCase):
    def _b(self, action, ref, req=None):
        return mt.build_request(action, ref, req or {}, page_id="PAGE", ig_user_id="IG")

    def test_reply_public_comments_on_the_target_on_facebook(self):
        m, url, body = self._b("reply_public", "12_34", {"text": "hi"})
        self.assertEqual((m, url), ("POST", f"{mt.GRAPH}/12_34/comments"))
        self.assertEqual(body, {"message": "hi"})

    def test_reply_public_uses_the_replies_edge_on_instagram(self):
        _m, url, _b = self._b("reply_public", "999", {"text": "hi", "channel": "instagram"})
        self.assertEqual(url, f"{mt.GRAPH}/999/replies")

    def test_reply_dm_is_a_private_reply(self):
        m, url, body = self._b("reply_dm", "12_34", {"text": "sorry"})
        self.assertEqual((m, url), ("POST", f"{mt.GRAPH}/12_34/private_replies"))
        self.assertEqual(body, {"message": "sorry"})

    def test_delete_reply_hides_by_default_and_can_delete_or_unhide(self):
        self.assertEqual(self._b("delete_reply", "c1")[2], {"is_hidden": True})
        self.assertEqual(self._b("delete_reply", "c1", {"mode": "delete"})[:2],
                         ("DELETE", f"{mt.GRAPH}/c1"))
        self.assertEqual(self._b("delete_reply", "c1", {"mode": "unhide"})[2],
                         {"is_hidden": False})

    def test_block_and_unblock_hit_the_page_blocked_edge(self):
        self.assertEqual(self._b("block", "user9")[:2], ("POST", f"{mt.GRAPH}/PAGE/blocked"))
        self.assertEqual(self._b("unblock", "user9")[:2],
                         ("DELETE", f"{mt.GRAPH}/PAGE/blocked"))

    def test_publish_posts_to_the_page_feed(self):
        m, url, body = self._b("publish", None, {"text": "gm", "link": "https://x.y"})
        self.assertEqual((m, url), ("POST", f"{mt.GRAPH}/PAGE/feed"))
        self.assertEqual(body, {"message": "gm", "link": "https://x.y"})

    def test_schedule_sends_an_epoch_and_published_false(self):
        import datetime as dt
        want = int(dt.datetime(2026, 9, 10, 10, 0, tzinfo=dt.timezone.utc).timestamp())
        _m, _u, body = self._b("schedule", None,
                               {"text": "later", "at": "2026-09-10T10:00:00Z"})
        self.assertIs(body["published"], False)
        self.assertEqual(body["scheduled_publish_time"], want)

    def test_missing_target_ref_raises(self):
        with self.assertRaises(write.WriteError):
            self._b("reply_public", None, {"text": "hi"})

    def test_instagram_publish_is_unsupported(self):
        with self.assertRaises(write.WriteError):
            self._b("publish", None, {"text": "x", "channel": "instagram"})


class BuildInstagramLoginDmTests(unittest.TestCase):
    """The Instagram-Login route's DM send -- graph.instagram.com, no
    Page-token exchange (integrations/write/platforms.py picks this branch
    over build_request when INSTAGRAM_LOGIN_ACCESS_TOKEN is configured)."""

    def test_hits_the_ig_native_host_with_the_ig_user_id(self):
        m, url, body = mt.build_instagram_login_dm(
            "17800000000000001", {"text": "hi there"}, ig_user_id="17841403122141569")
        self.assertEqual(m, "POST")
        self.assertEqual(url, f"{mt.IG_GRAPH}/17841403122141569/messages")
        self.assertEqual(body, {"recipient": {"id": "17800000000000001"},
                                "message": {"text": "hi there"}})

    def test_missing_ig_user_id_raises(self):
        with self.assertRaises(write.WriteError):
            mt.build_instagram_login_dm("psid", {"text": "hi"}, ig_user_id=None)

    def test_missing_target_ref_raises(self):
        with self.assertRaises(write.WriteError):
            mt.build_instagram_login_dm(None, {"text": "hi"}, ig_user_id="IG")


class ResolvePageTokenTests(unittest.TestCase):
    """The pure helper in isolation, no write client involved."""

    def test_missing_creds_raises(self):
        with self.assertRaises(write.WriteError):
            mt.resolve_page_token({})

    def test_returns_the_matching_pages_token(self):
        def fake(req, timeout=None):
            self.assertIn("me/accounts", req.full_url)
            self.assertIn("access_token=tok", req.full_url)
            return _FakeResp(json.dumps({"data": [
                {"id": "OTHER", "access_token": "nope"},
                {"id": "PAGE", "access_token": "page-tok"},
            ]}).encode())

        with patch("integrations.write.meta_transport.urllib.request.urlopen", fake):
            self.assertEqual(mt.resolve_page_token(CREDS), "page-tok")

    def test_page_id_not_among_the_accounts_raises(self):
        def fake(req, timeout=None):
            return _FakeResp(b'{"data": []}')

        with patch("integrations.write.meta_transport.urllib.request.urlopen", fake):
            with self.assertRaises(write.WriteError):
                mt.resolve_page_token(CREDS)


class _FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class LiveTransportTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.commit()
        self.s = self.db.session

    def _row(self, aid):
        return self.s.execute(sa.text(
            "SELECT state, external_id, response, error FROM outbound_action WHERE id=:i"),
            {"i": aid}).mappings().first()

    def _fake_urlopen(self, seen, *, action_body=b'{"id": "PAGE_888"}'):
        """A live write is now two Graph round-trips -- resolve_page_token's
        GET to /me/accounts, then the actual action -- dispatched here by URL
        exactly like the real host would see two different requests."""
        def fake_urlopen(req, timeout=None):
            if "/me/accounts" in req.full_url:
                # resolve_page_token (like dm_sync._page_token) passes the
                # token as a query param on this one GET, not a Bearer header.
                seen["page_token_url"] = req.full_url
                return _FakeResp(b'{"data": [{"id": "PAGE", "access_token": "page-tok"}]}')
            seen["url"] = req.full_url
            seen["method"] = req.get_method()
            seen["auth"] = req.get_header("Authorization")
            seen["body"] = json.loads(req.data)
            return _FakeResp(action_body)
        return fake_urlopen

    def test_live_reply_posts_to_graph_and_records_the_id(self):
        seen = {}
        c = write.MetaWriteClient({**CREDS, "GURU_WRITE_LIVE": "1"})
        self.assertTrue(c.is_live())
        with patch("integrations.write.meta_transport.urllib.request.urlopen",
                   self._fake_urlopen(seen)):
            result = c.reply_public(self.s, 1, target_ref="12_34", text="on it")
        self.db.commit()

        # resolved a real page-scoped token off the stored user token first...
        self.assertIn("access_token=tok", seen["page_token_url"])
        # ...and the actual write used THAT token, not the raw user one --
        # root cause of Chase C-116's replies never delivering (2026-09-11).
        self.assertEqual(seen["url"], f"{mt.GRAPH}/12_34/comments")
        self.assertEqual(seen["method"], "POST")
        self.assertEqual(seen["auth"], "Bearer page-tok")
        self.assertEqual(seen["body"], {"message": "on it"})
        self.assertEqual(result.state, "sent")
        self.assertTrue(result.ok)
        self.assertEqual(result.external_id, "PAGE_888")
        self.assertEqual(self._row(result.action_id)["state"], "sent")

    def test_a_graph_error_is_recorded_as_failed(self):
        import urllib.error

        def boom(req, timeout=None):
            if "/me/accounts" in req.full_url:
                return _FakeResp(b'{"data": [{"id": "PAGE", "access_token": "page-tok"}]}')
            raise urllib.error.HTTPError(
                req.full_url, 400, "Bad Request", {},
                io.BytesIO(b'{"error": {"code": 190, "message": "Invalid OAuth token"}}'))

        c = write.MetaWriteClient({**CREDS, "GURU_WRITE_LIVE": "1"})
        with patch("integrations.write.meta_transport.urllib.request.urlopen", boom):
            result = c.reply_public(self.s, 1, target_ref="12_34", text="x")
        self.db.commit()
        self.assertEqual(result.state, "failed")
        self.assertIn("190", self._row(result.action_id)["error"])
        self.assertIn("Invalid OAuth token", self._row(result.action_id)["error"])

    def test_reply_dm_to_a_messenger_conversation_uses_the_send_api(self):
        """The other half of the C-116 bug: a real DM conversation (not a
        public-comment private-reply) needs the Send API, not
        /{comment}/private_replies -- covered at build_request level in
        BuildRequestTests; this proves the live client wires it end-to-end
        with the page token."""
        seen = {}
        c = write.MetaWriteClient({**CREDS, "GURU_WRITE_LIVE": "1"})
        with patch("integrations.write.meta_transport.urllib.request.urlopen",
                   self._fake_urlopen(seen, action_body=b'{"message_id": "mid.123"}')):
            result = c.reply_dm(self.s, 1, target_ref="psid_1",
                                text="hi", channel="messenger")
        self.db.commit()
        self.assertEqual(seen["url"], f"{mt.GRAPH}/PAGE/messages")
        self.assertEqual(seen["auth"], "Bearer page-tok")
        self.assertEqual(seen["body"],
                         {"recipient": {"id": "psid_1"}, "message": {"text": "hi"},
                          "messaging_type": "RESPONSE"})
        self.assertEqual(result.state, "sent")
        # Root-caused 2026-09-12 (C-117): "id"/"post_id" don't exist on a
        # Send API response, only "message_id" -- this was silently None.
        self.assertEqual(result.external_id, "mid.123")

    def test_instagram_dm_prefers_the_instagram_login_route_when_configured(self):
        """No /me/accounts round-trip at all -- the Instagram-Login token is
        already scoped to the IG account, unlike the shared Page token."""
        seen = {}

        def fake_urlopen(req, timeout=None):
            self.assertNotIn("me/accounts", req.full_url)
            seen["url"] = req.full_url
            seen["auth"] = req.get_header("Authorization")
            seen["body"] = json.loads(req.data)
            return _FakeResp(b'{"message_id": "ig_mid.456"}')

        c = write.MetaWriteClient({**CREDS, "INSTAGRAM_LOGIN_ACCESS_TOKEN": "ig-login-tok",
                                   "GURU_WRITE_LIVE": "1"})
        with patch("integrations.write.meta_transport.urllib.request.urlopen", fake_urlopen):
            result = c.reply_dm(self.s, 1, target_ref="ig_psid_1",
                                text="hi", channel="instagram_dm")
        self.db.commit()
        self.assertEqual(seen["url"], f"{mt.IG_GRAPH}/IG/messages")
        self.assertEqual(seen["auth"], "Bearer ig-login-tok")
        self.assertEqual(seen["body"], {"recipient": {"id": "ig_psid_1"},
                                        "message": {"text": "hi"}})
        self.assertEqual(result.state, "sent")
        self.assertEqual(result.external_id, "ig_mid.456")

    def test_instagram_dm_falls_back_to_page_token_route_without_the_new_credential(self):
        """Unchanged behaviour for workspaces without INSTAGRAM_LOGIN_ACCESS_TOKEN."""
        seen = {}
        c = write.MetaWriteClient({**CREDS, "GURU_WRITE_LIVE": "1"})
        with patch("integrations.write.meta_transport.urllib.request.urlopen",
                   self._fake_urlopen(seen, action_body=b'{"message_id": "mid.789"}')):
            result = c.reply_dm(self.s, 1, target_ref="ig_psid_1",
                                text="hi", channel="instagram_dm")
        self.db.commit()
        self.assertEqual(seen["url"], f"{mt.GRAPH}/IG/messages")
        self.assertEqual(seen["auth"], "Bearer page-tok")
        self.assertEqual(result.state, "sent")

    def test_page_token_resolution_failure_is_recorded_as_failed_not_raised(self):
        """META_PAGE_ID not among /me/accounts' pages (wrong id, token
        missing manage_pages, ...) must be a clean failed outbound_action,
        not an unhandled exception."""
        def no_matching_page(req, timeout=None):
            return _FakeResp(b'{"data": [{"id": "OTHER_PAGE", "access_token": "x"}]}')

        c = write.MetaWriteClient({**CREDS, "GURU_WRITE_LIVE": "1"})
        with patch("integrations.write.meta_transport.urllib.request.urlopen",
                   no_matching_page):
            result = c.reply_public(self.s, 1, target_ref="12_34", text="x")
        self.db.commit()
        self.assertEqual(result.state, "failed")
        self.assertIn("no page-scoped token", self._row(result.action_id)["error"])

    def test_dry_run_log_names_the_real_endpoint(self):
        c = write.MetaWriteClient(CREDS)                      # creds, no live flag
        self.assertFalse(c.is_live())
        result = c.reply_public(self.s, 1, target_ref="12_34", text="x")
        self.db.commit()
        row = self._row(result.action_id)
        self.assertEqual(row["state"], "dry_run")
        self.assertEqual(row["response"]["endpoint"],
                         f"POST {mt.GRAPH}/12_34/comments")


if __name__ == "__main__":
    unittest.main()
