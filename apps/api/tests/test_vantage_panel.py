"""core/vantage_panel.py -- the Vantage AI-visibility panel's domain logic."""
import json
import unittest
from datetime import date
from unittest.mock import patch

import sqlalchemy as sa

from core import vantage_panel
from db.repositories import llm_panel
from integrations import llm

from ._db import DbTestCase

DAY = date(2026, 9, 10)


def _brand(name, is_focus, safe):
    return {"name": name, "is_focus": is_focus,
            "safe": json.dumps([safe]), "gated": json.dumps({}),
            "context": json.dumps([]), "exclude": json.dumps([])}


class VantagePanelTestCase(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.commit()
        self.s = self.db.session
        for b in (_brand("Chase Securities", 1, r"\bchase\s*securities\b"),
                 _brand("AKD Securities", 0, r"\bakd\s*securities\b"),
                 _brand("JS Global", 0, r"\bjs\s*global\b")):
            self.s.execute(sa.text(
                "INSERT INTO brand(workspace_id,name,is_focus,safe_patterns,"
                "gated_patterns,context_patterns,exclude_patterns) "
                "VALUES (1,:name,:is_focus,:safe,:gated,:context,:exclude)"), b)
        self.db.commit()


class StarterPromptTests(VantagePanelTestCase):
    def test_starter_prompts_mention_the_focus_brand(self):
        prompts = vantage_panel.starter_prompts("Chase Securities", ["AKD Securities"])
        self.assertGreaterEqual(len(prompts), 4)
        self.assertTrue(all("Chase Securities" in p for p in prompts))

    def test_ensure_starter_prompts_seeds_once(self):
        added = vantage_panel.ensure_starter_prompts(self.s, 1)
        self.db.commit()
        self.assertGreater(added, 0)
        self.assertEqual(llm_panel.count(self.s, 1), added)
        again = vantage_panel.ensure_starter_prompts(self.s, 1)
        self.assertEqual(again, 0)
        self.assertEqual(llm_panel.count(self.s, 1), added)   # unchanged

    def test_no_focus_brand_seeds_nothing(self):
        self.s.execute(sa.text("DELETE FROM brand WHERE workspace_id=1"))
        self.db.commit()
        self.assertEqual(vantage_panel.ensure_starter_prompts(self.s, 1), 0)


class RunTests(VantagePanelTestCase):
    def setUp(self):
        super().setUp()
        self.pid = llm_panel.add_prompt(self.s, 1, "What do you know about Chase Securities?")
        self.db.commit()

    def test_a_mentioning_answer_is_recorded_with_its_brand_hit(self):
        with patch.object(llm, "ask",
                          return_value=("google", "gemini-3.5-flash",
                                       "Chase Securities is a brokerage in Pakistan.")):
            out = vantage_panel.run(self.s, 1, {}, day=DAY)
        self.db.commit()
        self.assertEqual(out["asked"], len(llm.PANEL))
        self.assertEqual(out["failed"], 0)
        rows = llm_panel.responses(self.s, 1)
        self.assertEqual(len(rows), len(llm.PANEL))
        self.assertTrue(all(r["mentions"] for r in rows))
        self.assertTrue(all(m["is_focus"] for r in rows for m in r["mentions"]))

    def test_a_model_failure_is_recorded_as_an_error_row(self):
        with patch.object(llm, "ask", side_effect=llm.LlmError("quota exceeded")):
            out = vantage_panel.run(self.s, 1, {}, day=DAY)
        self.db.commit()
        self.assertEqual(out["failed"], len(llm.PANEL))
        rows = llm_panel.responses(self.s, 1)
        self.assertTrue(all(r["error"] for r in rows))

    def test_an_answer_with_no_brand_names_records_no_mentions(self):
        with patch.object(llm, "ask",
                          return_value=("google", "gemini-3.5-flash", "I have no idea.")):
            vantage_panel.run(self.s, 1, {}, day=DAY)
        self.db.commit()
        rows = llm_panel.responses(self.s, 1)
        self.assertTrue(all(r["mentions"] == [] for r in rows))


class InsightsTests(VantagePanelTestCase):
    def setUp(self):
        super().setUp()
        self.pid = llm_panel.add_prompt(self.s, 1, "compare firms")
        self.db.commit()

    def _seed(self, mentions):
        llm_panel.record_response(self.s, 1, self.pid, provider="google",
                                  model="gemini", day=DAY, response_text="x",
                                  mentions=mentions)

    def test_wilson_scored_mention_rate_per_brand(self):
        focus = [{"brand_id": 1, "name": "Chase Securities", "is_focus": True,
                 "rule": "exact_name", "excluded": False}]
        for _ in range(3):
            self._seed(focus)
        self._seed([])                                    # one non-mentioning response
        self.db.commit()
        out = vantage_panel.insights(self.s, 1)
        self.assertEqual(out["total_responses"], 4)
        chase = next(b for b in out["brands"] if b["name"] == "Chase Securities")
        self.assertEqual(chase["k"], 3)
        self.assertEqual(chase["n"], 4)
        self.assertAlmostEqual(chase["rate"], 0.75)
        self.assertLess(chase["wilson"][0], chase["rate"])
        self.assertGreater(chase["wilson"][1], chase["rate"])

    def test_a_competitor_only_answer_is_a_visibility_gap(self):
        self._seed([{"brand_id": 2, "name": "AKD Securities", "is_focus": False,
                    "rule": "exact_name", "excluded": False}])
        self.db.commit()
        out = vantage_panel.insights(self.s, 1)
        self.assertEqual(len(out["visibility_gaps"]), 1)
        self.assertEqual(out["visibility_gaps"][0]["competitors_named"], ["AKD Securities"])

    def test_a_focus_mention_is_never_a_gap_even_alongside_a_competitor(self):
        self._seed([
            {"brand_id": 1, "name": "Chase Securities", "is_focus": True,
             "rule": "exact_name", "excluded": False},
            {"brand_id": 2, "name": "AKD Securities", "is_focus": False,
             "rule": "exact_name", "excluded": False},
        ])
        self.db.commit()
        out = vantage_panel.insights(self.s, 1)
        self.assertEqual(out["visibility_gaps"], [])

    def test_error_rows_are_excluded_from_the_denominator(self):
        llm_panel.record_error(self.s, 1, self.pid, model="gemini", day=DAY, error="boom")
        self.db.commit()
        out = vantage_panel.insights(self.s, 1)
        self.assertEqual(out["total_responses"], 0)
        self.assertEqual(out["failed_calls"], 1)

    def test_a_focus_hit_confused_with_jpmorgan_chase_is_not_counted_as_a_mention(self):
        focus = [{"brand_id": 1, "name": "Chase Securities", "is_focus": True,
                 "rule": "exact_name", "excluded": False}]
        self._seed(focus)                                     # real, uncontested mention
        llm_panel.record_response(
            self.s, 1, self.pid, provider="openrouter", model="gpt-4o-mini", day=DAY,
            response_text=("Chase Securities, as part of JPMorgan Chase & Co., is a "
                           "reputable institution."), mentions=focus)
        self.db.commit()
        out = vantage_panel.insights(self.s, 1)
        chase = next(b for b in out["brands"] if b["name"] == "Chase Securities")
        self.assertEqual(chase["k"], 1)                        # the confused one excluded
        self.assertEqual(chase["n"], 2)
        self.assertEqual(out["confused_responses"], 1)

    def test_an_uncertain_response_is_counted_even_without_any_mention(self):
        llm_panel.record_response(
            self.s, 1, self.pid, provider="openrouter", model="llama-3.1", day=DAY,
            response_text="I don't have access to a search engine to answer that.",
            mentions=[])
        self.db.commit()
        out = vantage_panel.insights(self.s, 1)
        self.assertEqual(out["uncertain_responses"], 1)

    def test_evidence_carries_the_same_flags_as_insights(self):
        llm_panel.record_response(
            self.s, 1, self.pid, provider="openrouter", model="gpt-4o-mini", day=DAY,
            response_text="Chase Securities is JPMorgan Chase's brokerage arm.",
            mentions=[{"brand_id": 1, "name": "Chase Securities", "is_focus": True,
                      "rule": "exact_name", "excluded": False}])
        self.db.commit()
        row = vantage_panel.evidence(self.s, 1)[0]
        self.assertEqual(row["flags"], ["possible_wrong_entity"])


class EvidenceTests(VantagePanelTestCase):
    def setUp(self):
        super().setUp()
        self.pid = llm_panel.add_prompt(self.s, 1, "compare firms")
        self.db.commit()

    def test_evidence_carries_the_prompt_text_alongside_the_answer(self):
        llm_panel.record_response(self.s, 1, self.pid, provider="google", model="gemini",
                                  day=DAY, response_text="Chase Securities is solid.",
                                  mentions=[{"brand_id": 1, "name": "Chase Securities",
                                            "is_focus": True, "rule": "exact_name",
                                            "excluded": False}])
        self.db.commit()
        out = vantage_panel.evidence(self.s, 1)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["prompt_text"], "compare firms")
        self.assertEqual(out[0]["response_text"], "Chase Securities is solid.")
        self.assertEqual(out[0]["mentions"][0]["name"], "Chase Securities")
        self.assertIsNone(out[0]["error"])

    def test_evidence_carries_error_rows_too(self):
        llm_panel.record_error(self.s, 1, self.pid, model="gemini", day=DAY, error="quota")
        self.db.commit()
        out = vantage_panel.evidence(self.s, 1)
        self.assertEqual(out[0]["error"], "quota")


class ReportTests(VantagePanelTestCase):
    def setUp(self):
        super().setUp()
        self.pid = llm_panel.add_prompt(self.s, 1, "compare firms")
        self.db.commit()

    def _seed(self, mentions):
        llm_panel.record_response(self.s, 1, self.pid, provider="google", model="gemini",
                                  day=DAY, response_text="x", mentions=mentions)

    def test_no_responses_yet_says_so_plainly(self):
        out = vantage_panel.report(self.s, 1)
        self.assertIn("No panel responses recorded yet", out["headline"][0])
        self.assertEqual(out["improvements"],
                         ["No visibility gaps found in the responses recorded so far."])

    def test_headline_states_the_real_wilson_numbers(self):
        focus = [{"brand_id": 1, "name": "Chase Securities", "is_focus": True,
                 "rule": "exact_name", "excluded": False}]
        for _ in range(3):
            self._seed(focus)
        self._seed([{"brand_id": 2, "name": "AKD Securities", "is_focus": False,
                    "rule": "exact_name", "excluded": False}])
        self.db.commit()
        out = vantage_panel.report(self.s, 1)
        self.assertIn("Chase Securities was mentioned in 3 of 4 panel responses", out["headline"][0])
        self.assertIn("AKD Securities was the most-mentioned competitor", out["headline"][1])

    def test_a_visibility_gap_becomes_an_improvement_recommendation(self):
        self._seed([{"brand_id": 2, "name": "AKD Securities", "is_focus": False,
                    "rule": "exact_name", "excluded": False}])
        self.db.commit()
        out = vantage_panel.report(self.s, 1)
        self.assertTrue(any("AKD Securities" in line and "worth targeted content"
                            in line for line in out["improvements"]))

    def test_a_jpmorgan_confused_response_gets_its_own_improvement_line(self):
        self._seed([{"brand_id": 1, "name": "Chase Securities", "is_focus": True,
                    "rule": "exact_name", "excluded": False}])
        llm_panel.record_response(
            self.s, 1, self.pid, provider="openrouter", model="gpt-4o-mini", day=DAY,
            response_text="Chase Securities is JPMorgan Chase's brokerage arm.",
            mentions=[{"brand_id": 1, "name": "Chase Securities", "is_focus": True,
                      "rule": "exact_name", "excluded": False}])
        self.db.commit()
        out = vantage_panel.report(self.s, 1)
        self.assertTrue(any("JPMorgan Chase / Chase Bank" in line for line in out["improvements"]))

    def test_no_focus_mention_at_all_is_called_out_as_the_biggest_gap(self):
        self._seed([{"brand_id": 2, "name": "AKD Securities", "is_focus": False,
                    "rule": "exact_name", "excluded": False}])
        self.db.commit()
        out = vantage_panel.report(self.s, 1)
        self.assertTrue(any("biggest visibility gap" in line for line in out["improvements"]))


if __name__ == "__main__":
    unittest.main()
