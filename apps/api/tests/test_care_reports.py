"""P4.3 — care reports: agent session / ready / not-ready / idle + handling time."""
import unittest
from datetime import date, datetime, timezone

import sqlalchemy as sa

from core import care_reports
from db import repositories as repo

from ._db import ApiTestCase, DbTestCase

DAY = date(2026, 6, 15)


def _dt(h, m=0):
    return datetime(2026, 6, 15, h, m, tzinfo=timezone.utc)


class CareReportTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        for uid, name in ((10, "amir"), (11, "bina"), (12, "chan")):
            self.db.execute(
                'INSERT INTO "user"(id,username,password_hash,role,created_at) '
                "VALUES (?,?,'x','agent','now')", (uid, name))
        self.db.commit()
        self.s = self.db.session

    def _rec(self, uid, kind, at):
        repo.agent_activity.record(self.s, workspace_id=1, user_id=uid,
                                   kind=kind, at=at)

    def _report(self, start=DAY, end=DAY):
        return {a["user_id"]: a for a in
                care_reports.agent_report(self.s, 1, start, end)["agents"]}

    def test_state_durations_from_the_event_stream(self):
        for kind, at in [("login", _dt(9)), ("not_ready", _dt(10)),
                         ("ready", _dt(10, 30)), ("idle", _dt(12)),
                         ("active", _dt(12, 15)), ("logout", _dt(17))]:
            self._rec(10, kind, at)
        self.db.commit()
        a = self._report()[10]
        self.assertEqual(a["logins"], 1)
        self.assertEqual(a["not_ready_seconds"], 1800)
        self.assertEqual(a["idle_seconds"], 900)
        self.assertEqual(a["ready_seconds"], 3600 + 5400 + 17100)
        self.assertEqual(a["session_seconds"], 8 * 3600)

    def test_open_session_is_clamped_to_the_window_end(self):
        self._rec(11, "login", _dt(8))
        self.db.commit()
        a = self._report()[11]
        # 08:00 -> 23:59:59.999999 is just under 16h
        self.assertGreater(a["ready_seconds"], 16 * 3600 - 2)
        self.assertEqual(a["session_seconds"], a["ready_seconds"])

    def test_a_session_open_before_the_window_counts_from_the_window_start(self):
        repo.agent_activity.record(
            self.s, workspace_id=1, user_id=12, kind="login",
            at=datetime(2026, 6, 14, 9, tzinfo=timezone.utc))
        self._rec(12, "logout", _dt(11))
        self.db.commit()
        a = self._report()[12]
        self.assertEqual(a["ready_seconds"], 11 * 3600)   # 00:00 -> 11:00

    def test_handling_time_comes_from_case_timestamps(self):
        self._rec(10, "login", _dt(9))
        self._rec(10, "logout", _dt(17))
        cid = self.s.execute(sa.text(
            "INSERT INTO customer(workspace_id,display_name) VALUES (1,'C') RETURNING id"
        )).scalar()
        self.s.execute(sa.text("""
            INSERT INTO "case"(workspace_id,customer_id,channel,state,assignee_id,
                               opened_at,first_response_at,closed_at,last_activity_at)
            VALUES (1,:cid,'x','closed',10,:o,:fr,:cl,:cl)
        """), {"cid": cid, "o": _dt(9, 0), "fr": _dt(9, 5), "cl": _dt(9, 30)})
        self.db.commit()
        a = self._report()[10]
        self.assertEqual(a["cases_closed"], 1)
        self.assertAlmostEqual(a["avg_first_response_seconds"], 300.0)
        self.assertAlmostEqual(a["avg_handle_seconds"], 1800.0)
        self.assertIsNotNone(a["occupancy"])


class CareReportApiTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        token = self.client.get("/api/v1/csrf").get_json()["token"]
        self.client.post("/api/v1/auth/login",
                         json={"username": "admin", "password": "admin123"},
                         headers={"X-CSRF-Token": token})
        with self.client.session_transaction() as s:
            self.csrf = s.get("csrf_token", "")

    def test_session_endpoint_records_activity_and_report_reads_it(self):
        for state in ("login", "ready", "not_ready", "logout"):
            r = self.client.post("/api/v1/care/session", json={"state": state},
                                 headers={"X-CSRF-Token": self.csrf})
            self.assertEqual(r.status_code, 200, state)
        bad = self.client.post("/api/v1/care/session", json={"state": "wat"},
                               headers={"X-CSRF-Token": self.csrf})
        self.assertEqual(bad.status_code, 400)

        today = date.today().isoformat()
        rep = self.client.get(f"/api/v1/reports/care/agents?start={today}&end={today}")
        self.assertEqual(rep.status_code, 200)
        self.assertTrue(rep.get_json()["agents"])


if __name__ == "__main__":
    unittest.main()
