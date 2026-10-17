"""core/seo_report.py -- real DataForSEO keyword ranking + backlink summary
per tracked brand's domain. Every HTTP call mocked; nothing hits the network."""
import json
import unittest
from unittest.mock import patch

import sqlalchemy as sa

from core import collector, seo_report  # noqa: F401 -- import order, see test_web_backfill.py

from ._db import DbTestCase

BRANDS = [{"id": 1, "name": "Chase Securities", "is_focus": True, "domain": "chasesecurities.com"},
         {"id": 2, "name": "AKD Securities", "is_focus": False, "domain": "akdsl.com"},
         {"id": 3, "name": "JS Global", "is_focus": False, "domain": None}]

RANKED_KEYWORDS_OK = json.dumps({"tasks": [{"result": [{"items": [
    {"keyword_data": {"keyword": "chase bank", "keyword_info": {"search_volume": 22200}},
     "ranked_serp_element": {"serp_item": {"rank_absolute": 17,
                             "url": "https://chasesecurities.com/x"}}},
]}]}]})
BACKLINKS_OK = json.dumps({"tasks": [{"result": [
    {"backlinks": 500, "referring_domains": 40, "referring_main_domains": 35, "rank": 210},
]}]})


class RunTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.commit()
        self.s = self.db.session
        self.keys = {"DATAFORSEO_LOGIN": "u", "DATAFORSEO_PASSWORD": "p"}

    def test_a_brand_with_no_domain_is_skipped_not_guessed(self):
        logs = []
        with patch.object(collector, "_get", return_value=RANKED_KEYWORDS_OK):
            out = seo_report.run(self.s, 1, self.keys, [BRANDS[2]], log=logs.append)
        self.assertEqual(out["keywords_pulled"], 0)
        self.assertTrue(any("no domain known" in ln for ln in logs))

    def test_real_keyword_and_backlink_rows_are_written(self):
        calls = iter([RANKED_KEYWORDS_OK, BACKLINKS_OK])
        with patch.object(collector, "_get", side_effect=lambda *a, **k: next(calls)):
            out = seo_report.run(self.s, 1, self.keys, [BRANDS[0]])
        self.db.commit()
        self.assertEqual(out["keywords_pulled"], 1)
        self.assertEqual(out["backlinks_pulled"], 1)
        row = self.s.execute(sa.text(
            "SELECT value FROM metric_fact WHERE workspace_id=1 AND entity_type='keyword' "
            "AND entity_ref='chase bank'")).scalar()
        self.assertEqual(row, 17)

    def test_an_api_failure_for_one_brand_does_not_stop_the_others(self):
        def boom(*a, **k):
            raise RuntimeError("timeout")
        with patch.object(collector, "_get", side_effect=boom):
            out = seo_report.run(self.s, 1, self.keys, [BRANDS[0]])
        self.assertEqual(len(out["errors"]), 2)   # keywords + backlinks both fail
        self.assertEqual(out["facts_written"], 0)


class ResolveDomainsTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.execute(
            "INSERT INTO brand(id,workspace_id,name,is_focus) VALUES "
            "(1,1,'Chase Securities',1), (2,1,'AKD Securities',0)")
        self.db.commit()
        self.s = self.db.session

    def test_focus_domain_comes_from_brand_domains_key(self):
        out = seo_report.resolve_domains(self.s, 1, {"BRAND_DOMAINS": "chasesecurities.com"})
        focus = next(b for b in out if b["is_focus"])
        self.assertEqual(focus["domain"], "chasesecurities.com")

    def test_competitor_domain_comes_from_real_serp_attribution(self):
        self.s.execute(sa.text("""
            INSERT INTO item(id,workspace_id,surface,source,source_kind,external_id,
                             url,outlet,raw_json,collected_at,content_hash)
            VALUES (1,1,'web','dataforseo_brand_serp','licensed','e1',
                   'https://www.akdsecurities.com/','www.akdsecurities.com',:raw,'now','e1')
        """), {"raw": '{"rank":1}'})
        self.db.commit()
        out = seo_report.resolve_domains(self.s, 1, {})
        akd = next(b for b in out if b["name"] == "AKD Securities")
        self.assertEqual(akd["domain"], "www.akdsecurities.com")

    def test_a_focus_brand_with_no_brand_domains_key_is_never_guessed(self):
        """The focus brand's domain is what actually gets crawled and billed
        for -- a wrong guess there means running a paid crawl against
        someone else's site and showing it as the client's own (real risk,
        live-verified 2026-09-12). Unlike a competitor, it must never fall
        back to the SERP-attribution heuristic, even when that heuristic
        would otherwise find a plausible-looking hit."""
        self.s.execute(sa.text("""
            INSERT INTO item(id,workspace_id,surface,source,source_kind,external_id,
                             url,outlet,raw_json,collected_at,content_hash)
            VALUES (1,1,'web','dataforseo_brand_serp','licensed','e1',
                   'https://chasesecurities.com/','chasesecurities.com',:raw,'now','e1')
        """), {"raw": '{"rank":1}'})
        self.db.commit()
        out = seo_report.resolve_domains(self.s, 1, {})
        focus = next(b for b in out if b["is_focus"])
        self.assertIsNone(focus["domain"])

    def test_a_brand_with_no_known_domain_resolves_to_none(self):
        out = seo_report.resolve_domains(self.s, 1, {})
        akd = next(b for b in out if b["name"] == "AKD Securities")
        self.assertIsNone(akd["domain"])


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
        out = seo_report.report(self.s, 1)
        self.assertEqual(out, {"day": None, "brands": []})

    def test_report_groups_keywords_and_backlinks_by_brand(self):
        calls = iter([RANKED_KEYWORDS_OK, BACKLINKS_OK])
        with patch.object(collector, "_get", side_effect=lambda *a, **k: next(calls)):
            seo_report.run(self.s, 1, {"DATAFORSEO_LOGIN": "u", "DATAFORSEO_PASSWORD": "p"},
                           [BRANDS[0]])
        self.db.commit()
        out = seo_report.report(self.s, 1)
        self.assertEqual(len(out["brands"]), 1)
        b = out["brands"][0]
        self.assertEqual(b["name"], "Chase Securities")
        self.assertTrue(b["is_focus"])
        self.assertEqual(b["keywords"][0]["keyword"], "chase bank")
        self.assertEqual(b["keywords"][0]["rank"], 17)
        self.assertEqual(b["backlinks"]["referring_domains"], 40)


if __name__ == "__main__":
    unittest.main()
