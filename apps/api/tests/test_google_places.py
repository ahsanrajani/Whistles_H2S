"""google_places_reviews -- Google Places API (First Gen) Place Details reviews."""
import json
import unittest
from unittest.mock import patch

from core import collector, sources  # noqa: F401 -- import order, see test_web_backfill.py
from integrations.adapters import GooglePlacesReviews


class GooglePlacesReviewsTests(unittest.TestCase):
    def _adapter(self):
        return GooglePlacesReviews(
            {"GOOGLE_PLACES_API_KEY": "gk", "GOOGLE_PLACE_ID": "abc123"},
            lambda *_: None, lambda *_a, **_k: None)

    def test_yields_each_review_with_a_stable_unique_id(self):
        payload = {"status": "OK", "result": {
            "url": "https://maps.google.com/?cid=1",
            "reviews": [
                {"time": 1000, "author_name": "A", "rating": 1,
                 "text": "Terrible service at the branch.",
                 "relative_time_description": "a week ago"},
                {"time": 2000, "author_name": "B", "rating": 5,
                 "text": "Great experience."},
            ]}}
        with patch.object(collector, "_get", return_value=json.dumps(payload)):
            out = list(self._adapter().fetch([]))
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["external_id"], "gplace:1000")
        self.assertEqual(out[1]["external_id"], "gplace:2000")
        self.assertTrue(out[0]["url"].endswith("#review-1000"))
        self.assertEqual(out[0]["rating"], 1)
        self.assertEqual(out[0]["published_at"], "1970-01-01T00:16:40+00:00")

    def test_a_non_ok_status_yields_nothing_and_logs(self):
        payload = {"status": "NOT_FOUND"}
        logs = []
        with patch.object(collector, "_get", return_value=json.dumps(payload)):
            a = GooglePlacesReviews({"GOOGLE_PLACES_API_KEY": "gk", "GOOGLE_PLACE_ID": "x"},
                                    logs.append, lambda *_a, **_k: None)
            out = list(a.fetch([]))
        self.assertEqual(out, [])
        self.assertTrue(any("NOT_FOUND" in ln for ln in logs))

    def test_a_request_failure_yields_nothing_and_logs(self):
        logs = []
        with patch.object(collector, "_get", side_effect=RuntimeError("timeout")):
            a = GooglePlacesReviews({"GOOGLE_PLACES_API_KEY": "gk", "GOOGLE_PLACE_ID": "x"},
                                    logs.append, lambda *_a, **_k: None)
            out = list(a.fetch([]))
        self.assertEqual(out, [])
        self.assertTrue(any("failed" in ln for ln in logs))

    def test_registered_with_needs_and_official_source_class(self):
        meta = sources.SOURCES["google_places_reviews"]
        self.assertEqual(meta["needs"], ["GOOGLE_PLACES_API_KEY", "GOOGLE_PLACE_ID"])
        self.assertEqual(meta["source_class"], "official")


if __name__ == "__main__":
    unittest.main()
