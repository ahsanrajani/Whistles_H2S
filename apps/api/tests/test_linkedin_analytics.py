"""§D.3 — LinkedIn organization owned-analytics transport."""
import io
import json
import unittest
from datetime import date
from unittest.mock import patch

from integrations import owned
from integrations.owned import linkedin_analytics_transport as lt

URN = "urn:li:organization:99"
CREDS = {"LINKEDIN_ACCESS_TOKEN": "tok", "LINKEDIN_ORG_URN": URN}
DAY = date(2026, 9, 1)


class MapDayTests(unittest.TestCase):
    def test_maps_stats_and_derives_engagement_rate(self):
        stats = {"impressionCount": 1000, "uniqueImpressionsCount": 850,
                 "likeCount": 20, "commentCount": 5, "shareCount": 3, "clickCount": 12}
        facts = lt.map_day(stats, 4000, DAY)
        by = {f["metric"]: f for f in facts}
        self.assertEqual(by["impressions"]["value"], 1000.0)
        self.assertEqual(by["reach"]["value"], 850.0)
        self.assertEqual(by["engagements"]["value"], 40.0)
        self.assertEqual(by["followers"]["value"], 4000.0)
        self.assertEqual(by["engagement_rate"]["numerator"], 40.0)
        self.assertEqual(by["engagement_rate"]["denominator"], 1000.0)

    def test_missing_impressions_still_reports_engagements_and_followers(self):
        facts = lt.map_day({"likeCount": 2}, 10, DAY)
        self.assertEqual({f["metric"] for f in facts}, {"engagements", "followers"})

    def test_none_stats_is_zero_engagements(self):
        facts = lt.map_day(None, None, DAY)
        self.assertEqual([(f["metric"], f["value"]) for f in facts], [("engagements", 0.0)])


class _Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


class FetchDayTests(unittest.TestCase):
    def test_picks_the_days_interval_and_reads_followers(self):
        start_ms = lt._ms(DAY)
        calls = []

        def fake(req, timeout=None):
            calls.append(req.full_url)
            self.assertEqual(req.get_header("Linkedin-version"), "202405")
            if "organizationalEntityShareStatistics" in req.full_url:
                return _Resp(json.dumps({"elements": [
                    {"timeRange": {"start": start_ms - 86_400_000},
                     "totalShareStatistics": {"impressionCount": 1}},
                    {"timeRange": {"start": start_ms},
                     "totalShareStatistics": {"impressionCount": 500, "likeCount": 10}},
                ]}).encode())
            return _Resp(json.dumps({"firstDegreeSize": 321}).encode())

        with patch("integrations.owned.linkedin_analytics_transport.urllib.request.urlopen", fake):
            facts = lt.fetch_day(URN, DAY, "tok")
        self.assertIn(f"start={start_ms}", calls[0])
        self.assertIn("urn%3Ali%3Aorganization%3A99", calls[0])
        by = {f["metric"]: f["value"] for f in facts}
        self.assertEqual(by["impressions"], 500.0)
        self.assertEqual(by["engagements"], 10.0)
        self.assertEqual(by["followers"], 321.0)

    def test_http_error_becomes_owned_analytics_error(self):
        import urllib.error

        def boom(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 403, "no", {},
                                         io.BytesIO(b'{"message":"ACCESS_DENIED"}'))

        with patch("integrations.owned.linkedin_analytics_transport.urllib.request.urlopen", boom):
            with self.assertRaises(owned.OwnedAnalyticsError):
                lt.fetch_day(URN, DAY, "tok")


class ProviderTests(unittest.TestCase):
    def test_live_path_passes_the_urn_and_version(self):
        p = owned.LinkedInAnalytics({**CREDS, "GURU_WRITE_LIVE": "1",
                                     "LINKEDIN_API_VERSION": "202501"})
        self.assertTrue(p.is_live())
        with patch("integrations.owned.linkedin_analytics_transport.fetch_day",
                   return_value=[{"source": "linkedin"}]) as fd:
            out = p.fetch(1, DAY)
        fd.assert_called_once_with(URN, DAY, "tok", version="202501")
        self.assertEqual(out, [{"source": "linkedin"}])

    def test_dormant_without_creds(self):
        self.assertTrue(owned.LinkedInAnalytics({}).is_mock())
        self.assertEqual(owned.LinkedInAnalytics(CREDS).fetch(1, DAY), [])


if __name__ == "__main__":
    unittest.main()
