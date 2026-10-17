"""P4.7 — CSAT / survey module + complaint analytics."""
import json
import unittest
from datetime import date, datetime, timezone

import sqlalchemy as sa

from core import surveys

from ._db import ApiTestCase, DbTestCase

D0, D1 = date(2026, 6, 1), date(2026, 6, 30)


def _dt(d, h=9):
    return datetime(2026, 6, d, h, tzinfo=timezone.utc)


class SurveyCoreTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.commit()
        self.s = self.db.session
        self.cust = self.s.execute(sa.text(
            "INSERT INTO customer(workspace_id,display_name) VALUES (1,'C') RETURNING id"
        )).scalar()

    def _case(self, d, category="complaint", channel="x", closed=True, state="closed"):
        return self.s.execute(sa.text("""
            INSERT INTO "case"(workspace_id,customer_id,channel,state,closure_category,
                               opened_at,closed_at,last_activity_at)
            VALUES (1,:cu,:ch,:st,:cat,:o,:cl,:o) RETURNING id
        """), {"cu": self.cust, "ch": channel, "st": state, "cat": category,
               "o": _dt(d), "cl": _dt(d, 11) if closed else None}).scalar()

    def _close_event(self, cid, d):
        self.s.execute(sa.text(
            "INSERT INTO case_event(case_id,kind,at,detail) "
            "VALUES (:c,'closed',:at,'{}'::jsonb)"), {"c": cid, "at": _dt(d, 11)})

    def test_ensure_default_is_idempotent(self):
        a = surveys.ensure_default(self.s, 1)
        b = surveys.ensure_default(self.s, 1)
        self.assertEqual(a, b)

    def test_bucketing(self):
        self.assertEqual(surveys.bucket_for("csat", 5, 1, 5), "satisfied")
        self.assertEqual(surveys.bucket_for("csat", 3, 1, 5), "neutral")
        self.assertEqual(surveys.bucket_for("csat", 1, 1, 5), "dissatisfied")
        self.assertEqual(surveys.bucket_for("nps", 10, 0, 10), "promoter")
        self.assertEqual(surveys.bucket_for("nps", 8, 0, 10), "passive")
        self.assertEqual(surveys.bucket_for("nps", 4, 0, 10), "detractor")

    def test_issue_then_record(self):
        out = surveys.issue(self.s, 1, case_id=None)
        self.assertIsNotNone(out["token"])
        rec = surveys.record(self.s, 1, out["token"], 5, comment="great")
        self.assertEqual(rec["bucket"], "satisfied")
        with self.assertRaises(surveys.SurveyError):
            surveys.record(self.s, 1, out["token"], 4)          # already answered
        with self.assertRaises(surveys.SurveyError):
            surveys.record(self.s, 1, "nope", 4)                # bad token
        out2 = surveys.issue(self.s, 1)
        with self.assertRaises(surveys.SurveyError):
            surveys.record(self.s, 1, out2["token"], 9)         # out of scale

    def test_on_case_closed_issues_once(self):
        cid = self._case(3)
        first = surveys.on_case_closed(self.s, 1, cid)
        self.assertIsNotNone(first)
        self.assertIsNone(surveys.on_case_closed(self.s, 1, cid))

    def test_csat_report_wilson_and_distribution(self):
        toks = [surveys.issue(self.s, 1)["token"] for _ in range(4)]
        for tok, sc in zip(toks[:3], (5, 5, 2)):
            surveys.record(self.s, 1, tok, sc)
        self.db.commit()
        r = surveys.csat_report(self.s, 1, date(2026, 1, 1), date(2027, 1, 1))
        self.assertEqual(r["issued"], 4)
        self.assertEqual(r["responses"], 3)
        self.assertEqual(r["response_rate"]["k"], 3)
        self.assertEqual(r["response_rate"]["n"], 4)
        self.assertEqual(r["csat"]["k"], 2)
        self.assertEqual(r["csat"]["n"], 3)
        self.assertAlmostEqual(r["avg_score"], (5 + 5 + 2) / 3)
        self.assertEqual(r["distribution"], {"2": 1, "5": 2})
        self.assertIsNotNone(r["csat"]["wilson"][0])

    def test_complaint_report(self):
        c1 = self._case(4, category="billing", channel="x")
        c2 = self._case(5, category="billing", channel="facebook")
        c3 = self._case(6, category="fraud", channel="x", state="open")
        self._close_event(c3, 6)                # was closed, now open -> reopened
        tok = surveys.issue(self.s, 1, case_id=c1)["token"]
        surveys.record(self.s, 1, tok, 4)
        self.db.commit()

        rep = surveys.complaint_report(self.s, 1, D0, D1)
        self.assertEqual(rep["total"], 3)
        self.assertEqual(rep["by_category"]["billing"], 2)
        self.assertEqual(rep["reopen_rate"]["k"], 1)
        self.assertEqual(rep["reopen_rate"]["n"], 3)
        self.assertAlmostEqual(rep["avg_csat"], 4.0)
        self.assertIn("x", rep["by_channel"])


class SurveyApiTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        token = self.client.get("/api/v1/csrf").get_json()["token"]
        self.client.post("/api/v1/auth/login",
                         json={"username": "admin", "password": "admin123"},
                         headers={"X-CSRF-Token": token})
        with self.client.session_transaction() as s:
            self.csrf = s.get("csrf_token", "")

    def _post(self, path, body):
        return self.client.post(path, json=body, headers={"X-CSRF-Token": self.csrf})

    def test_close_auto_issues_and_full_survey_cycle(self):
        cid = self._post("/api/v1/care/cases/ingest",
                         {"platform": "x", "handle": "@c", "body": "help"}
                         ).get_json()["case_id"]
        self._post(f"/api/v1/care/cases/{cid}/transition",
                   {"state": "closed", "closure_category": "resolved"})

        conn = self.app.db_operator()
        try:
            tok = conn.execute(
                "SELECT token FROM survey_response WHERE case_id = ?", (cid,)).fetchone()[0]
        finally:
            conn.close()

        r = self._post("/api/v1/care/surveys/respond",
                       {"token": tok, "score": 5, "comment": "quick help"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["bucket"], "satisfied")

        csat = self.client.get("/api/v1/reports/csat"
                               "?start=2026-01-01&end=2027-01-01").get_json()
        self.assertGreaterEqual(csat["responses"], 1)
        comp = self.client.get("/api/v1/reports/complaints"
                               "?start=2026-01-01&end=2027-01-01").get_json()
        self.assertGreaterEqual(comp["total"], 1)


if __name__ == "__main__":
    unittest.main()
