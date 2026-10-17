import os
import unittest

from ._db import DbTestCase
from pathlib import Path
from unittest.mock import patch

from core import classify, insights

ROOT = Path(__file__).resolve().parents[1]


class ClassifyTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.execute(
            "INSERT INTO brand(id,workspace_id,name,is_focus) VALUES (1,1,'Focus',1)")


    def _item(self, iid, *, surface="app_reviews", lang="en", body=""):
        self.db.execute(
            """INSERT INTO item(id,workspace_id,surface,source,source_kind,external_id,
               url,outlet,published_at,body,lang_guess,raw_json,collected_at,content_hash)
               VALUES (?,1,?,'appstore_reviews','public',?,?,?,?,?,?,'{}','now',?)""",
            (iid, surface, str(iid), f"https://s/{iid}", "App Store",
             f"2026-08-{10 + iid:02d}T09:00:00Z", body, lang, str(iid)))
        self.db.execute(
            "INSERT INTO mention(id,item_id,brand_id,rule) VALUES (?,?,1,'app_review')",
            (iid, iid))
        self.db.commit()

    def _run(self, fake):
        orig = classify._post
        classify._post = fake
        try:
            return classify.classify_pending(self.db, 1, {"HF_TOKEN": "x"}, lambda _m: None)
        finally:
            classify._post = orig

    # ---- unit: keyword rules --------------------------------------------

    def test_rule_category_covers_the_high_stakes_buckets(self):
        cases = {
            "someone hacked my account, money deducted without OTP": "fraud",
            "the app keeps crashing and support never replies": "complaint",
            "please add dark mode and fingerprint login": "feature_request",
            "is Meezan better than HBL for salary accounts": "comparison",
            "how do I reset my transaction PIN": "question",
            "love this app, smooth and fast, highly recommend": "praise",
        }
        for text, expected in cases.items():
            self.assertEqual(classify._rule_category(text, "app_reviews")[0], expected, text)
        self.assertEqual(classify._rule_category("it is a banking app", "app_reviews")[0], None)

    def test_fallback_uses_surface_rating_and_sentiment(self):
        self.assertEqual(classify._fallback_category("app_reviews", 1, None)[0], "complaint")
        self.assertEqual(classify._fallback_category("app_reviews", 5, None)[0], "praise")
        self.assertEqual(classify._fallback_category("app_reviews", 3, "neg")[0], "complaint")
        self.assertEqual(classify._fallback_category("youtube", None, None)[0], "news")
        self.assertEqual(classify._fallback_category("news", None, None)[0], "news")
        self.assertEqual(classify._fallback_category("reddit", None, "pos")[0], "praise")
        self.assertEqual(classify._fallback_category("reddit", None, None)[0], "other")

    def test_news_rule_only_fires_on_news_surface(self):
        text = "Focus Bank announces record quarterly profit and appoints new CEO"
        self.assertEqual(classify._rule_category(text, "news")[0], "news")
        self.assertNotEqual(classify._rule_category(text, "app_reviews")[0], "news")

    def test_category_of_accepts_both_router_shapes(self):
        complaint = classify.CATEGORIES[0][1]
        self.assertEqual(classify._category_of({"labels": [complaint], "scores": [0.9]})[0],
                         "complaint")
        self.assertEqual(classify._category_of([{"label": complaint, "score": 0.9},
                                                {"label": "praise", "score": 0.1}])[0],
                         "complaint")
        self.assertEqual(classify._category_of([{"label": complaint, "score": 0.12}])[0], "other")

    # ---- pipeline ------------------------------------------------------

    def test_rules_decide_confident_rows_and_the_model_takes_the_rest(self):
        self._item(1, body="the app keeps crashing after every update")     # rule: complaint
        self._item(2, body="thinking about the interest rate situation")    # → model
        self._item(3, lang="ur", body="bohot acha bank hai")               # → fallback (other)

        comparison = classify.CATEGORIES[3][1]

        def fake(model_id, token, text, timeout=60):
            return {"labels": [comparison], "scores": [0.9]}

        result = self._run(fake)
        self.assertEqual(result["by_rule"], 1)
        self.assertEqual(result["by_model"], 1)
        self.assertEqual(result["by_fallback"], 1)     # the Urdu, no rating, no cue
        got = dict(self.db.execute("SELECT mention_id,category FROM mention_class").fetchall())
        self.assertEqual((got[1], got[2], got[3]), ("complaint", "comparison", "other"))
        by_id = dict(self.db.execute("SELECT mention_id,model_id FROM mention_class").fetchall())
        self.assertEqual(by_id[1], "rules")
        self.assertEqual(by_id[2], classify.MODEL_DEFAULT)
        self.assertEqual(by_id[3], "fallback")

    def test_low_model_confidence_falls_back_to_other(self):
        self._item(1, body="some neutral musing about banking in general")
        self._run(lambda *a, **k: {"labels": [classify.CATEGORIES[0][1]], "scores": [0.1]})
        self.assertEqual(
            self.db.execute("SELECT category FROM mention_class WHERE mention_id=1").fetchone()[0],
            "other")

    @patch.dict(os.environ, {}, clear=False)
    def test_no_token_leaves_unmatched_rows_as_other(self):
        os.environ.pop("HF_TOKEN", None)
        self._item(1, body="the app keeps crashing")             # rule fires
        self._item(2, body="a neutral sentence about nothing")   # no rule, no token
        result = classify.classify_pending(self.db, 1, {}, lambda _m: None)
        self.assertEqual(result["by_model"], 0)
        got = dict(self.db.execute("SELECT mention_id,category FROM mention_class").fetchall())
        self.assertEqual(got[1], "complaint")
        self.assertEqual(got[2], "other")

    def test_evidence_filter_and_mix_aggregate_by_category(self):
        self._item(1, body="the app keeps crashing and freezing")           # complaint
        self._item(2, body="is HBL better than Focus for savings")          # comparison
        self._item(3, lang="ur", body="acha bank hai")                      # other

        self._run(lambda *a, **k: {"labels": [classify.CATEGORIES[4][1]], "scores": [0.9]})

        rows, total = insights.evidence(self.db, 1, category="complaint")
        self.assertEqual(total, 1)
        self.assertEqual(rows[0][19], "complaint")

        mix = insights.mention_mix(self.db, 1)
        self.assertEqual(mix["total"], 3)
        by_key = {c["key"]: c["n"] for c in mix["cats"]}
        self.assertEqual(by_key.get("complaint"), 1)
        self.assertEqual(by_key.get("comparison"), 1)
        self.assertEqual(by_key.get("other"), 1)
        self.assertEqual(sum(c["n"] for c in mix["cats"]), 3)


if __name__ == "__main__":
    unittest.main()
