"""P4.9 — scheduled report distribution by email via the job system."""
import unittest
from datetime import date

import sqlalchemy as sa

from core import report_delivery
from integrations import email

from ._db import ApiTestCase, DbTestCase


class ReportDeliveryCoreTests(DbTestCase):
    def setUp(self):
        super().setUp()
        email.OUTBOX.clear()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.commit()
        self.s = self.db.session

    def test_build_report_dispatch(self):
        out = report_delivery.build_report(self.s, 1, "csat",
                                           date(2026, 1, 1), date(2026, 1, 31))
        self.assertIn("issued", out)
        with self.assertRaises(report_delivery.DeliveryError):
            report_delivery.build_report(self.s, 1, "metrics",
                                         date(2026, 1, 1), date(2026, 1, 31))
        with self.assertRaises(report_delivery.DeliveryError):
            report_delivery.build_report(self.s, 1, "bogus",
                                         date(2026, 1, 1), date(2026, 1, 31))

    def test_upsert_registers_a_scheduled_task(self):
        sid = report_delivery.upsert(
            self.s, 1, name="Weekly SLA", kind="sla", cron="0 7 * * 1",
            recipients=["ops@bank.test"], fmt="pdf")
        self.db.commit()
        task = self.s.execute(sa.text(
            "SELECT kind, cron, enabled FROM scheduled_task WHERE name = :n"),
            {"n": f"report:{sid}"}).first()
        self.assertEqual(task[0], "report_email")
        self.assertEqual(task[1], "0 7 * * 1")

    def test_upsert_validates(self):
        with self.assertRaises(report_delivery.DeliveryError):
            report_delivery.upsert(self.s, 1, name="x", kind="nope",
                                   cron="* * * * *", recipients=["a@b.c"])
        with self.assertRaises(report_delivery.DeliveryError):
            report_delivery.upsert(self.s, 1, name="x", kind="sla",
                                   cron="* * * * *", recipients=[])

    def test_run_renders_and_sends_to_the_mock_outbox(self):
        sid = report_delivery.upsert(
            self.s, 1, name="Weekly complaints", kind="complaints",
            cron="0 7 * * 1", recipients=["a@bank.test", "b@bank.test"], fmt="xlsx")
        res = report_delivery.run(self.s, 1, sid)
        self.db.commit()
        self.assertEqual(res["status"], "queued(mock)")
        self.assertEqual(len(email.OUTBOX), 1)
        msg = email.OUTBOX[0]
        self.assertEqual(msg["to"], ["a@bank.test", "b@bank.test"])
        self.assertEqual(len(msg["attachments"]), 1)
        self.assertTrue(msg["attachments"][0].endswith(".xlsx"))
        status = self.s.execute(sa.text(
            "SELECT last_status FROM report_schedule WHERE id = :i"),
            {"i": sid}).scalar()
        self.assertEqual(status, "queued(mock)")

    def test_delete_disables_the_task(self):
        sid = report_delivery.upsert(self.s, 1, name="x", kind="sla",
                                     cron="* * * * *", recipients=["a@b.c"])
        report_delivery.delete(self.s, 1, sid)
        self.db.commit()
        enabled = self.s.execute(sa.text(
            "SELECT enabled FROM scheduled_task WHERE name = :n"),
            {"n": f"report:{sid}"}).scalar()
        self.assertIn(enabled, (False, 0))


class ReportDeliveryApiTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        email.OUTBOX.clear()
        token = self.client.get("/api/v1/csrf").get_json()["token"]
        self.client.post("/api/v1/auth/login",
                         json={"username": "admin", "password": "admin123"},
                         headers={"X-CSRF-Token": token})
        with self.client.session_transaction() as s:
            self.csrf = s.get("csrf_token", "")

    def _h(self):
        return {"X-CSRF-Token": self.csrf}

    def test_schedule_crud_run_and_worker(self):
        sid = self.client.post("/api/v1/reports/schedules",
                               json={"name": "Weekly CSAT", "kind": "csat",
                                     "format": "csv", "cron": "0 7 * * 1",
                                     "recipients": ["ops@bank.test"]},
                               headers=self._h()).get_json()["id"]

        listed = self.client.get("/api/v1/reports/schedules").get_json()["schedules"]
        self.assertTrue(any(s["id"] == sid for s in listed))

        run = self.client.post(f"/api/v1/reports/schedules/{sid}/run",
                               headers=self._h())
        self.assertEqual(run.status_code, 200)
        self.assertEqual(len(email.OUTBOX), 1)

        # the same path via the job worker
        from jobs import runner, worker
        conn = self.app.db_operator()
        try:
            ws = conn.execute("SELECT id FROM workspace ORDER BY id LIMIT 1").fetchone()[0]
            runner.enqueue(conn.session, "report_email",
                           {"ws": ws, "schedule_id": sid}, tenant_id=ws)
            conn.commit()
        finally:
            conn.close()
        self.assertTrue(worker.run_one(kinds=["report_email"]))
        self.assertEqual(len(email.OUTBOX), 2)

        self.assertEqual(self.client.put(f"/api/v1/reports/schedules/{sid}",
                                         json={"name": "Weekly CSAT v2", "kind": "csat",
                                               "cron": "0 8 * * 1",
                                               "recipients": ["ops@bank.test"]},
                                         headers=self._h()).status_code, 200)
        self.assertEqual(self.client.delete(f"/api/v1/reports/schedules/{sid}",
                                            headers=self._h()).status_code, 200)

    def test_bad_schedule_is_rejected(self):
        self.assertEqual(self.client.post("/api/v1/reports/schedules",
                                          json={"kind": "csat", "recipients": []},
                                          headers=self._h()).status_code, 400)


if __name__ == "__main__":
    unittest.main()
