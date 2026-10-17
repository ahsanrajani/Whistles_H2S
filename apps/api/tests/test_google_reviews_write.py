"""Google Business Profile review-reply write transport."""
import io
import unittest
from unittest.mock import patch

import sqlalchemy as sa

from integrations import write
from integrations.write import google_reviews_transport as gr

from ._db import DbTestCase

CREDS = {"GOOGLE_BUSINESS_TOKEN": "gtok"}
REVIEW = "accounts/1/locations/2/reviews/abc"


class BuildRequestTests(unittest.TestCase):
    def test_reply_puts_the_comment_on_the_review_reply(self):
        m, url, body = gr.build_request("reply_public", REVIEW, {"text": "thank you"})
        self.assertEqual((m, url), ("PUT", f"{gr.API}/{REVIEW}/reply"))
        self.assertEqual(body, {"comment": "thank you"})

    def test_delete_reply(self):
        m, url, _b = gr.build_request("delete_reply", REVIEW, {})
        self.assertEqual((m, url), ("DELETE", f"{gr.API}/{REVIEW}/reply"))

    def test_missing_target_raises(self):
        with self.assertRaises(write.WriteError):
            gr.build_request("reply_public", None, {"text": "x"})


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

    def test_live_reply_is_sent_and_keyed_by_the_review_name(self):
        def fake(req, timeout=None):
            self.assertEqual(req.get_method(), "PUT")
            return _Resp(b'{"comment": "thank you", "updateTime": "now"}')

        c = write.GoogleReviewsWriteClient({**CREDS, "GURU_WRITE_LIVE": "1"})
        with patch("integrations.write.google_reviews_transport.urllib.request.urlopen", fake):
            r = c.reply_public(self.s, 1, target_ref=REVIEW, text="thank you")
        self.db.commit()
        self.assertEqual(r.state, "sent")
        self.assertEqual(r.external_id, REVIEW)

    def test_a_400_is_a_rejection_and_lands_in_rework(self):
        import urllib.error
        from db import repositories as repo

        def boom(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 400, "bad", {},
                                         io.BytesIO(b'{"error":{"message":"Reply violates policy"}}'))

        c = write.GoogleReviewsWriteClient({**CREDS, "GURU_WRITE_LIVE": "1"})
        with patch("integrations.write.google_reviews_transport.urllib.request.urlopen", boom):
            r = c.reply_public(self.s, 1, target_ref=REVIEW, text="x")
        self.db.commit()
        self.assertEqual(r.state, "rejected")
        pending = repo.outbound.pending_rework(self.s, 1)
        self.assertEqual(len(pending), 1)
        self.assertIn("policy", pending[0]["error"])

    def test_other_errors_are_failed(self):
        import urllib.error

        def boom(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 401, "no", {},
                                         io.BytesIO(b'{"error":{"message":"bad token"}}'))

        c = write.GoogleReviewsWriteClient({**CREDS, "GURU_WRITE_LIVE": "1"})
        with patch("integrations.write.google_reviews_transport.urllib.request.urlopen", boom):
            r = c.reply_public(self.s, 1, target_ref=REVIEW, text="x")
        self.db.commit()
        self.assertEqual(r.state, "failed")

    def test_dry_run_by_default(self):
        c = write.GoogleReviewsWriteClient(CREDS)
        r = c.reply_public(self.s, 1, target_ref=REVIEW, text="x")
        self.db.commit()
        self.assertEqual(self._row(r.action_id)["state"], "dry_run")

    def test_an_oauth_refresh_triple_is_live_even_without_a_static_token(self):
        refresh_keys = {"GOOGLE_OAUTH2_CLIENT_ID": "cid",
                        "GOOGLE_OAUTH2_CLIENT_SECRET": "sec",
                        "GOOGLE_OAUTH2_REFRESH_TOKEN": "rt", "GURU_WRITE_LIVE": "1"}
        c = write.GoogleReviewsWriteClient(refresh_keys)
        self.assertFalse(c.is_mock())

        def fake_mint(_keys):
            return "minted-token"

        def fake_call(req, timeout=None):
            self.assertEqual(req.get_header("Authorization"), "Bearer minted-token")
            return _Resp(b'{"comment": "thank you"}')

        with patch("integrations.write.platforms.google_oauth.mint_access_token", fake_mint), \
             patch("integrations.write.google_reviews_transport.urllib.request.urlopen", fake_call):
            r = c.reply_public(self.s, 1, target_ref=REVIEW, text="thank you")
        self.db.commit()
        self.assertEqual(r.state, "sent")

    def test_no_static_token_and_no_refresh_triple_stays_mock(self):
        c = write.GoogleReviewsWriteClient({})
        self.assertTrue(c.is_mock())


if __name__ == "__main__":
    unittest.main()
