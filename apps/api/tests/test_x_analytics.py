"""§D.3 — X owned-analytics transport."""
import io
import json
import unittest
from datetime import date
from unittest.mock import patch

from integrations import owned
from integrations.owned import x_analytics_transport as xt

CREDS = {"X_BEARER_TOKEN": "bear", "X_OWNED_HANDLE": "acme"}
DAY = date(2026, 9, 1)


def _account(facts):
    return {f["metric"]: f for f in facts if f["entity_type"] == "account"}


class MapDayTests(unittest.TestCase):
    def test_followers_plus_aggregated_engagements_and_impressions(self):
        tweets = [
            {"id": "1", "public_metrics": {"retweet_count": 2, "reply_count": 1,
                                           "like_count": 10, "quote_count": 0,
                                           "impression_count": 500}},
            {"id": "2", "public_metrics": {"retweet_count": 0, "reply_count": 0,
                                           "like_count": 5, "quote_count": 1,
                                           "impression_count": 200}},
        ]
        by = _account(xt.map_day({"followers_count": 3000}, tweets, DAY))
        self.assertEqual(by["followers"]["value"], 3000.0)
        self.assertEqual(by["engagements"]["value"], 2 + 1 + 10 + 0 + 0 + 0 + 5 + 1)
        self.assertEqual(by["impressions"]["value"], 700.0)
        self.assertEqual(by["engagement_rate"]["numerator"], 19.0)
        self.assertEqual(by["engagement_rate"]["denominator"], 700.0)

    def test_per_tweet_post_rows_carry_a_media_type_dim(self):
        tweets = [{"id": "t1", "attachments": {"media_keys": ["m1"]},
                   "public_metrics": {"like_count": 4, "retweet_count": 1,
                                      "reply_count": 0, "quote_count": 0,
                                      "impression_count": 100}}]
        posts = [f for f in xt.map_day({}, tweets, DAY, {"m1": "video"})
                 if f["entity_type"] == "post"]
        self.assertEqual({f["metric"] for f in posts},
                         {"engagements", "reactions", "impressions", "engagement_rate"})
        self.assertTrue(all(f["dims"] == {"media_type": "video"} for f in posts))
        self.assertTrue(all(f["entity_ref"] == "t1" for f in posts))

    def test_impressions_omitted_when_the_token_cannot_see_them(self):
        tweets = [{"id": "1", "public_metrics": {"like_count": 4, "retweet_count": 1,
                                                 "reply_count": 0, "quote_count": 0}}]
        metrics = {f["metric"] for f in xt.map_day({"followers_count": 10}, tweets, DAY)
                   if f["entity_type"] == "account"}
        self.assertEqual(metrics, {"followers", "engagements"})   # no impressions/rate

    def test_no_tweets_still_reports_followers_and_zero_engagements(self):
        by = {f["metric"]: f["value"] for f in xt.map_day({"followers_count": 42}, [], DAY)}
        self.assertEqual(by, {"followers": 42.0, "engagements": 0.0})


class _Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


class FetchDayTests(unittest.TestCase):
    def test_resolves_the_handle_then_pulls_that_days_tweets(self):
        calls = []

        def fake(req, timeout=None):
            calls.append(req.full_url)
            if "by/username/acme" in req.full_url:
                return _Resp(json.dumps({"data": {"id": "77", "public_metrics": {"followers_count": 9}}}).encode())
            return _Resp(json.dumps({"data": [{"public_metrics": {"like_count": 3, "retweet_count": 0, "reply_count": 0, "quote_count": 0}}]}).encode())

        with patch("integrations.owned.x_analytics_transport.urllib.request.urlopen", fake):
            facts = xt.fetch_day("@acme", DAY, "bear")
        self.assertTrue(calls[0].endswith("by/username/acme?user.fields=public_metrics"))
        self.assertIn("/users/77/tweets?", calls[1])
        self.assertIn("start_time=2026-09-01T00:00:00Z", calls[1])
        by = {f["metric"]: f["value"] for f in facts}
        self.assertEqual(by["followers"], 9.0)
        self.assertEqual(by["engagements"], 3.0)

    def test_api_error_becomes_owned_analytics_error(self):
        import urllib.error

        def boom(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 401, "no", {},
                                         io.BytesIO(b'{"title":"Unauthorized"}'))

        with patch("integrations.owned.x_analytics_transport.urllib.request.urlopen", boom):
            with self.assertRaises(owned.OwnedAnalyticsError):
                xt.fetch_day("acme", DAY, "bear")


class ProviderTests(unittest.TestCase):
    def test_live_path(self):
        p = owned.XAnalytics({**CREDS, "GURU_WRITE_LIVE": "1"})
        self.assertTrue(p.is_live())
        with patch("integrations.owned.x_analytics_transport.fetch_day",
                   return_value=[{"source": "x"}]) as fd:
            out = p.fetch(1, DAY)
        fd.assert_called_once_with("acme", DAY, "bear")
        self.assertEqual(out, [{"source": "x"}])

    def test_needs_both_a_token_and_a_handle(self):
        self.assertTrue(owned.XAnalytics({"X_BEARER_TOKEN": "b"}).is_mock())
        self.assertFalse(owned.XAnalytics(CREDS).is_mock())


if __name__ == "__main__":
    unittest.main()
