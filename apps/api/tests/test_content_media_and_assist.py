"""core/content_media.py (real file uploads) + core/content_assist.py (AI
caption/hashtag suggestions). File tests use a temp directory, never the
real static/uploads/; every LLM call is mocked."""
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from core import content_assist, content_media
from integrations.llm import panel

from ._db import DbTestCase


class ContentMediaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self._patch = patch.object(content_media, "UPLOAD_ROOT", self.tmp)
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def test_a_real_image_is_saved_and_a_url_returned(self):
        out = content_media.save(1, filename="pic.jpg", content_type="image/jpeg",
                                 data=b"\xff\xd8\xff fake jpeg bytes")
        self.assertTrue(out["url"].startswith("/uploads/1/"))
        self.assertTrue(out["url"].endswith(".jpg"))
        disk_path = os.path.join(self.tmp, "1", out["url"].rsplit("/", 1)[1])
        self.assertTrue(os.path.isfile(disk_path))
        self.assertEqual(out["size"], len(b"\xff\xd8\xff fake jpeg bytes"))

    def test_an_unsupported_content_type_is_rejected(self):
        with self.assertRaises(content_media.UploadError):
            content_media.save(1, filename="x.exe", content_type="application/x-msdownload",
                               data=b"MZ")

    def test_an_empty_file_is_rejected(self):
        with self.assertRaises(content_media.UploadError):
            content_media.save(1, filename="x.jpg", content_type="image/jpeg", data=b"")

    def test_a_file_over_the_size_cap_is_rejected(self):
        with patch.object(content_media, "MAX_BYTES", 10):
            with self.assertRaises(content_media.UploadError):
                content_media.save(1, filename="x.jpg", content_type="image/jpeg",
                                   data=b"x" * 11)

    def test_two_workspaces_land_in_separate_directories(self):
        out1 = content_media.save(1, filename="a.png", content_type="image/png", data=b"a")
        out2 = content_media.save(2, filename="b.png", content_type="image/png", data=b"b")
        self.assertTrue(out1["url"].startswith("/uploads/1/"))
        self.assertTrue(out2["url"].startswith("/uploads/2/"))


class ContentAssistTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.execute(
            "INSERT INTO brand(id,workspace_id,name,is_focus) VALUES (1,1,'Chase Securities',1)")
        self.db.commit()
        self.s = self.db.session

    def test_neither_topic_nor_draft_raises(self):
        with self.assertRaises(content_assist.ContentAssistError):
            content_assist.suggest(self.s, 1, keys={})

    def test_mock_mode_mentions_the_focus_brand(self):
        out = content_assist.suggest(self.s, 1, topic="a new savings account", keys={})
        self.assertTrue(out["mock"])
        self.assertIn("Chase Securities", out["caption"])
        self.assertTrue(out["hashtags"])

    def test_real_mode_parses_caption_and_hashtags(self):
        with patch.object(panel, "ask", return_value=(
                "openrouter", "anthropic/claude-haiku-4.5",
                "Exciting news! Our new savings account is here.\n"
                "HASHTAGS: #ChaseSecurities #Savings #Pakistan\n")):
            out = content_assist.suggest(self.s, 1, topic="a new savings account",
                                         channel="instagram", keys={"OPENROUTER_API_KEY": "k"})
        self.assertFalse(out["mock"])
        self.assertEqual(out["caption"], "Exciting news! Our new savings account is here.")
        self.assertEqual(out["hashtags"], ["#ChaseSecurities", "#Savings", "#Pakistan"])

    def test_a_failed_llm_call_raises_content_assist_error(self):
        with patch.object(panel, "ask", side_effect=RuntimeError("rate limited")):
            with self.assertRaises(content_assist.ContentAssistError):
                content_assist.suggest(self.s, 1, topic="x", keys={"OPENROUTER_API_KEY": "k"})


if __name__ == "__main__":
    unittest.main()
