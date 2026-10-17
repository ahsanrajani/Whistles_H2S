"""P2.8 — match-precision report per brand × pattern class, Wilson intervals.

Gate: safe >= 0.95, gated >= 0.85, each with its interval. `met` is true only
when the interval's lower bound clears the target.
"""
import unittest

from core import precision

from ._db import ApiTestCase, DbTestCase


class MatchPrecisionTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.execute(
            "INSERT INTO brand(id,workspace_id,name,is_focus) VALUES (1,1,'Acme',1)")
        self.db.execute(
            "INSERT INTO brand(id,workspace_id,name,is_focus) VALUES (2,1,'Beta',0)")
        self.db.commit()
        self._iid = 0
        self._mid = 0

    def _match(self, brand_id, *, gated, correct, rule="exact_name"):
        self._iid += 1
        self._mid += 1
        self.db.execute(
            """INSERT INTO item(id,workspace_id,surface,source,source_kind,external_id,
               raw_json,collected_at,content_hash)
               VALUES (?,1,'news','googlenews_rss','public',?,'{}','now',?)""",
            (self._iid, str(self._iid), str(self._iid)))
        self.db.execute(
            "INSERT INTO mention(id,workspace_id,item_id,brand_id,rule,needs_review) "
            "VALUES (?,1,?,?,?,?)",
            (self._mid, self._iid, brand_id, rule, 1 if gated else 0))
        if correct is not None:
            self.db.execute(
                "INSERT INTO gold_label(mention_id,workspace_id,correct,labelled_at) "
                "VALUES (?,1,?,'now')", (self._mid, 1 if correct else 0))
        self.db.commit()

    def _report(self):
        return precision.match_precision(self.db, 1)

    def test_shape_and_point_estimate(self):
        for _ in range(8):
            self._match(1, gated=False, correct=True)
        self._match(1, gated=False, correct=False)          # 8/9 correct
        acme = next(b for b in self._report()["brands"] if b["brand"] == "Acme")
        self.assertEqual(acme["safe"]["matched"], 9)
        self.assertEqual(acme["safe"]["labelled"], 9)
        self.assertEqual(acme["safe"]["correct"], 8)
        self.assertAlmostEqual(acme["safe"]["precision"], 8 / 9, places=3)
        self.assertLess(acme["safe"]["ci_low"], acme["safe"]["precision"])
        self.assertGreater(acme["safe"]["ci_high"], acme["safe"]["precision"])

    def test_small_perfect_sample_does_not_meet_the_target(self):
        for _ in range(10):
            self._match(1, gated=False, correct=True)       # 10/10 but CI low ~0.72
        acme = next(b for b in self._report()["brands"] if b["brand"] == "Acme")
        self.assertEqual(acme["safe"]["precision"], 1.0)
        self.assertFalse(acme["safe"]["met"])

    def test_large_clean_sample_meets_the_target(self):
        for _ in range(150):
            self._match(1, gated=False, correct=True)
        acme = next(b for b in self._report()["brands"] if b["brand"] == "Acme")
        self.assertGreaterEqual(acme["safe"]["ci_low"], precision.SAFE_TARGET)
        self.assertTrue(acme["safe"]["met"])

    def test_gated_uses_the_lower_target(self):
        for _ in range(60):
            self._match(2, gated=True, correct=True, rule="context_name")
        beta = next(b for b in self._report()["brands"] if b["brand"] == "Beta")
        self.assertEqual(beta["gated"]["target"], precision.GATED_TARGET)
        self.assertTrue(beta["gated"]["met"])
        self.assertFalse(beta["safe"]["met"])               # no safe labels

    def test_unlabelled_matches_have_no_precision(self):
        self._match(1, gated=False, correct=None)
        acme = next(b for b in self._report()["brands"] if b["brand"] == "Acme")
        self.assertEqual(acme["safe"]["matched"], 1)
        self.assertEqual(acme["safe"]["labelled"], 0)
        self.assertIsNone(acme["safe"]["precision"])
        self.assertFalse(acme["safe"]["met"])

    def test_identity_rules_are_excluded(self):
        self._match(1, gated=False, correct=True, rule="meta_mention")
        self._match(1, gated=False, correct=True, rule="app_review")
        report = self._report()
        self.assertEqual(report["sample_size"], 0)

    def test_sample_size_counts_labels(self):
        self._match(1, gated=False, correct=True)
        self._match(1, gated=True, correct=False)
        self._match(1, gated=False, correct=None)           # not labelled
        self.assertEqual(self._report()["sample_size"], 2)


class AdminPrecisionEndpointTests(ApiTestCase):
    def _login(self, user, pw):
        token = self.client.get("/api/v1/csrf").get_json()["token"]
        self.client.post("/api/v1/auth/login", json={"username": user, "password": pw},
                         headers={"X-CSRF-Token": token})

    def test_admin_gets_the_report(self):
        self._login("admin", "admin123")
        resp = self.client.get("/api/v1/admin/precision")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertIn("brands", body)
        self.assertEqual(body["targets"], {"safe": 0.95, "gated": 0.85})
        self.assertEqual(body["sample_target"], 200)

    def test_viewer_is_forbidden(self):
        self._login("bank", "viewer123")
        self.assertEqual(self.client.get("/api/v1/admin/precision").status_code, 403)


if __name__ == "__main__":
    unittest.main()
