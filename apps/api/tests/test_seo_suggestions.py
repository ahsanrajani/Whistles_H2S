"""core/seo_suggestions.py -- LLM-generated SEO recommendations, grounded
only in the real crawl/keyword/backlink/search-visibility facts already on
file. Every LLM call mocked; nothing hits the network."""
import json
import unittest
from unittest.mock import patch

import sqlalchemy as sa

from core import collector, seo_crawl, seo_report, seo_suggestions  # noqa: F401
from integrations.llm import panel

from ._db import DbTestCase

RANKED_KEYWORDS_OK = json.dumps({"tasks": [{"result": [{"items": [
    {"keyword_data": {"keyword": "chase bank", "keyword_info": {"search_volume": 22200}},
     "ranked_serp_element": {"serp_item": {"rank_absolute": 17,
                             "url": "https://chasesecurities.com/x"}}},
]}]}]})


class ParseTests(unittest.TestCase):
    def test_parses_priority_lines(self):
        text = (
            "HIGH: Fix the missing H1 tag on the homepage.\n"
            "some preamble the model added anyway\n"
            "MEDIUM: Add alt text to product images.\n"
            "- LOW: Consider a shorter title tag.\n"
        )
        out = seo_suggestions._parse(text)
        self.assertEqual(len(out), 3)
        self.assertEqual(out[0], {"priority": "HIGH", "text": "Fix the missing H1 tag on the homepage."})
        self.assertEqual(out[2]["priority"], "LOW")

    def test_no_matching_lines_returns_empty(self):
        self.assertEqual(seo_suggestions._parse("just prose, no priority tags"), [])


class GenerateTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.execute(
            "INSERT INTO brand(id,workspace_id,name,is_focus) VALUES (1,1,'Chase Securities',1)")
        self.db.commit()
        self.s = self.db.session
        self.keys = {"OPENROUTER_API_KEY": "k"}

    def test_raises_when_no_seo_data_on_file_yet(self):
        with self.assertRaises(seo_suggestions.NoSeoDataError):
            seo_suggestions.generate(self.s, 1, self.keys)

    def _seed_keywords(self):
        with patch.object(collector, "_get", return_value=RANKED_KEYWORDS_OK):
            seo_report.run(self.s, 1, {"DATAFORSEO_LOGIN": "u", "DATAFORSEO_PASSWORD": "p"},
                           [{"id": 1, "name": "Chase Securities", "is_focus": True,
                             "domain": "chasesecurities.com"}])
        self.db.commit()

    def test_generate_grounds_the_prompt_in_real_facts_and_records_the_result(self):
        self._seed_keywords()
        with patch.object(panel, "ask", return_value=(
                "openrouter", "anthropic/claude-haiku-4.5",
                "HIGH: Target 'chase bank' more directly, it already ranks #17.\n"
                "MEDIUM: Build more backlinks.\n")):
            row = seo_suggestions.generate(self.s, 1, self.keys)
        self.db.commit()
        self.assertIsNone(row["error"])
        self.assertEqual(len(row["suggestions"]), 2)
        self.assertIn("chase bank", row["prompt"])   # grounded in the real keyword fact

        latest = seo_suggestions.latest(self.s, 1)
        self.assertEqual(latest["id"], row["id"])

    def test_a_failed_llm_call_is_recorded_not_raised(self):
        self._seed_keywords()
        with patch.object(panel, "ask", side_effect=RuntimeError("openrouter 429: rate limited")):
            row = seo_suggestions.generate(self.s, 1, self.keys)
        self.db.commit()
        self.assertIn("rate limited", row["error"])
        self.assertEqual(row["suggestions"], [])

    def test_workspaces_are_isolated(self):
        self._seed_keywords()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (2,'WS2','PK','now')")
        self.db.commit()
        self.assertIsNone(seo_suggestions.latest(self.s, 2))


if __name__ == "__main__":
    unittest.main()
