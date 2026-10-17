"""P3.8 — scheduled messages, block/unblock audit fields, case export.

Exit criterion: a scheduled message dispatches at its time via the job system
(the scheduled_task row is in Postgres, so a restart cannot lose it).
"""
import unittest
from datetime import datetime, timedelta, timezone

from jobs import scheduler

from ._db import ApiTestCase


class CareSchedulingApiTests(ApiTestCase):
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

    def _case(self):
        return self._post("/api/v1/care/cases/ingest",
                          {"platform": "x", "handle": "@c", "body": "help"}
                          ).get_json()["case_id"]

    # --- scheduling --------------------------------------------------
    def test_scheduled_message_dispatches_via_the_job_system(self):
        cid = self._case()
        past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        resp = self._post(f"/api/v1/care/cases/{cid}/schedule",
                          {"text": "Following up as promised", "platform": "x",
                           "target_ref": "dm:1", "at": past})
        self.assertEqual(resp.status_code, 200)
        aid = resp.get_json()["outbound_action_id"]

        conn = self.app.db_operator()
        try:
            # the timer is a persisted scheduled_task row (survives a restart)
            row = conn.execute("SELECT once, enabled FROM scheduled_task "
                               "WHERE name = ?", (f"send:{aid}",)).fetchone()
            self.assertEqual(row, (1, 1))
            self.assertEqual(conn.execute("SELECT state FROM outbound_action WHERE id=?",
                                          (aid,)).fetchone()[0], "pending")
        finally:
            conn.close()

        # the scheduler fires the one-shot -> enqueues send_scheduled ->
        # (drain it) -> the message is delivered
        import app
        scheduler.run_pending(now=datetime.now(timezone.utc))
        from jobs import worker
        for _ in range(4):
            if not worker.run_one(kinds=["send_scheduled"]):
                break

        conn = self.app.db_operator()
        try:
            state = conn.execute("SELECT state FROM outbound_action WHERE id=?",
                                 (aid,)).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(state, "sent")
        detail = self.client.get(f"/api/v1/care/cases/{cid}").get_json()
        self.assertTrue([m for m in detail["messages"] if m["direction"] == "outbound"])

    # --- block / unblock -----------------------------------------
    def test_block_requires_reason_and_category(self):
        cid = self._case()
        self.assertEqual(
            self._post(f"/api/v1/care/cases/{cid}/block",
                       {"target_ref": "u:1", "platform": "x"}).status_code, 400)
        ok = self._post(f"/api/v1/care/cases/{cid}/block",
                        {"target_ref": "u:1", "platform": "x",
                         "reason": "repeated abuse", "category": "harassment"})
        self.assertEqual(ok.status_code, 200)

        conn = self.app.db_operator()
        try:
            ev = conn.execute("SELECT action, after_state FROM audit_event "
                              "WHERE action='care.block' ORDER BY id DESC LIMIT 1").fetchone()
        finally:
            conn.close()
        self.assertEqual(ev[0], "care.block")
        self.assertIn("harassment", ev[1])

    # --- export ----------------------------------------------------
    def test_export_pdf_and_xlsx(self):
        cid = self._case()
        pdf = self.client.get(f"/api/v1/care/cases/{cid}/export?format=pdf")
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.get_data().startswith(b"%PDF"))

        xl = self.client.get(f"/api/v1/care/cases/{cid}/export?format=xlsx")
        self.assertEqual(xl.status_code, 200)
        self.assertTrue(xl.get_data().startswith(b"PK"))     # xlsx is a zip

    def test_export_unknown_case_404(self):
        self.assertEqual(
            self.client.get("/api/v1/care/cases/999999/export").status_code, 404)


if __name__ == "__main__":
    unittest.main()
