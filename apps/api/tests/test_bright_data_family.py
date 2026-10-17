"""P2.6 — the Bright Data family is complete.

* Google Maps reviews, LinkedIn, TikTok and Quora are config-only adapters:
  dormant until their dataset id + owned-channel target are set, and returning
  mapped rows against a recorded fixture when they are.
* No orphan comments — a comments adapter with no collected posts yields nothing.
"""
import unittest
from unittest.mock import patch

from core import collector
from core.bright_data import BrightDataResult
from integrations.adapters.brightdata import (BrightDataFacebookComments,
                                              BrightDataGoogleMapsReviews,
                                              BrightDataLinkedIn,
                                              BrightDataQuora, BrightDataTikTok)

_BUDGET = collector._BrightDataBudget(
    records=20, unit_cost=0.0015, used=0, record_cap=100, spend=0.0, dollar_cap=0.10)

_LI_ROWS = [
    {"post_id": "li1", "url": "https://linkedin.com/feed/update/li1",
     "content": "We are hiring across our technology teams this quarter.",
     "user_posted": "Acme Bank", "date_posted": "2026-09-01T09:00:00Z"},
    {"id": "li2", "url": "https://linkedin.com/feed/update/li2",
     "description": "Our quarterly results webinar is next week — register now.",
     "profile_name": "Acme Bank", "timestamp": "2026-09-02T09:00:00Z"},
]
_GMAPS_ROWS = [
    {"review_id": "g1", "review_text": "Staff were quick and the queue was short.",
     "rating": 5, "reviewer_name": "A. Khan", "review_date": "2026-08-30",
     "url": "https://maps.google.com/r/g1"},
]


def _keys(**extra):
    base = {"BRIGHT_DATA_API_KEY": "k"}
    base.update(extra)
    return base


class OwnedChannelAdapterTests(unittest.TestCase):
    def _run(self, cls, keys, rows):
        with patch("core.collector._bright_data_month_budget", return_value=_BUDGET), \
             patch("core.collector.bright_data.BrightDataClient.discover_owned_posts",
                   return_value=BrightDataResult(rows, "snap")):
            adapter = cls(keys, lambda _l: None, lambda *a, **k: None)
            return list(adapter.fetch([]))

    def test_dormant_without_a_dataset_id(self):
        self.assertEqual(
            self._run(BrightDataLinkedIn, _keys(BRIGHT_DATA_LINKEDIN_COMPANY="acme"),
                      _LI_ROWS), [])

    def test_dormant_without_a_target(self):
        self.assertEqual(
            self._run(BrightDataLinkedIn, _keys(BRIGHT_DATA_LINKEDIN_DATASET="gd_abcdef123"),
                      _LI_ROWS), [])

    def test_linkedin_maps_rows_when_configured(self):
        rows = self._run(
            BrightDataLinkedIn,
            _keys(BRIGHT_DATA_LINKEDIN_DATASET="gd_abcdef123",
                  BRIGHT_DATA_LINKEDIN_COMPANY="acme-bank"), _LI_ROWS)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["external_id"], "bd-li-post:li1")
        self.assertEqual(rows[0]["outlet"], "LinkedIn")
        self.assertIn("hiring", rows[0]["body"])
        self.assertEqual(rows[1]["external_id"], "bd-li-post:li2")

    def test_tiktok_and_quora_smoke(self):
        tt = self._run(BrightDataTikTok,
                       _keys(BRIGHT_DATA_TIKTOK_DATASET="gd_tiktok01",
                             BRIGHT_DATA_TIKTOK_USERNAME="acme"),
                       [{"post_id": "t1", "content": "New reel is up on our page today.",
                         "url": "https://tiktok.com/@acme/video/t1"}])
        self.assertEqual(tt[0]["external_id"], "bd-tt-post:t1")
        qr = self._run(BrightDataQuora,
                       _keys(BRIGHT_DATA_QUORA_DATASET="gd_quora001",
                             BRIGHT_DATA_QUORA_PROFILE="acme"),
                       [{"id": "q1", "text": "Answer: our card fees are listed here.",
                         "url": "https://quora.com/q1"}])
        self.assertEqual(qr[0]["external_id"], "bd-qr-post:q1")

    def test_gmaps_reviews_carry_the_rating(self):
        rows = self._run(
            BrightDataGoogleMapsReviews,
            _keys(BRIGHT_DATA_GMAPS_REVIEWS_DATASET="gd_gmaps001",
                  BRIGHT_DATA_GMAPS_PLACE="Acme Bank Gulberg"), _GMAPS_ROWS)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["external_id"], "bd-gmaps-review:g1")
        self.assertEqual(rows[0]["rating"], 5)
        self.assertEqual(rows[0]["author"], "A. Khan")

    def test_over_limit_response_is_a_quota_error(self):
        flood = [{"post_id": f"x{i}", "content": "post"} for i in range(30)]
        with self.assertRaises(collector.QuotaExceeded):
            self._run(BrightDataLinkedIn,
                      _keys(BRIGHT_DATA_LINKEDIN_DATASET="gd_abcdef123",
                            BRIGHT_DATA_LINKEDIN_COMPANY="acme"), flood)


class DiscoverOwnedPostsValidationTests(unittest.TestCase):
    def _client(self):
        from core.bright_data import BrightDataClient
        return BrightDataClient("token")

    def test_rejects_a_bad_dataset_id(self):
        with self.assertRaises(ValueError):
            self._client().discover_owned_posts("not-a-dataset", "acme", 5)

    def test_rejects_an_empty_target(self):
        with self.assertRaises(ValueError):
            self._client().discover_owned_posts("gd_abcdef123", "", 5)

    def test_rejects_a_silly_limit(self):
        with self.assertRaises(ValueError):
            self._client().discover_owned_posts("gd_abcdef123", "acme", 0)


class NoOrphanCommentsTests(unittest.TestCase):
    def test_comments_adapter_yields_nothing_without_collected_posts(self):
        with patch("core.collector._bright_data_month_budget", return_value=_BUDGET):
            adapter = BrightDataFacebookComments(
                {"BRIGHT_DATA_API_KEY": "k", "_BRIGHT_DATA_FACEBOOK_POST_URLS": []},
                lambda _l: None, lambda *a, **k: None)
            self.assertEqual(list(adapter.fetch([])), [])


if __name__ == "__main__":
    unittest.main()
