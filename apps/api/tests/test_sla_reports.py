"""P4.4 — SLA reports: compliance %, first response, assignment wait, missed."""
import unittest
from datetime import date, datetime, timezone

import sqlalchemy as sa

from core import sla_reports

from ._db import ApiTestCase, DbTestCase

DAY = date(2026, 6, 15)
NOW = datetime(2026, 6, 16, 0, 0, tzinfo=timezone.utc)


def _dt(h, m=0):
    return datetime(2026, 6, 15, h, m, tzinfo=timezone.utc)


class SlaReportTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.commit()
        self.s = self.db.session
        self.cust = self.s.execute(sa.text(
            "INSERT INTO customer(workspace_id,display_name) VALUES (1,'C') RETURNING id"
        )).scalar()

    def _case(self, opened, first=None, closed=None, state="open"):
        return self.s.execute(sa.text("""
            INSERT INTO "case"(workspace_id,customer_id,channel,state,
                               opened_at,first_response_at,closed_at,last_activity_at)
            VALUES (1,:cu,'x',:st,:o,:fr,:cl,:o) RETURNING id
        """), {"cu": self.cust, "st": state, "o": opened, "fr": first,
               "cl": closed}).scalar()

    def _event(self, cid, kind, at, **detail):
        import json
        self.s.execute(sa.text(
            "INSERT INTO case_event(case_id,kind,at,detail) "
            "VALUES (:c,:k,:at,CAST(:d AS jsonb))"),
            {"c": cid, "k": kind, "at": at, "d": json.dumps(detail)})

    def _report(self):
        return sla_reports.sla_report(self.s, 1, DAY, DAY, now=NOW)

    def test_first_response_compliance_is_wilson_scored(self):
        c1 = self._case(_dt(9), first=_dt(9, 10), closed=_dt(9, 40), state="closed")
        self._event(c1, "assigned", _dt(9, 2))
        c2 = self._case(_dt(10), first=_dt(10, 30))
        self._event(c2, "assigned", _dt(10, 5))
        c3 = self._case(_dt(11))
        self._event(c3, "sla_breach", _dt(11, 20), check="first_response")
        self.db.commit()

        r = self._report()
        fr = r["first_response"]["compliance"]
        self.assertEqual(fr["met"], 1)
        self.assertEqual(fr["eligible"], 3)
        self.assertAlmostEqual(fr["rate"], 1 / 3)
        lo, hi = fr["wilson"]
        self.assertLess(lo, fr["rate"])
        self.assertGreater(hi, fr["rate"])

    def test_time_distributions_and_assignment_wait(self):
        c1 = self._case(_dt(9), first=_dt(9, 10))
        self._event(c1, "assigned", _dt(9, 2))
        c2 = self._case(_dt(10), first=_dt(10, 30))
        self._event(c2, "assigned", _dt(10, 5))
        self.db.commit()

        r = self._report()
        self.assertEqual(r["first_response"]["seconds"]["n"], 2)
        self.assertAlmostEqual(r["first_response"]["seconds"]["avg"], (600 + 1800) / 2)
        self.assertAlmostEqual(r["first_response"]["seconds"]["max"], 1800.0)
        self.assertAlmostEqual(r["assignment_wait"]["seconds"]["avg"], (120 + 300) / 2)

    def test_missed_count_reconciles_against_case_event(self):
        c = self._case(_dt(9))
        self._event(c, "sla_breach", _dt(9, 20), check="first_response")
        self._event(c, "sla_breach", _dt(9, 40), check="escalation")
        self.db.commit()
        r = self._report()
        self.assertEqual(r["missed"]["total"], 2)
        self.assertEqual(r["missed"]["by_check"],
                         {"first_response": 1, "escalation": 1})

    def test_resolution_not_past_due_is_not_counted_against_compliance(self):
        self._case(_dt(9), first=_dt(9, 5), closed=_dt(9, 30), state="closed")
        self._case(_dt(10), first=_dt(10, 5))       # open, < 24h old at NOW
        self.db.commit()
        res = self._report()["resolution"]["compliance"]
        self.assertEqual(res["met"], 1)
        self.assertEqual(res["eligible"], 1)


class SlaReportApiTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        token = self.client.get("/api/v1/csrf").get_json()["token"]
        self.client.post("/api/v1/auth/login",
                         json={"username": "admin", "password": "admin123"},
                         headers={"X-CSRF-Token": token})

    def test_sla_report_endpoint(self):
        r = self.client.get("/api/v1/reports/sla?start=2026-06-01&end=2026-06-30")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertIn("first_response", body)
        self.assertIn("wilson", body["first_response"]["compliance"])
        self.assertEqual(
            self.client.get("/api/v1/reports/sla?start=bad&end=2026-06-30").status_code,
            400)


if __name__ == "__main__":
    unittest.main()
