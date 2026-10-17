import unittest

from ._db import DbTestCase
from pathlib import Path
from unittest.mock import patch

from core import collector, regulatory

ROOT = Path(__file__).resolve().parents[1]

RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel>
  <item><title>SBP imposes monetary penalty for AML/CFT lapses</title>
    <link>https://sbp.example/pr/1</link>
    <description>The State Bank has imposed a fine over KYC deficiencies.</description>
    <pubDate>Mon, 25 Aug 2026 10:00:00 +0500</pubDate></item>
  <item><title>Raast person-to-merchant goes live</title>
    <link>https://sbp.example/pr/2</link>
    <description>Instant payment system expanded for QR payments.</description>
    <pubDate>Tue, 26 Aug 2026 09:00:00 +0500</pubDate></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
  <entry><title>PSX announcement: trading halt lifted</title>
    <link href="https://psx.example/a/9"/>
    <summary>Corporate action and board meeting notice.</summary>
    <updated>2026-08-27T08:00:00Z</updated></entry>
</feed>"""


class RegulatoryAdapterTests(unittest.TestCase):
    def _adapter(self, keys=None):
        return collector.RegulatoryWatch(keys or {}, lambda *_a: None,
                                         lambda *_a, **_k: None)

    def test_parses_rss_items(self):
        with patch("core.collector._get", return_value=RSS):
            adapter = self._adapter()
            adapter.FEEDS = [("SBP", "https://sbp.example/rss")]
            rows = list(adapter.fetch([]))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["outlet"], "SBP")
        self.assertEqual(rows[0]["raw"], {"regulator": "SBP"})
        self.assertEqual(rows[0]["url"], "https://sbp.example/pr/1")
        self.assertTrue(rows[0]["published_at"])

    def test_parses_atom_entries(self):
        with patch("core.collector._get", return_value=ATOM):
            adapter = self._adapter()
            adapter.FEEDS = [("PSX", "https://psx.example/atom")]
            rows = list(adapter.fetch([]))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["url"], "https://psx.example/a/9")
        self.assertEqual(rows[0]["title"], "PSX announcement: trading halt lifted")

    def test_broken_feed_is_skipped_not_fatal(self):
        def flaky(url, **_kw):
            if "bad" in url:
                raise OSError("boom")
            return RSS
        with patch("core.collector._get", side_effect=flaky):
            adapter = self._adapter()
            adapter.FEEDS = [("bad", "https://bad.example/x"),
                             ("SBP", "https://sbp.example/rss")]
            rows = list(adapter.fetch([]))
        self.assertEqual(len(rows), 2)

    def test_extra_feeds_from_keys(self):
        with patch("core.collector._get", return_value=ATOM) as get:
            adapter = self._adapter({"REGULATORY_FEEDS": "Custom|https://x.example/feed"})
            adapter.FEEDS = []
            list(adapter.fetch([]))
        get.assert_called_once_with("https://x.example/feed", timeout=30)


class RegulatoryPipelineTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'Bank Alfalah','PK','now')")
        self.db.execute(
            "INSERT INTO brand(id,workspace_id,name,is_focus) VALUES (1,1,'Bank Alfalah',1)")
        self.db.commit()


    @patch("core.collector.sentiment.score_pending", return_value={})
    @patch("core.collector.REGISTRY", [collector.RegulatoryWatch])
    @patch.object(collector.RegulatoryWatch, "FEEDS",
                  [("SBP", "https://sbp.example/rss")])
    @patch("core.collector._get", return_value=RSS)
    def test_items_land_on_regulatory_surface_with_no_mention(self, _get, _s):
        new = collector.run_collection(self.db, 1, "run-reg", {}, lambda _l: None)
        self.assertEqual(new, 2)
        surfaces = {row[0] for row in self.db.execute("SELECT DISTINCT surface FROM item")}
        self.assertEqual(surfaces, {"regulatory"})
        kinds = {row[0] for row in self.db.execute("SELECT DISTINCT source_kind FROM item")}
        self.assertEqual(kinds, {"public"})
        self.assertEqual(
            self.db.execute("SELECT COUNT(*) FROM mention").fetchone()[0], 0)


class SummarizeTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.execute(
            "INSERT INTO brand(id,workspace_id,name,is_focus) VALUES (1,1,'Bank Alfalah',1)")
        self.db.execute(
            "INSERT INTO brand(id,workspace_id,name,is_focus) VALUES (2,1,'HBL',0)")
        self._iid = 0


    def _notice(self, regulator, title, body, published):
        self._iid += 1
        self.db.execute(
            """INSERT INTO item(id,workspace_id,surface,source,source_kind,external_id,
                                url,outlet,published_at,title,body,raw_json,collected_at,
                                content_hash)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (self._iid, 1, "regulatory", "regulatory_watch", "public", f"r{self._iid}",
             f"https://x/{self._iid}", regulator, published, title, body,
             f'{{"regulator": "{regulator}"}}', "now", f"h{self._iid}"))
        self.db.commit()

    def test_tags_topics_and_named_brands(self):
        self._notice("SBP", "SBP fines a bank over AML lapses",
                     "Monetary penalty imposed on Bank Alfalah for KYC and money laundering "
                     "control deficiencies.", "2026-08-25")
        self._notice("PSX", "Trading halt on a scrip lifted",
                     "Corporate action announcement; board meeting to consider dividend.",
                     "2026-08-20")

        report = regulatory.summarize(self.db, 1)

        self.assertEqual(report["total"], 2)
        self.assertEqual(report["focus_brand"], "Bank Alfalah")
        first = report["notices"][0]                       # newest first
        self.assertEqual(first["regulator"], "SBP")
        self.assertIn("enforcement", first["topics"])
        self.assertIn("aml", first["topics"])
        self.assertEqual(first["brands"], ["Bank Alfalah"])
        self.assertTrue(first["names_focus"])
        self.assertEqual(report["brand_hits"], [{"brand": "Bank Alfalah", "n": 1}])
        by_topic = {t["key"]: t["n"] for t in report["topics"]}
        self.assertEqual(by_topic["enforcement"], 1)
        self.assertEqual(by_topic["markets"], 1)
        self.assertIn("topics", report["policy"])


if __name__ == "__main__":
    unittest.main()
