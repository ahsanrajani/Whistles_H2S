"""P1.8 — the scheduler.

A tick enqueues a job for every due ``scheduled_task`` row and advances its
``next_run`` off the cron expression. The exit criterion: when two schedulers
tick at the same instant, only one does the pass — the other cannot take the
Postgres transaction advisory lock and no-ops.
"""
import json
import threading
import unittest
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa

from db.session import OperatorSession
from jobs import cron, runner, scheduler
from jobs.scheduler import LOCK_KEY

from . import owner_engine


class CronTests(unittest.TestCase):
    def test_star_matches_any_minute(self):
        self.assertTrue(cron.matches("* * * * *", datetime(2026, 9, 3, 14, 7)))

    def test_specific_minute_and_hour(self):
        c = cron.parse("30 9 * * *")
        self.assertTrue(c.matches(datetime(2026, 9, 3, 9, 30)))
        self.assertFalse(c.matches(datetime(2026, 9, 3, 9, 31)))
        self.assertFalse(c.matches(datetime(2026, 9, 3, 10, 30)))

    def test_step_range_and_list(self):
        self.assertEqual(cron.parse("*/15 * * * *").minute, {0, 15, 30, 45})
        self.assertEqual(cron.parse("0 9-17 * * *").hour, set(range(9, 18)))
        self.assertEqual(cron.parse("0 0 1,15 * *").dom, {1, 15})

    def test_next_after_rolls_to_tomorrow(self):
        nxt = cron.next_after("0 3 * * *",
                              datetime(2026, 9, 3, 5, 0, tzinfo=timezone.utc))
        self.assertEqual(nxt, datetime(2026, 9, 4, 3, 0, tzinfo=timezone.utc))

    def test_next_after_preserves_tzinfo_and_is_strict(self):
        base = datetime(2026, 9, 3, 3, 0, tzinfo=timezone.utc)
        nxt = cron.next_after("0 3 * * *", base)          # already a match -> next day
        self.assertEqual(nxt, base + timedelta(days=1))

    def test_day_of_week_sunday_is_zero(self):
        c = cron.parse("0 0 * * 0")
        sunday = datetime(2026, 9, 1)
        while sunday.weekday() != 6:                      # 6 == Sunday for datetime
            sunday += timedelta(days=1)
        self.assertTrue(c.matches(sunday.replace(hour=0, minute=0)))
        self.assertFalse(c.matches((sunday + timedelta(days=1)).replace(hour=0, minute=0)))

    def test_rejects_malformed_expressions(self):
        for bad in ("* * * *", "* * * * * *", "60 * * * *", "* 24 * * *",
                    "bogus * * * *", "5-1 * * * *"):
            with self.assertRaises(ValueError):
                cron.parse(bad)


class SchedulerTickTests(unittest.TestCase):
    def setUp(self):
        self._wipe()
        self.s = OperatorSession()
        # LIFO: _wipe registered first so it runs *last* — after self.s is
        # closed and has released its ACCESS SHARE locks, so the TRUNCATE
        # inside _wipe can't block on this session's open read transaction.
        self.addCleanup(self._wipe)
        self.addCleanup(self.s.close)

    @staticmethod
    def _wipe():
        with owner_engine.begin() as c:
            c.execute(sa.text("TRUNCATE scheduled_task RESTART IDENTITY"))
            c.execute(sa.text("TRUNCATE job RESTART IDENTITY"))

    def _add(self, name, cron_expr, *, next_run, kind="collection",
             enabled=1, payload=None, tenant_id=None):
        self.s.execute(sa.text("""
            INSERT INTO scheduled_task (name, kind, cron, payload, next_run, enabled, tenant_id)
            VALUES (:n, :k, :c, CAST(:p AS jsonb), :nr, :e, :t)
        """), {"n": name, "k": kind, "c": cron_expr, "p": json.dumps(payload or {}),
               "nr": next_run, "e": enabled, "t": tenant_id})
        self.s.commit()

    def _jobs(self):
        self.s.expire_all()
        return self.s.execute(sa.text(
            "SELECT kind, payload, tenant_id, state FROM job ORDER BY id")).mappings().all()

    def _task(self, name):
        return self.s.execute(sa.text(
            "SELECT last_run, next_run FROM scheduled_task WHERE name = :n"),
            {"n": name}).one()

    def test_due_task_enqueues_a_job_and_advances_next_run(self):
        past = datetime.now(timezone.utc) - timedelta(minutes=1)
        self._add("nightly", "0 3 * * *", next_run=past, kind="collection",
                  payload={"ws": 1}, tenant_id=1)

        out = scheduler.tick(self.s)
        self.s.commit()

        self.assertEqual([name for name, _ in out], ["nightly"])
        jobs = self._jobs()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["kind"], "collection")
        self.assertEqual(jobs[0]["payload"], {"ws": 1})
        self.assertEqual(jobs[0]["tenant_id"], 1)
        self.assertEqual(jobs[0]["state"], "queued")

        row = self._task("nightly")
        self.assertIsNotNone(row.last_run)
        self.assertGreater(row.next_run, datetime.now(timezone.utc))

    def test_task_not_yet_due_is_left_alone(self):
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        self._add("later", "* * * * *", next_run=future)
        self.assertEqual(scheduler.tick(self.s), [])
        self.s.commit()
        self.assertEqual(self._jobs(), [])

    def test_disabled_task_is_skipped(self):
        past = datetime.now(timezone.utc) - timedelta(minutes=1)
        self._add("paused", "* * * * *", next_run=past, enabled=0)
        self.assertEqual(scheduler.tick(self.s), [])
        self.s.commit()
        self.assertEqual(self._jobs(), [])

    def test_a_second_tick_does_not_re_enqueue(self):
        past = datetime.now(timezone.utc) - timedelta(minutes=1)
        self._add("nightly", "0 3 * * *", next_run=past)
        scheduler.tick(self.s)
        self.s.commit()
        scheduler.tick(self.s)               # next_run is now in the future
        self.s.commit()
        self.assertEqual(len(self._jobs()), 1)

    def test_identical_pending_job_is_not_stacked_but_next_run_advances(self):
        past = datetime.now(timezone.utc) - timedelta(minutes=1)
        self._add("poll", "* * * * *", next_run=past, kind="dm_sync",
                  payload={"ws": 2}, tenant_id=2)
        scheduler.tick(self.s)
        self.s.commit()
        self.s.execute(sa.text("UPDATE scheduled_task SET next_run = :p"), {"p": past})
        self.s.commit()

        out = scheduler.tick(self.s)         # first job still queued
        self.s.commit()

        self.assertEqual(out, [("poll", None)])
        self.assertEqual(len(self._jobs()), 1)
        self.assertGreater(self._task("poll").next_run, datetime.now(timezone.utc))

    def test_a_finished_job_does_not_block_the_next_one(self):
        past = datetime.now(timezone.utc) - timedelta(minutes=1)
        self._add("poll", "* * * * *", next_run=past, kind="dm_sync",
                  payload={"ws": 2}, tenant_id=2)
        scheduler.tick(self.s)
        self.s.execute(sa.text("UPDATE job SET state = 'dead'"))
        self.s.execute(sa.text("UPDATE scheduled_task SET next_run = :p"), {"p": past})
        self.s.commit()
        scheduler.tick(self.s)
        self.s.commit()
        self.assertEqual(len(self._jobs()), 2)

    def test_runner_schedule_registers_and_is_idempotent_on_name(self):
        first = runner.schedule(self.s, "collect-hourly", "0 * * * *", "collection",
                                {"ws": 2}, tenant_id=2)
        self.s.commit()
        again = runner.schedule(self.s, "collect-hourly", "*/30 * * * *", "collection",
                                {"ws": 2}, tenant_id=2)
        self.s.commit()
        self.assertEqual(first, again)
        row = self.s.execute(sa.text(
            "SELECT cron, kind FROM scheduled_task WHERE name = 'collect-hourly'")).one()
        self.assertEqual(row.cron, "*/30 * * * *")

    def test_only_one_of_two_concurrent_ticks_runs(self):
        past = datetime.now(timezone.utc) - timedelta(minutes=1)
        self._add("dup", "* * * * *", next_run=past, kind="collection")

        # A second connection holds the advisory lock with an open transaction.
        holder = OperatorSession()
        self.addCleanup(holder.close)
        holder.execute(sa.text("SELECT pg_advisory_xact_lock(:k)"), {"k": LOCK_KEY})

        blocked = scheduler.tick(self.s)
        self.s.commit()
        self.assertIsNone(blocked)                        # lock not acquired -> no-op
        self.assertEqual(self._jobs(), [])

        holder.rollback()                                 # releases the xact lock
        ran = scheduler.tick(self.s)
        self.s.commit()
        self.assertEqual(len(ran), 1)
        self.assertEqual(len(self._jobs()), 1)

    def test_run_pending_serialises_across_threads(self):
        past = datetime.now(timezone.utc) - timedelta(minutes=1)
        self._add("dup", "* * * * *", next_run=past, kind="collection")

        results: list = []

        def go():
            results.append(scheduler.run_pending())

        threads = [threading.Thread(target=go) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        enqueued = [r for r in results if r]              # non-None, non-empty
        self.assertEqual(sum(len(r) for r in enqueued), 1)
        self.assertEqual(len(self._jobs()), 1)


if __name__ == "__main__":
    unittest.main()
