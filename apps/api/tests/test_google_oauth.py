"""integrations/google_oauth.py -- refresh-token -> short-lived access token."""
import io
import json
import unittest
from unittest.mock import patch

from integrations import google_oauth


class _Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


class MintAccessTokenTests(unittest.TestCase):
    KEYS = {"GOOGLE_OAUTH2_CLIENT_ID": "cid", "GOOGLE_OAUTH2_CLIENT_SECRET": "secret",
            "GOOGLE_OAUTH2_REFRESH_TOKEN": "rt"}

    def test_missing_creds_raises_without_a_network_call(self):
        with self.assertRaises(google_oauth.OAuthError):
            google_oauth.mint_access_token({})

    def test_happy_path_returns_the_fresh_token(self):
        def fake(req, timeout=None):
            return _Resp(json.dumps({"access_token": "fresh", "expires_in": 3599}).encode())

        with patch("integrations.google_oauth.urllib.request.urlopen", fake):
            out = google_oauth.mint_access_token(self.KEYS)
        self.assertEqual(out, "fresh")

    def test_http_error_becomes_oauth_error(self):
        import urllib.error

        def boom(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 400, "bad", {},
                                         io.BytesIO(b'{"error":"invalid_grant"}'))

        with patch("integrations.google_oauth.urllib.request.urlopen", boom):
            with self.assertRaises(google_oauth.OAuthError):
                google_oauth.mint_access_token(self.KEYS)

    def test_has_refresh_creds(self):
        self.assertTrue(google_oauth.has_refresh_creds(self.KEYS))
        self.assertFalse(google_oauth.has_refresh_creds({}))
        self.assertFalse(google_oauth.has_refresh_creds({"GOOGLE_OAUTH2_CLIENT_ID": "cid"}))


if __name__ == "__main__":
    unittest.main()
