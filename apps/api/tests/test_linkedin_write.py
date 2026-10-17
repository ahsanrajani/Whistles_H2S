"""LinkedIn write transport for LinkedInWriteClient."""
import io
import json
import unittest
from unittest.mock import patch

import sqlalchemy as sa

from integrations import write
from integrations.write import linkedin_write_transport as lt

from ._db import DbTestCase

ORG = "urn:li:organization:42"
CREDS = {"LINKEDIN_ACCESS_TOKEN": "tok", "LINKEDIN_ORG_URN": ORG}
SHARE = "urn:li:share:777"


class BuildRequestTests(unittest.TestCase):
    def _b(self, action, ref=None, req=None):
        return lt.build_request(action, ref, req or {}, org_urn=ORG)

    def test_publish_posts_with_the_org_as_author(self):
        m, url, body = self._b("publish", req={"text": "hello world"})
        self.assertEqual((m, url), ("POST", f"{lt.REST}/posts"))
        self.assertEqual(body["author"], ORG)
        self.assertEqual(body["commentary"], "hello world")
        self.assertEqual(body["lifecycleState"], "PUBLISHED")

    def test_reply_public_comments_on_the_encoded_share_urn(self):
        m, url, body = self._b("reply_public", SHARE, {"text": "nice"})
        self.assertEqual(m, "POST")
        self.assertIn("urn%3Ali%3Ashare%3A777/comments", url)
        self.assertEqual(body, {"actor": ORG, "message": {"text": "nice"}})

    def test_delete_reply_deletes_the_post(self):
        m, url, _b = self._b("delete_reply", SHARE)
        self.assertEqual(m, "DELETE")
        self.assertIn("/posts/urn%3Ali%3Ashare%3A777", url)

    def test_reply_without_target_raises(self):
        with self.assertRaises(write.WriteError):
            self._b("reply_public", None, {"text": "x"})


class _Resp(io.BytesIO):
    def __init__(self, data=b"{}", headers=None):
        super().__init__(data)
        self.headers = headers or {}

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

    def test_publish_reads_the_created_id_from_the_restli_header(self):
        seen = {}

        def fake(req, timeout=None):
            seen["url"] = req.full_url
            seen["ver"] = req.get_header("Linkedin-version")
            return _Resp(b"{}", {"x-restli-id": "urn:li:share:NEW"})

        c = write.LinkedInWriteClient({**CREDS, "GURU_WRITE_LIVE": "1"})
        with patch("integrations.write.linkedin_write_transport.urllib.request.urlopen", fake):
            r = c.publish(self.s, 1, text="hi")
        self.db.commit()
        self.assertEqual(seen["url"], f"{lt.REST}/posts")
        self.assertEqual(seen["ver"], "202405")
        self.assertEqual(r.state, "sent")
        self.assertEqual(r.external_id, "urn:li:share:NEW")

    def test_api_error_is_failed(self):
        import urllib.error

        def boom(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 403, "no", {},
                                         io.BytesIO(b'{"message":"Not enough permissions"}'))

        c = write.LinkedInWriteClient({**CREDS, "GURU_WRITE_LIVE": "1"})
        with patch("integrations.write.linkedin_write_transport.urllib.request.urlopen", boom):
            r = c.reply_public(self.s, 1, target_ref=SHARE, text="x")
        self.db.commit()
        self.assertEqual(r.state, "failed")
        self.assertIn("Not enough permissions", self._row(r.action_id)["error"])

    def test_dry_run_by_default(self):
        c = write.LinkedInWriteClient(CREDS)
        r = c.publish(self.s, 1, text="x")
        self.db.commit()
        self.assertEqual(self._row(r.action_id)["state"], "dry_run")


if __name__ == "__main__":
    unittest.main()
