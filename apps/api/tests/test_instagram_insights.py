"""§D.3 — Instagram Insights owned-analytics transport."""
import io
import json
import unittest
from datetime import date
from unittest.mock import patch

from integrations import owned
from integrations.owned import instagram_insights_transport as it

CREDS = {"META_ACCESS_TOKEN": "tok", "META_IG_USER_ID": "IG123"}
DAY = date(2026, 9, 1)


def _insights(**named):
    return {"data": [{"name": n, "period": "day", "values": [{"value": v}]}
                     for n, v in named.items()]}


class MapAccountTests(unittest.TestCase):
    def test_maps_the_ig_account_metrics(self):
        facts = it.map_account(_insights(reach=700, follower_count=5000), DAY)
        by = {(f["entity_type"], f["metric"]): f["value"] for f in facts}
        self.assertEqual(by[("account", "reach")], 700.0)
        self.assertEqual(by[("account", "followers")], 5000.0)
        self.assertTrue(all(f["source"] == "instagram" for f in facts))

    def test_unknown_metric_ignored(self):
        facts = it.map_account(_insights(reach=1, accounts_engaged=9), DAY)
        self.assertEqual({(f["entity_type"], f["metric"]) for f in facts},
                         {("account", "reach")})


class _Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


def _route(account=None, media=None, media_insights=None):
    seen = []

    def fake(req, timeout=None):
        seen.append(req.full_url)
        u = req.full_url
        if "/media?" in u:
            return _Resp(json.dumps({"data": media or []}).encode())
        if "/insights?" in u and "/IG123/" not in u:
            return _Resp(json.dumps(media_insights or {"data": []}).encode())
        return _Resp(json.dumps(account or _insights(reach=42)).encode())

    return fake, seen


class FetchDayTests(unittest.TestCase):
    def test_account_call_shape_and_parse(self):
        fake, seen = _route()
        with patch("integrations.owned.instagram_insights_transport.urllib.request.urlopen", fake):
            facts = it.fetch_day("IG123", DAY, "tok")
        self.assertIn("/IG123/insights?metric=reach", seen[0])
        acct = [f for f in facts if f["entity_type"] == "account"]
        self.assertEqual(next(f for f in acct if f["metric"] == "reach")["value"], 42.0)

    def test_per_media_rows_carry_media_type(self):
        media = [{"id": "M1", "media_type": "REELS"}]
        mi = {"data": [
            {"name": "reach", "values": [{"value": 300}]},
            {"name": "total_interactions", "values": [{"value": 30}]},
        ]}
        fake, _ = _route(media=media, media_insights=mi)
        with patch("integrations.owned.instagram_insights_transport.urllib.request.urlopen", fake):
            facts = it.fetch_day("IG123", DAY, "tok")
        post = {f["metric"]: f for f in facts if f["entity_type"] == "post"}
        self.assertEqual(post["reach"]["value"], 300.0)
        self.assertEqual(post["engagements"]["value"], 30.0)
        self.assertTrue(all(f["dims"] == {"media_type": "reel"}
                            for f in facts if f["entity_type"] == "post"))

    def test_http_error_becomes_owned_analytics_error(self):
        import urllib.error

        def boom(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 400, "Bad", {},
                                        io.BytesIO(b'{"error":{"message":"x"}}'))

        with patch("integrations.owned.instagram_insights_transport.urllib.request.urlopen", boom):
            with self.assertRaises(owned.OwnedAnalyticsError):
                it.fetch_day("IG123", DAY, "tok")


class ProviderTests(unittest.TestCase):
    def test_live_path_calls_the_transport_with_the_ig_id(self):
        p = owned.InstagramInsights({**CREDS, "GURU_WRITE_LIVE": "1"})
        self.assertTrue(p.is_live())
        with patch("integrations.owned.instagram_insights_transport.fetch_day",
                   return_value=[{"source": "instagram"}]) as fd:
            out = p.fetch(1, DAY)
        fd.assert_called_once_with("IG123", DAY, "tok")
        self.assertEqual(out, [{"source": "instagram"}])

    def test_not_live_without_the_flag(self):
        self.assertEqual(owned.InstagramInsights(CREDS).fetch(1, DAY), [])


if __name__ == "__main__":
    unittest.main()
