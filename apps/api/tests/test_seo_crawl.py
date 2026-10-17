"""core/seo_crawl.py -- real DataForSEO on-page crawl + Lighthouse Core Web
Vitals per brand's domain. Every HTTP call and time.sleep mocked."""
import json
import unittest
from unittest.mock import patch

import sqlalchemy as sa

from core import collector, seo_crawl  # noqa: F401 -- import order, see test_web_backfill.py

from ._db import DbTestCase

BRANDS = [{"id": 1, "name": "Chase Securities", "is_focus": True, "domain": "chasesecurities.com"},
         {"id": 2, "name": "JS Global", "is_focus": False, "domain": None}]

CRAWL_POST = json.dumps({"tasks": [{"id": "task-1"}]})
CRAWL_FINISHED = json.dumps({"tasks": [{"result": [{
    "crawl_progress": "finished",
    "domain_info": {"crawl_status": {"pages_crawled": 30}, "total_pages": 30},
    "page_metrics": {"onpage_score": 92.1, "broken_links": 0, "duplicate_content": 0,
                     "duplicate_title": 0, "duplicate_description": 0,
                     "checks": {"no_description": 1, "no_h1_tag": 2, "title_too_long": 1}},
}]}]})
CRAWL_IN_PROGRESS = json.dumps({"tasks": [{"result": [{"crawl_progress": "in_progress"}]}]})

LH_POST = json.dumps({"tasks": [{"id": "lh-task-1"}]})
LH_DONE = json.dumps({"tasks": [{"status_code": 20000, "result": [{
    "categories": {"performance": {"score": 0.51}, "accessibility": {"score": 0.77},
                  "best-practices": {"score": 0.92}, "seo": {"score": 0.92}},
    "audits": {"largest-contentful-paint": {"numericValue": 8170.5},
              "cumulative-layout-shift": {"numericValue": 0},
              "total-blocking-time": {"numericValue": 269.5}},
}]}]})
LH_PENDING = json.dumps({"tasks": [{"status_code": 40602, "status_message": "Task in progress"}]})

PAGES_OK = json.dumps({"tasks": [{"status_code": 20000, "result": [{"items": [
    {"url": "https://chasesecurities.com/about", "status_code": 200},
    {"url": "https://chasesecurities.com/contact", "status_code": 200},
]}]}]})
PAGES_TASK_EXPIRED = json.dumps({"tasks": [
    {"status_code": 40501, "status_message": "Invalid Field: 'id'."}]})


class RunTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.commit()
        self.s = self.db.session
        self.keys = {"DATAFORSEO_LOGIN": "u", "DATAFORSEO_PASSWORD": "p"}

    def test_a_brand_with_no_domain_is_skipped(self):
        logs = []
        with patch.object(seo_crawl.time, "sleep"):
            out = seo_crawl.run(self.s, 1, self.keys, [BRANDS[1]], log=logs.append)
        self.assertEqual(out, {"sites_crawled": 0, "cwv_measured": 0, "facts_written": 0,
                               "errors": [], "day": out["day"]})
        self.assertTrue(any("no domain known" in ln for ln in logs))

    def test_a_finished_crawl_and_lighthouse_run_write_real_facts(self):
        calls = iter([CRAWL_POST, CRAWL_FINISHED, LH_POST, LH_DONE])
        with patch.object(seo_crawl.time, "sleep"), \
             patch.object(collector, "_get", side_effect=lambda *a, **k: next(calls)):
            out = seo_crawl.run(self.s, 1, self.keys, [BRANDS[0]])
        self.db.commit()
        self.assertEqual(out["sites_crawled"], 1)
        self.assertEqual(out["cwv_measured"], 1)
        self.assertEqual(out["errors"], [])

        score = self.s.execute(sa.text(
            "SELECT value FROM metric_fact WHERE workspace_id=1 AND entity_type='site_crawl' "
            "AND metric='onpage_score'")).scalar()
        self.assertEqual(score, 92.1)
        lcp = self.s.execute(sa.text(
            "SELECT value FROM metric_fact WHERE workspace_id=1 "
            "AND entity_type='core_web_vitals' AND metric='lcp_ms'")).scalar()
        self.assertEqual(lcp, 8170.5)

    def test_a_crawl_that_never_finishes_is_a_clean_error_not_a_hang(self):
        calls = iter([CRAWL_POST] + [CRAWL_IN_PROGRESS] * 100)
        with patch.object(seo_crawl, "_CRAWL_MAX_WAIT", 10), \
             patch.object(seo_crawl.time, "sleep"), \
             patch.object(collector, "_get", side_effect=lambda *a, **k: next(calls)), \
             patch.object(seo_crawl, "_lighthouse", return_value=None):
            out = seo_crawl.run(self.s, 1, self.keys, [BRANDS[0]])
        self.assertEqual(out["sites_crawled"], 0)
        self.assertTrue(any("timed out" in e for e in out["errors"]))


class PagesForCheckTests(unittest.TestCase):
    def setUp(self):
        self.keys = {"DATAFORSEO_LOGIN": "u", "DATAFORSEO_PASSWORD": "p"}

    def test_returns_the_real_page_list_for_a_check(self):
        with patch.object(collector, "_get", return_value=PAGES_OK):
            out = seo_crawl.pages_for_check("task-1", "no_h1_tag", self.keys)
        self.assertEqual(out, [
            {"url": "https://chasesecurities.com/about", "status_code": 200},
            {"url": "https://chasesecurities.com/contact", "status_code": 200},
        ])

    def test_a_non_20000_status_raises_instead_of_returning_empty(self):
        with patch.object(collector, "_get", return_value=PAGES_TASK_EXPIRED):
            with self.assertRaises(RuntimeError):
                seo_crawl.pages_for_check("stale-task", "no_h1_tag", self.keys)

    def test_a_page_metrics_only_check_is_rejected_before_the_call(self):
        with patch.object(collector, "_get") as mocked:
            for check in ("duplicate_title", "duplicate_description",
                         "duplicate_content", "broken_links"):
                with self.assertRaises(ValueError):
                    seo_crawl.pages_for_check("task-1", check, self.keys)
            mocked.assert_not_called()


class ReportTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.execute(
            "INSERT INTO brand(id,workspace_id,name,is_focus) VALUES (1,1,'Chase Securities',1)")
        self.db.commit()
        self.s = self.db.session

    def test_no_run_yet_returns_an_empty_report(self):
        self.assertEqual(seo_crawl.report(self.s, 1), {"day": None, "brands": []})

    def test_report_groups_crawl_and_cwv_by_brand(self):
        calls = iter([CRAWL_POST, CRAWL_FINISHED, LH_POST, LH_DONE])
        with patch.object(seo_crawl.time, "sleep"), \
             patch.object(collector, "_get", side_effect=lambda *a, **k: next(calls)):
            seo_crawl.run(self.s, 1, {"DATAFORSEO_LOGIN": "u", "DATAFORSEO_PASSWORD": "p"},
                          [BRANDS[0]])
        self.db.commit()
        out = seo_crawl.report(self.s, 1)
        b = out["brands"][0]
        self.assertEqual(b["name"], "Chase Securities")
        self.assertEqual(b["onpage_score"], 92.1)
        self.assertEqual(b["pages_crawled"], 30)
        self.assertEqual(b["checks"]["no_h1_tag"], 2)
        self.assertEqual(b["cwv"]["lcp_ms"], 8170.5)
        self.assertEqual(b["scores"]["performance"], 51.0)
        self.assertEqual(b["task_id"], "task-1")


if __name__ == "__main__":
    unittest.main()
