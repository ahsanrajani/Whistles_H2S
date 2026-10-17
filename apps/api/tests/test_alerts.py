import unittest

from ._db import DbTestCase
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core import alerts

ROOT = Path(__file__).resolve().parents[1]


def _day(offset):
    return (datetime.now(timezone.utc) - timedelta(days=offset)).strftime("%Y-%m-%dT09:00:00Z")


class ConfigTests(unittest.TestCase):
    def test_merges_over_defaults_and_ignores_junk(self):
        merged = alerts._config('{"triage_critical": 4, "bogus": 9, "switch_high": "x"}')
        self.assertEqual(merged["triage_critical"], 4)
        self.assertEqual(merged["switch_high"], alerts.DEFAULT_CONFIG["switch_high"])
        self.assertNotIn("bogus", merged)

    def test_bad_json_falls_back_to_defaults(self):
        self.assertEqual(alerts._config("not json{"), alerts.DEFAULT_CONFIG)


class DispatchTests(unittest.TestCase):
    def _evaluation(self, firing=1):
        rows = [{"key": "k", "severity": "critical", "title": "T", "detail": "d",
                 "value": 3, "threshold": 1, "fired": True, "href": "/triage"}][:firing]
        return {"firing": rows, "counts": {"rules": 1, "firing": firing,
                                           "critical": firing, "warning": 0}}

    def test_sends_to_each_configured_channel(self):
        calls = []
        result = alerts.dispatch(self._evaluation(), slack_url="https://slack",
                                 webhook_url="https://hook",
                                 poster=lambda url, payload: calls.append((url, payload)))
        self.assertEqual(result["sent"], ["slack", "webhook"])
        self.assertEqual([url for url, _p in calls], ["https://slack", "https://hook"])
        self.assertIn("text", calls[0][1])

    def test_one_bad_channel_does_not_block_the_other(self):
        def poster(url, _payload):
            if "slack" in url:
                raise OSError("nope")
        result = alerts.dispatch(self._evaluation(), slack_url="https://slack",
                                 webhook_url="https://hook", poster=poster)
        self.assertEqual(result["sent"], ["webhook"])
        self.assertEqual(result["errors"][0]["channel"], "slack")

    def test_no_urls_no_send(self):
        result = alerts.dispatch(self._evaluation(0), poster=lambda *_a: self.fail())
        self.assertEqual(result["sent"], [])
        self.assertIn("no alerts firing", result["text"].lower())


class EvaluateTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.execute(
            "INSERT INTO brand(id,workspace_id,name,is_focus) VALUES (1,1,'Focus Bank',1)")
        self._iid = self._mid = 0


    def _complaint(self, body, *, category="complaint", sentiment="neg"):
        self._iid += 1
        self._mid += 1
        self.db.execute(
            """INSERT INTO item(id,workspace_id,surface,source,source_kind,external_id,
                                url,published_at,body,raw_json,collected_at,content_hash)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (self._iid, 1, "x", "x_recent", "licensed", f"e{self._iid}",
             f"https://x/{self._iid}", _day(1), body, "{}", "now", f"h{self._iid}"))
        self.db.execute(
            "INSERT INTO mention(id,item_id,brand_id,rule) VALUES (?,?,1,'x_search')",
            (self._mid, self._iid))
        if sentiment:
            self.db.execute(
                """INSERT INTO sentiment(mention_id,label,model_id,scored_lang,scored_at)
                   VALUES (?,?,?,?,?)""", (self._mid, sentiment, "lexicon", "en", "now"))
        if category:
            self.db.execute(
                """INSERT INTO mention_class(mention_id,category,model_id,classified_at)
                   VALUES (?,?,?,?)""", (self._mid, category, "rules", "now"))
        self.db.commit()

    def test_empty_workspace_fires_nothing(self):
        report = alerts.evaluate(self.db, 1)
        self.assertEqual(report["counts"]["firing"], 0)
        self.assertTrue(all(not a["fired"] for a in report["alerts"]))
        self.assertEqual(report["counts"]["rules"], len(report["alerts"]))
        self.assertEqual(report["config"], alerts.DEFAULT_CONFIG)

    def test_a_critical_complaint_fires_the_triage_rule(self):
        self._complaint("Account blocked for a week now, complaint number 5, "
                        "escalating to the Banking Mohtasib and my lawyer. "
                        "Unauthorized transaction, money deducted.", category="fraud")

        report = alerts.evaluate(self.db, 1)
        by_key = {a["key"]: a for a in report["alerts"]}
        self.assertTrue(by_key["triage_critical"]["fired"])
        self.assertGreaterEqual(by_key["triage_critical"]["value"], 1)
        self.assertEqual(by_key["triage_critical"]["severity"], "critical")
        self.assertIn(by_key["triage_critical"], report["firing"])
        self.assertGreaterEqual(report["counts"]["critical"], 1)
        # a rule with no data stays quiet
        self.assertFalse(by_key["incident_firing"]["fired"])

    def test_config_override_raises_the_bar(self):
        for _ in range(2):
            self._complaint("worst bank, closing my account, unresolved for weeks, "
                            "account blocked, no response", category="complaint")
        strict = alerts.evaluate(self.db, 1, {"triage_high": 999})
        by_key = {a["key"]: a for a in strict["alerts"]}
        self.assertEqual(by_key["triage_high"]["threshold"], 999)
        self.assertFalse(by_key["triage_high"]["fired"])


if __name__ == "__main__":
    unittest.main()
