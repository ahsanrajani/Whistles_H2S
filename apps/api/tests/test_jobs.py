"""P1.7a — the Postgres job queue.

Claim-once semantics, exponential backoff, the dead-letter state, and — the
exit criterion — a job whose worker died is reclaimed and finished by another,
not lost.
"""
import threading
import time
import unittest

import sqlalchemy as sa

import app as _app
from db.session import OperatorSession
from jobs import queue, runner, worker

from . import owner_engine
from ._db import ApiTestCase


class JobQueueTests(unittest.TestCase):
    def setUp(self):
        with owner_engine.begin() as c:
            c.execute(sa.text("TRUNCATE job RESTART IDENTITY"))
        self.s = OperatorSession()

    def tearDown(self):
        self.s.close()
        for kind in ("echo", "boom", "count"):
            worker._HANDLERS.pop(kind, None)
        with owner_engine.begin() as c:
            c.execute(sa.text("TRUNCATE job RESTART IDENTITY"))

    def _commit(self):
        self.s.commit()

    def _get(self, jid):
        self.s.expire_all()
        return queue.get(self.s, jid)

    # --- queue mechanics --------------------------------------------------
    def test_enqueue_creates_a_queued_job(self):
        jid = runner.enqueue(self.s, "echo", {"n": 1})
        self._commit()
        row = self._get(jid)
        self.assertEqual(row["state"], "queued")
        self.assertEqual(row["attempts"], 0)
        self.assertEqual(row["payload"], {"n": 1})

    def test_claim_marks_running_and_bumps_attempts(self):
        jid = runner.enqueue(self.s, "echo", {})
        self._commit()
        row = queue.claim(self.s, "w1")
        self._commit()
        self.assertEqual(row["id"], jid)
        self.assertEqual(row["state"], "running")
        self.assertEqual(row["attempts"], 1)
        self.assertEqual(row["locked_by"], "w1")

    def test_a_running_job_is_not_re_claimed_before_the_reclaim_window(self):
        runner.enqueue(self.s, "echo", {})
        self._commit()
        self.assertIsNotNone(queue.claim(self.s, "w1"))
        self._commit()
        self.assertIsNone(queue.claim(self.s, "w2"))

    def test_complete_marks_done_and_stores_the_result(self):
        jid = runner.enqueue(self.s, "echo", {})
        self._commit()
        queue.claim(self.s, "w1")
        self._commit()
        queue.complete(self.s, jid, {"ok": True})
        self._commit()
        self.assertEqual(self._get(jid)["state"], "done")
        self.assertEqual(self._get(jid)["result"], {"ok": True})

    def test_fail_backs_off_and_requeues(self):
        jid = runner.enqueue(self.s, "echo", {}, max_attempts=3)
        self._commit()
        queue.claim(self.s, "w1")
        self._commit()
        queue.fail(self.s, jid, "boom")
        self._commit()
        row = self._get(jid)
        self.assertEqual(row["state"], "queued")
        self.assertEqual(row["last_error"], "boom")
        self.assertIsNone(queue.claim(self.s, "w2"))         # run_after is in the future

    def test_dead_letter_after_max_attempts(self):
        jid = runner.enqueue(self.s, "echo", {}, max_attempts=2)
        self._commit()
        for _ in range(2):
            self.assertIsNotNone(queue.claim(self.s, "w1"))
            self._commit()
            queue.fail(self.s, jid, "boom", base_seconds=0)
            self._commit()
        self.assertEqual(self._get(jid)["state"], "dead")
        self.assertIsNone(queue.claim(self.s, "w1"))

    def test_a_job_whose_worker_died_is_reclaimed(self):
        jid = runner.enqueue(self.s, "echo", {})
        self._commit()
        first = queue.claim(self.s, "worker-A")
        self._commit()
        self.assertEqual(first["attempts"], 1)
        # worker-A dies mid-run: its lock goes stale
        self.s.execute(sa.text(
            "UPDATE job SET locked_at = now() - interval '10 minutes' WHERE id=:i"),
            {"i": jid})
        self._commit()
        again = queue.claim(self.s, "worker-B", reclaim_after_seconds=300)
        self._commit()
        self.assertEqual(again["id"], jid)
        self.assertEqual(again["attempts"], 2)
        self.assertEqual(again["locked_by"], "worker-B")

    # --- worker.run_one --------------------------------------------------
    def test_run_one_executes_the_registered_handler(self):
        worker.handler("echo")(lambda payload: {"echoed": payload})
        jid = runner.enqueue(self.s, "echo", {"hi": 5})
        self._commit()
        self.assertTrue(worker.run_one("w1", kinds=["echo"]))
        row = self._get(jid)
        self.assertEqual(row["state"], "done")
        self.assertEqual(row["result"], {"echoed": {"hi": 5}})

    def test_run_one_routes_a_raising_handler_to_dead_letter(self):
        def boom(_payload):
            raise RuntimeError("kaboom")
        worker.handler("boom")(boom)
        jid = runner.enqueue(self.s, "boom", {}, max_attempts=1)
        self._commit()
        self.assertTrue(worker.run_one("w1", kinds=["boom"]))
        row = self._get(jid)
        self.assertEqual(row["state"], "dead")
        self.assertIn("kaboom", row["last_error"])

    def test_run_one_on_an_empty_queue_returns_false(self):
        self.assertFalse(worker.run_one("w1"))

    def test_two_workers_never_run_the_same_job(self):
        ran = []
        worker.handler("count")(lambda payload: ran.append(1))
        runner.enqueue(self.s, "count", {})
        self._commit()

        def drain():
            for _ in range(20):
                if not worker.run_one(kinds=["count"]):
                    time.sleep(0.02)

        threads = [threading.Thread(target=drain) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        self.assertEqual(sum(ran), 1)


class JobRouteWiringTests(ApiTestCase):
    """The kick-off routes enqueue onto the `job` table instead of spawning threads."""

    def _login_admin(self):
        self.client.post("/api/v1/auth/login",
                         json={"username": "admin", "password": "admin123"},
                         headers={"X-CSRF-Token": self.client.get("/api/v1/csrf").get_json()["token"]})
        with self.client.session_transaction() as s:
            return s.get("csrf_token")

    def _jobs(self):
        connection = self.app.db_operator()
        try:
            return connection.execute(
                "SELECT kind, payload, state, max_attempts FROM job ORDER BY id").fetchall()
        finally:
            connection.close()

    def test_score_route_enqueues_a_scoring_job(self):
        token = self._login_admin()
        resp = self.client.post("/api/v1/jobs/score", json={"reset": True},
                                headers={"X-CSRF-Token": token})
        self.assertEqual(resp.status_code, 200)
        rows = self._jobs()
        self.assertEqual([r[0] for r in rows], ["scoring"])
        self.assertEqual(rows[0][1]["handle"], resp.get_json()["job_id"])
        self.assertTrue(rows[0][1]["reset"])
        self.assertEqual(rows[0][2], "queued")

    def test_refresh_route_enqueues_a_collection_job_with_one_attempt(self):
        token = self._login_admin()
        resp = self.client.post("/api/v1/jobs/refresh", headers={"X-CSRF-Token": token})
        self.assertEqual(resp.status_code, 200)
        rows = self._jobs()
        self.assertEqual([r[0] for r in rows], ["collection"])
        self.assertEqual(rows[0][1]["run_id"], resp.get_json()["job_id"])
        self.assertEqual(rows[0][3], 1)

    def test_a_running_run_in_another_workspace_does_not_block_refresh(self):
        """P2.7 regression — see db/repositories/runs.py::running_id."""
        from db.repositories import runs
        connection = self.app.db_operator()
        try:
            connection.execute(
                "INSERT INTO workspace(id,name,market,created_at) "
                "VALUES (2,'Other','PK','now')")
            runs.create(connection.session, run_id="other-ws-run", workspace_id=2,
                       started_at=_app.now())
            connection.commit()
        finally:
            connection.close()

        token = self._login_admin()                    # admin's own ws is 1
        resp = self.client.post("/api/v1/jobs/refresh", headers={"X-CSRF-Token": token})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.get_json().get("already"))
        self.assertEqual([r[0] for r in self._jobs()], ["collection"])


if __name__ == "__main__":
    unittest.main()
