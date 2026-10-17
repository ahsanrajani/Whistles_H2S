"""Bright Data SERP adapters — X / Reddit keyword discovery."""
import json
import unittest
from unittest.mock import patch

from core import collector
from integrations.adapters import BrightDataSerpReddit, BrightDataSerpX

KEYS = {"BRIGHT_DATA_API_KEY": "k", "BRIGHT_DATA_SERP_ZONE": "serp1"}

_SERP = json.dumps({"organic": [
    {"link": "https://x.com/acme/status/1", "title": "Acme rocks",
     "description": "great service", "rank": 1},
    {"link": "https://twitter.com/someone/status/2", "title": "meh", "rank": 2},
    {"link": "https://reddit.com/r/pk/comments/3/acme/", "title": "Acme on reddit",
     "description": "thread", "rank": 3},
    {"link": "https://example.com/blog", "title": "off surface", "rank": 4},
]})


def _adapter(cls, keys=KEYS):
    calls = []
    return cls(dict(keys), lambda m: None, lambda *a, **k: calls.append((a, k))), calls


class SurfaceFilterTests(unittest.TestCase):
    def test_x_adapter_keeps_only_x_and_twitter_links(self):
        a, _ = _adapter(BrightDataSerpX)
        with patch.object(collector, "_get", return_value=_SERP):
            items = list(a.fetch(["Acme"]))
        urls = [i["url"] for i in items]
        self.assertEqual(urls, ["https://x.com/acme/status/1",
                                "https://twitter.com/someone/status/2"])
        self.assertEqual(items[0]["title"], "Acme rocks")
        self.assertIn("great service", items[0]["body"])
        self.assertEqual(items[0]["external_id"], collector._h(urls[0]))
        self.assertEqual(items[0]["outlet"], "x.com")
        self.assertEqual(items[0]["raw"]["via"], "brightdata_serp")

    def test_reddit_adapter_keeps_only_reddit_links(self):
        a, _ = _adapter(BrightDataSerpReddit)
        with patch.object(collector, "_get", return_value=_SERP):
            items = list(a.fetch(["Acme"]))
        self.assertEqual([i["url"] for i in items],
                         ["https://reddit.com/r/pk/comments/3/acme/"])

    def test_query_is_a_site_scoped_google_search_with_brd_json(self):
        a, _ = _adapter(BrightDataSerpX)
        seen = {}

        def fake_get(url, timeout=45, headers=None, data=None):
            seen["url"] = url
            seen["headers"] = headers
            seen["body"] = json.loads(data)
            return "{}"

        with patch.object(collector, "_get", fake_get):
            list(a.fetch(["Chase Securities"]))
        self.assertEqual(seen["url"], "https://api.brightdata.com/request")
        self.assertEqual(seen["headers"]["Authorization"], "Bearer k")
        self.assertEqual(seen["body"]["zone"], "serp1")
        self.assertIn("brd_json=1", seen["body"]["url"])
        self.assertIn("site%3Ax.com+OR+site%3Atwitter.com+Chase+Securities",
                      seen["body"]["url"])

    def test_double_encoded_json_is_handled(self):
        a, _ = _adapter(BrightDataSerpX)
        with patch.object(collector, "_get", return_value=json.dumps(_SERP)):
            items = list(a.fetch(["Acme"]))
        self.assertEqual(len(items), 2)


class GuardTests(unittest.TestCase):
    def test_no_zone_means_no_calls(self):
        a, _ = _adapter(BrightDataSerpX, {"BRIGHT_DATA_API_KEY": "k"})
        with patch.object(collector, "_get") as g:
            self.assertEqual(list(a.fetch(["Acme"])), [])
        g.assert_not_called()

    def test_needs_lists_the_zone(self):
        from core import sources
        self.assertIn("BRIGHT_DATA_SERP_ZONE",
                      sources.SOURCES["brightdata_serp_x"]["needs"])
        self.assertEqual(sources.SOURCES["brightdata_serp_reddit"]["surface"], "reddit")

    def test_a_failed_serp_call_is_counted_and_skipped(self):
        a, calls = _adapter(BrightDataSerpX)

        def boom(*a, **k):
            raise RuntimeError("502")

        with patch.object(collector, "_get", boom):
            self.assertEqual(list(a.fetch(["Acme"])), [])
        self.assertTrue(any(kw.get("ok") is False for _args, kw in calls))


if __name__ == "__main__":
    unittest.main()
