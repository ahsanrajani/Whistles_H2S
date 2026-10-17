"""§D.3 — Meta Page Insights owned-analytics transport.

``map_account`` is pure; the live path is exercised with a stubbed ``urlopen``.
"""
import io
import json
import unittest
from datetime import date
from unittest.mock import patch

from integrations import owned
from integrations.owned import meta_insights_transport as mt

CREDS = {"META_ACCESS_TOKEN": "tok", "META_PAGE_ID": "PAGE"}
DAY = date(2026, 9, 1)


def _insights(**named):
    return {"data": [{"name": n, "period": "day", "values": [{"value": v, "end_time": "x"}]}
                     for n, v in named.items()]}


class MapAccountTests(unittest.TestCase):
    def test_maps_the_four_metrics(self):
        facts = mt.map_account(_insights(
            page_post_engagements=50, page_follows=12000,
            page_views_total=300, page_actions_post_reactions_total=40), DAY)
        by = {(f["entity_type"], f["metric"]): f for f in facts}
        self.assertEqual(by[("page", "engagements")]["value"], 50.0)
        self.assertEqual(by[("page", "followers")]["value"], 12000.0)
        self.assertEqual(by[("page", "page_views")]["value"], 300.0)
        self.assertEqual(by[("page", "reactions")]["value"], 40.0)
        self.assertTrue(all(f["source"] == "meta" and f["day"] == DAY for f in facts))

    def test_unknown_metrics_ignored_and_missing_values_skipped(self):
        facts = mt.map_account({"data": [
            {"name": "page_post_engagements", "values": [{"value": 10}]},
            {"name": "page_weird_metric", "values": [{"value": 99}]},
            {"name": "page_follows", "values": [{}]},
        ]}, DAY)
        metrics = {(f["entity_type"], f["metric"]) for f in facts}
        self.assertEqual(metrics, {("page", "engagements")})   # no value -> skipped

    def test_empty_payload_is_no_facts(self):
        self.assertEqual(mt.map_account({}, DAY), [])
        self.assertEqual(mt.map_account(None, DAY), [])

    def test_dict_valued_reactions_breakdown_is_summed(self):
        facts = mt.map_account({"data": [
            {"name": "page_actions_post_reactions_total",
             "values": [{"value": {"like": 3, "love": 2}}]},
        ]}, DAY)
        self.assertEqual(facts[0]["value"], 5.0)

    def test_empty_dict_value_skipped(self):
        facts = mt.map_account({"data": [
            {"name": "page_actions_post_reactions_total", "values": [{"value": {}}]},
        ]}, DAY)
        self.assertEqual(facts, [])


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _route(account=None, posts=None, post_insights=None):
    """A urlopen stub that answers by URL: the page-token exchange, account
    insights, the posts list, then per-post insights."""
    seen = []

    def fake(req, timeout=None):
        seen.append(req.full_url)
        u = req.full_url
        if "/me/accounts" in u:
            return _Resp(json.dumps(
                {"data": [{"id": "PAGE", "access_token": "page-tok"}]}).encode())
        if "/posts?" in u:
            return _Resp(json.dumps({"data": posts or []}).encode())
        if "/insights?" in u and "/PAGE/" not in u:
            return _Resp(json.dumps(post_insights or {"data": []}).encode())
        return _Resp(json.dumps(account or _insights(page_post_engagements=5)).encode())

    return fake, seen


class FetchDayTests(unittest.TestCase):
    def test_account_call_shape_and_parse(self):
        fake, seen = _route(account=_insights(page_post_engagements=5))
        with patch("integrations.owned.meta_insights_transport.urllib.request.urlopen", fake):
            facts = mt.fetch_day("PAGE", DAY, "tok")
        insights_call = next(u for u in seen if "/PAGE/insights?metric=" in u)
        self.assertIn("page_post_engagements", insights_call)
        self.assertIn("since=", insights_call)
        acct = [f for f in facts if f["entity_type"] == "page"]
        self.assertEqual(next(f for f in acct if f["metric"] == "engagements")["value"], 5.0)

    def test_per_post_rows_carry_media_type_and_reactions(self):
        posts = [{"id": "P1", "attachments": {"data": [{"media_type": "video"}]}}]
        pi = {"data": [
            {"name": "post_clicks", "values": [{"value": 200}]},
            {"name": "post_video_views", "values": [{"value": 20}]},
            {"name": "post_reactions_by_type_total", "values": [{"value": {"like": 8, "love": 2}}]},
        ]}
        fake, _ = _route(posts=posts, post_insights=pi)
        with patch("integrations.owned.meta_insights_transport.urllib.request.urlopen", fake):
            facts = mt.fetch_day("PAGE", DAY, "tok")
        post = {f["metric"]: f for f in facts if f["entity_type"] == "post"}
        self.assertEqual(post["clicks"]["value"], 200.0)
        self.assertEqual(post["video_views"]["value"], 20.0)
        self.assertEqual(post["reactions"]["value"], 10.0)
        self.assertTrue(all(f["dims"] == {"media_type": "video"}
                            for f in facts if f["entity_type"] == "post"))

    def test_one_bad_post_does_not_sink_the_day(self):
        import urllib.error
        posts = [{"id": "P1"}, {"id": "P2"}]

        def fake(req, timeout=None):
            u = req.full_url
            if "/me/accounts" in u:
                return _Resp(json.dumps(
                    {"data": [{"id": "PAGE", "access_token": "page-tok"}]}).encode())
            if "/posts?" in u:
                return _Resp(json.dumps({"data": posts}).encode())
            if "/P1/insights" in u:
                raise urllib.error.HTTPError(u, 400, "Bad", {},
                                             io.BytesIO(b'{"error":{"message":"gone"}}'))
            if "/P2/insights" in u:
                return _Resp(json.dumps(
                    {"data": [{"name": "post_clicks", "values": [{"value": 9}]}]}).encode())
            return _Resp(json.dumps(_insights(page_post_engagements=1)).encode())

        with patch("integrations.owned.meta_insights_transport.urllib.request.urlopen", fake):
            facts = mt.fetch_day("PAGE", DAY, "tok")
        refs = {f["entity_ref"] for f in facts if f["entity_type"] == "post"}
        self.assertEqual(refs, {"P2"})

    def test_http_error_on_the_account_call_becomes_owned_analytics_error(self):
        import urllib.error

        def boom(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 400, "Bad", {},
                                        io.BytesIO(b'{"error":{"message":"bad metric"}}'))

        with patch("integrations.owned.meta_insights_transport.urllib.request.urlopen", boom):
            with self.assertRaises(owned.OwnedAnalyticsError):
                mt.fetch_day("PAGE", DAY, "tok")


class ProviderLiveTests(unittest.TestCase):
    def test_not_live_without_the_flag_even_with_creds(self):
        p = owned.MetaInsights(CREDS)
        self.assertFalse(p.is_mock())
        self.assertFalse(p.is_live())
        self.assertEqual(p.fetch(1, DAY), [])

    def test_live_path_calls_the_transport(self):
        p = owned.MetaInsights({**CREDS, "GURU_WRITE_LIVE": "1"})
        self.assertTrue(p.is_live())
        with patch("integrations.owned.meta_insights_transport.fetch_day",
                   return_value=[{"source": "meta", "metric": "impressions"}]) as fd:
            out = p.fetch(1, DAY)
        fd.assert_called_once_with("PAGE", DAY, "tok")
        self.assertEqual(out, [{"source": "meta", "metric": "impressions"}])

    def test_mock_mode_still_wins_without_creds(self):
        p = owned.MetaInsights({"GURU_WRITE_LIVE": "1"})
        self.assertTrue(p.is_mock())
        self.assertTrue(len(p.fetch(1, DAY)) > 0)


if __name__ == "__main__":
    unittest.main()
