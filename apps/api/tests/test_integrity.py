import json
import unittest

from ._db import DbTestCase
from pathlib import Path
from unittest.mock import patch

from core import collector, insights


ROOT = Path(__file__).resolve().parents[1]


class ClientSafetyTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'Bank Alfalah','PK','now')")
        self.db.execute(
            "INSERT INTO brand(id,workspace_id,name,is_focus) VALUES (1,1,'Bank Alfalah',1)")
        for iid, kind, source in ((1, "public", "googlenews_rss"),
                                  (2, "unlicensed", "arctic_shift"),
                                  (3, "noncommercial", "reddit_free")):
            self.db.execute(
                """INSERT INTO item(id,workspace_id,surface,source,source_kind,external_id,
                   url,outlet,title,body,lang_guess,raw_json,collected_at,content_hash)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (iid, 1, "news", source, kind, str(iid), f"https://source/{iid}",
                 "Outlet", f"Item {iid}", "Body", "en", "{}", "now", str(iid)))
            self.db.execute(
                "INSERT INTO mention(id,item_id,brand_id,rule) VALUES (?,?,1,'exact_name')",
                (iid, iid))
        self.db.commit()


    def test_client_insights_exclude_unlicensed_and_noncommercial_items(self):
        sov = insights.share_of_voice(self.db, 1)
        self.assertEqual(sov[0]["n"], 1)
        self.assertEqual(len(insights.feed(self.db, 1)), 1)
        self.assertEqual(insights.top_outlets(self.db, 1), [("Outlet", 1)])

    def test_eligible_language_is_not_claimed_as_scored(self):
        language = insights.language_mix(self.db, 1)[0]
        self.assertTrue(language["eligible"])
        self.assertEqual(language["scored_n"], 0)

    def test_evidence_is_source_traceable_and_client_safe(self):
        rows, total = insights.evidence(self.db, 1)
        self.assertEqual(total, 1)
        self.assertEqual(rows[0][0], 1)
        self.assertEqual(rows[0][11], "https://source/1")

    def test_coverage_hides_unmonitorable_and_unlicensed_surfaces(self):
        statuses = (
            ("news", "collected", 1, 0, "Google News RSS"),
            ("reddit", "collected", 1, 0, "Arctic Shift"),
            ("facebook_public", "unmonitorable", 0, 0, "No API"),
        )
        for surface, state, count, can_estimate, note in statuses:
            self.db.execute(
                """INSERT INTO surface_status
                   (run_id,workspace_id,surface,state,n_sources,estimable,note)
                   VALUES ('run-1',1,?,?,?,?,?)""",
                (surface, state, count, can_estimate, note))
        ledger = insights.surface_ledger(self.db, 1, "run-1")
        self.assertEqual([row["surface"] for row in ledger], ["news", "reddit"])
        reddit = next(row for row in ledger if row["surface"] == "reddit")
        self.assertEqual(reddit["state"], "failed")
        self.assertNotIn("Arctic Shift", reddit["note"])


class AdapterGuardrailTests(unittest.TestCase):
    def test_x_cap_raises_before_an_over_budget_request(self):
        adapter = collector.XRecent(
            {"X_BEARER_TOKEN": "token", "X_MONTHLY_READ_CAP": "4000",
             "_X_MONTHLY_USED": 3950}, lambda _: None, lambda *a, **k: None)
        with self.assertRaises(collector.QuotaExceeded):
            list(adapter.fetch(["Bank Alfalah"]))

    @patch("core.collector.time.sleep", return_value=None)
    @patch("core.collector._get")
    def test_dataforseo_uses_standard_queue(self, get, _sleep):
        get.side_effect = [
            json.dumps({"tasks": [{"id": "task-1"}]}).encode(),
            json.dumps({"tasks": [{"result": [{"keyword": "site:reddit.com Bank Alfalah",
                "items": [{"type": "organic", "url": "https://reddit.com/r/pakistan/1",
                           "domain": "reddit.com", "title": "Bank Alfalah", "description": "post"}]}]}]}).encode(),
        ]
        counts = []
        adapter = collector.DataForSEOSerp(
            {"DATAFORSEO_LOGIN": "user", "DATAFORSEO_PASSWORD": "pass"},
            lambda _: None, lambda *a, **k: counts.append((a, k)))
        rows = list(adapter.fetch(["Bank Alfalah"]))
        self.assertEqual(len(rows), 1)
        self.assertIn("/task_post", get.call_args_list[0].args[0])
        self.assertIn("/task_get/advanced/", get.call_args_list[1].args[0])
        self.assertNotIn("/live/", get.call_args_list[0].args[0])


if __name__ == "__main__":
    unittest.main()
