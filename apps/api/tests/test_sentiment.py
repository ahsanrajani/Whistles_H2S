import os
import unittest

from ._db import DbTestCase
from pathlib import Path
from unittest.mock import patch

from core import insights, sentiment

ROOT = Path(__file__).resolve().parents[1]


class SentimentScoringTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'Bank Alfalah','PK','now')")
        self.db.execute(
            "INSERT INTO brand(id,workspace_id,name,is_focus) VALUES (1,1,'Bank Alfalah',1)")


    def _item(self, iid, *, surface="news", lang="en", title=None, body="", rating=None):
        self.db.execute(
            """INSERT INTO item(id,workspace_id,surface,source,source_kind,external_id,
               url,outlet,title,body,rating,lang_guess,raw_json,collected_at,content_hash)
               VALUES (?,1,?,'googlenews_rss','public',?,?,?,?,?,?,?,'{}','now',?)""",
            (iid, surface, str(iid), f"https://s/{iid}", "Outlet", title, body, rating,
             lang, str(iid)))
        self.db.execute(
            "INSERT INTO mention(id,item_id,brand_id,rule) VALUES (?,?,1,'exact_name')",
            (iid, iid))
        self.db.commit()

    # ---- unit: response-shape normalisation --------------------------------

    def test_normalise_handles_the_router_batch_shape(self):
        # Router flattens a batch into one list of per-input top-1 dicts.
        flat = [[{"label": "negative", "score": 0.9},
                 {"label": "positive", "score": 0.8},
                 {"label": "neutral", "score": 0.7}]]
        got = sentiment._normalise(flat, 3)
        self.assertEqual([sentiment._label_of(p) for p in got], ["neg", "pos", "neu"])
        # Ideal shape: one label list per input.
        nested = [[{"label": "negative", "score": 0.9}], [{"label": "positive", "score": 0.8}]]
        self.assertEqual([sentiment._label_of(p) for p in sentiment._normalise(nested, 2)],
                         ["neg", "pos"])
        # Single un-nested prediction.
        self.assertEqual(sentiment._normalise([{"label": "negative", "score": 1.0}], 1),
                         [[{"label": "negative", "score": 1.0}]])

    def test_label_vocabularies_collapse(self):
        self.assertEqual(sentiment._label_of(
            [{"label": "LABEL_0", "score": 0.7}, {"label": "LABEL_1", "score": 0.3}]), "neg")
        self.assertEqual(sentiment._label_of([{"label": "positive", "score": 0.9}]), "pos")

    # ---- rating is the sentiment for app reviews --------------------------

    def test_star_rating_drives_review_sentiment_without_a_model_call(self):
        self._item(1, surface="app_reviews", title="Slowest App", body="unusable", rating=1)
        self._item(2, surface="app_reviews", title="Perfect", body="love it", rating=5)
        self._item(3, surface="app_reviews", title="Meh", body="it is an app", rating=3)
        with patch.object(sentiment, "_post", side_effect=AssertionError("model called")):
            result = sentiment.score_pending(self.db, 1, {"HF_TOKEN": "hf_x"}, lambda _m: None)
        self.assertEqual(result["by_rating"], 3)
        rows = dict(self.db.execute("SELECT mention_id,label FROM sentiment").fetchall())
        self.assertEqual((rows[1], rows[2], rows[3]), ("neg", "pos", "neu"))
        model_ids = {r[0] for r in self.db.execute("SELECT DISTINCT model_id FROM sentiment")}
        self.assertEqual(model_ids, {"rating"})

    # ---- lexicon decides the clear cases --------------------------------

    def test_lexicon_scores_clear_text_and_the_model_takes_the_rest(self):
        self._item(1, body="Bank Alfalah app keeps crashing, worst service ever")   # neg cues
        self._item(2, body="Great experience opening a Bank Alfalah account")        # pos cue
        self._item(3, surface="reddit", body="anyone here banking with Bank Alfalah")  # faint

        with patch.object(sentiment, "_post",
                          return_value=[[{"label": "neutral", "score": 0.7}]]) as post:
            sentiment.score_pending(self.db, 1, {"HF_TOKEN": "hf_x", "SENTIMENT_MODEL_ID": "pinned/model"},
                                    lambda _m: None)
        got = dict(self.db.execute("SELECT mention_id,label FROM sentiment").fetchall())
        self.assertEqual((got[1], got[2], got[3]), ("neg", "pos", "neu"))
        by_model = dict(self.db.execute("SELECT mention_id,model_id FROM sentiment").fetchall())
        self.assertEqual(by_model[1], "lexicon")
        self.assertEqual(by_model[3], "pinned/model")     # only the faint one hit the model
        post.assert_called_once()

    def test_non_english_is_marked_not_scored(self):
        self._item(1, lang="roman_urdu", body="Bank Alfalah ka app bohat acha hai")
        with patch.object(sentiment, "_post", return_value=[]):
            result = sentiment.score_pending(self.db, 1, {"HF_TOKEN": "hf_x", "SENTIMENT_MODEL_ID": "pinned/model"},
                                             lambda _m: None)
        self.assertEqual(result["skipped"], 1)
        row = self.db.execute("SELECT label,model_id,note FROM sentiment WHERE mention_id=1").fetchone()
        self.assertEqual(row[0], "not_scored")
        self.assertEqual(row[1], "pinned/model")
        self.assertIn("only en is scored", row[2])

    @patch.dict(os.environ, {}, clear=False)
    def test_no_token_falls_back_to_the_lexicon(self):
        os.environ.pop("HF_TOKEN", None)
        self._item(1, body="this update is terrible and broken")
        self._item(2, body="a routine corporate filing")
        result = sentiment.score_pending(self.db, 1, {}, lambda _m: None)   # no HF_TOKEN
        self.assertEqual(result["by_model"], 0)
        got = dict(self.db.execute("SELECT mention_id,label FROM sentiment").fetchall())
        self.assertEqual(got[1], "neg")
        self.assertEqual(got[2], "neu")                   # no cue, no model → neutral

    def test_breakdown_reports_negative_share_with_interval(self):
        self._item(1, surface="app_reviews", body="crashes constantly", rating=1)
        self._item(2, surface="app_reviews", body="works great", rating=5)
        with patch.object(sentiment, "_post", side_effect=AssertionError("no model")):
            sentiment.score_pending(self.db, 1, {"HF_TOKEN": "hf_x"}, lambda _m: None)
        brand = insights.sentiment_breakdown(self.db, 1)[0]
        self.assertEqual(brand["scored"], 2)
        self.assertEqual(brand["neg"], 1)
        self.assertIsNotNone(brand["neg_share"])
        self.assertLessEqual(brand["neg_lo"], brand["neg_share"])
        self.assertGreaterEqual(brand["neg_hi"], brand["neg_share"])


if __name__ == "__main__":
    unittest.main()
