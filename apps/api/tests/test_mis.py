"""P4.10 — MIS: daily case counts + 13-header closed-case report."""
import unittest
from datetime import date, datetime, timezone

import sqlalchemy as sa

from core import mis

from ._db import ApiTestCase, DbTestCase

D0, D1 = date(2026, 6, 1), date(2026, 6, 30)


def _dt(d, h=9, mi=0):
    return datetime(2026, 6, d, h, mi, tzinfo=timezone.utc)


class MisCoreTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.execute(
            'INSERT INTO "user"(id,username,password_hash,role,created_at) '
            "VALUES (10,'amir','x','agent','now')")
        self.db.commit()
        self.s = self.db.session
        self.cust = self.s.execute(sa.text(
            "INSERT INTO customer(workspace_id,display_name,handle) "
            "VALUES (1,'Ayesha','@ak') RETURNING id")).scalar()

    def _case(self, opened, first=None, closed=None, state="open",
              cat=None, assignee=10):
        return self.s.execute(sa.text("""
            INSERT INTO "case"(workspace_id,customer_id,channel,state,assignee_id,
                               closure_category,opened_at,first_response_at,
                               closed_at,last_activity_at)
            VALUES (1,:cu,'x',:st,:asg,:cat,:o,:fr,:cl,:o) RETURNING id
        """), {"cu": self.cust, "st": state, "asg": assignee, "cat": cat,
               "o": opened, "fr": first, "cl": closed}).scalar()

    def _msg(self, cid, direction):
        self.s.execute(sa.text(
            "INSERT INTO case_message(case_id,workspace_id,direction,channel,body) "
            "VALUES (:c,1,:d,'x','hi')"), {"c": cid, "d": direction})

    def _ev(self, cid, kind, at, **d):
        import json
        self.s.execute(sa.text(
            "INSERT INTO case_event(case_id,kind,at,detail) "
            "VALUES (:c,:k,:at,CAST(:d AS jsonb))"),
            {"c": cid, "k": kind, "at": at, "d": json.dumps(d)})

    def test_daily_case_counts(self):
        c1 = self._case(_dt(1, 9), first=_dt(1, 9, 10), closed=_dt(1, 10),
                        state="closed", cat="resolved")
        self._case(_dt(2), closed=_dt(3), state="closed", cat="billing")
        self._case(_dt(2))                                   # still open
        c4 = self._case(_dt(1))
        self._ev(c4, "closed", _dt(1, 12))
        self._ev(c4, "state_change", _dt(2, 9), state="open")
        self.db.commit()

        r = mis.daily_case_counts(self.s, 1, D0, D1)
        by = {d["day"]: d for d in r["daily"]}
        self.assertEqual(by["2026-06-01"]["opened"], 2)
        self.assertEqual(by["2026-06-01"]["closed"], 1)
        self.assertEqual(by["2026-06-02"]["opened"], 2)
        self.assertEqual(by["2026-06-02"]["reopened"], 1)
        self.assertEqual(by["2026-06-03"]["closed"], 1)
        self.assertEqual(r["totals"], {"opened": 4, "closed": 2, "reopened": 1})
        _ = c1

    def test_closed_case_report_has_13_headers_and_correct_rows(self):
        c1 = self._case(_dt(1, 9), first=_dt(1, 9, 10), closed=_dt(1, 10),
                        state="closed", cat="resolved")
        for _ in range(2):
            self._msg(c1, "inbound")
        self._msg(c1, "outbound")
        self._case(_dt(5))                                   # open -> excluded
        self.db.commit()

        rep = mis.closed_case_report(self.s, 1, D0, D1)
        self.assertEqual(len(rep["headers"]), 13)
        self.assertEqual(rep["count"], 1)
        row = rep["rows"][0]
        self.assertEqual(row["Case Ref"], f"C-{c1}")
        self.assertEqual(row["Closure Category"], "resolved")
        self.assertEqual(row["First Response (s)"], 600)
        self.assertEqual(row["Handle Time (s)"], 3600)
        self.assertEqual(row["Inbound Msgs"], 2)
        self.assertEqual(row["Outbound Msgs"], 1)
        self.assertEqual(list(row.keys()), rep["headers"])


class MisApiTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        token = self.client.get("/api/v1/csrf").get_json()["token"]
        self.client.post("/api/v1/auth/login",
                         json={"username": "admin", "password": "admin123"},
                         headers={"X-CSRF-Token": token})

    def test_mis_endpoints_and_export(self):
        self.assertEqual(self.client.get(
            "/api/v1/reports/mis/daily?start=2026-06-01&end=2026-06-30").status_code, 200)
        cc = self.client.get(
            "/api/v1/reports/mis/closed-cases?start=2026-06-01&end=2026-06-30")
        self.assertEqual(cc.status_code, 200)
        self.assertEqual(len(cc.get_json()["headers"]), 13)

        csv_r = self.client.get("/api/v1/reports/export"
                                "?kind=mis_closed&format=csv"
                                "&start=2026-06-01&end=2026-06-30")
        self.assertEqual(csv_r.status_code, 200)
        self.assertIn(b"Case Ref", csv_r.get_data())


if __name__ == "__main__":
    unittest.main()
