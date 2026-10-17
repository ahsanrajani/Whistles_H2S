"""P2.7 — per-source collection scheduling.

Each source runs on its declared cadence; Bright Data comment sources decay
(hourly < 24h, daily 24h–7d, then off) so the per-record spend stays bounded.
"""
import json
import unittest
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa

from collection import schedule
from core import sources
from db.repositories import scheduled_task, source_state

from ._db import DbTestCase


class DueSourcesTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.commit()
        self.s = self.db.session
        self.now = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)

    def _ran(self, source, when):
        self.s.execute(sa.text(
            "INSERT INTO source_state(workspace_id, source, last_attempt_at) "
            "VALUES (1, :src, :t) "
            "ON CONFLICT (workspace_id, source) DO UPDATE SET last_attempt_at = :t"),
            {"src": source, "t": when})
        self.db.commit()

    def _post(self, surface, published_at, iid=None):
        iid = iid or (hash((surface, str(published_at))) & 0xffff) + 1000
        self.db.execute(
            """INSERT INTO item(id,workspace_id,surface,source,source_kind,external_id,
               raw_json,collected_at,content_hash,published_at)
               VALUES (?,1,?,'x','licensed',?,?,'now',?,?)""",
            (iid, surface, str(iid), json.dumps({"kind": "post"}), str(iid),
             published_at.isoformat()))
        self.db.commit()

    def _due(self):
        return set(schedule.due_sources(self.s, 1, now=self.now))

    def test_never_run_sources_are_all_due(self):
        due = self._due()
        self.assertIn("googlenews_rss", due)
        self.assertNotIn("brightdata_facebook_comments", due)   # decay: no posts
        self.assertNotIn("huggingface_sentiment", due)          # cadence 0

    def test_recently_run_source_is_not_due(self):
        self._ran("googlenews_rss", self.now - timedelta(minutes=5))
        self.assertNotIn("googlenews_rss", self._due())

    def test_source_past_its_cadence_is_due_again(self):
        cad = sources.SOURCES["googlenews_rss"]["cadence"]
        self._ran("googlenews_rss", self.now - timedelta(seconds=cad + 60))
        self.assertIn("googlenews_rss", self._due())

    def test_comments_hourly_while_a_post_is_fresh(self):
        self._post("facebook", self.now - timedelta(hours=2))
        self.assertIn("brightdata_facebook_comments", self._due())

    def test_comments_daily_tier_when_the_post_is_a_few_days_old(self):
        self._post("facebook", self.now - timedelta(days=3))
        self._ran("brightdata_facebook_comments", self.now - timedelta(hours=2))
        self.assertNotIn("brightdata_facebook_comments", self._due())   # < 1 day
        self._ran("brightdata_facebook_comments", self.now - timedelta(hours=30))
        self.assertIn("brightdata_facebook_comments", self._due())      # >= 1 day

    def test_comments_stop_once_every_post_is_older_than_a_week(self):
        self._post("facebook", self.now - timedelta(days=9))
        self.assertNotIn("brightdata_facebook_comments", self._due())

    def test_a_disabled_source_is_never_due(self):
        self.assertIn("googlenews_rss", self._due())
        source_state.set_enabled(self.s, 1, "googlenews_rss", False)
        self.db.commit()
        self.assertNotIn("googlenews_rss", self._due())

    def test_re_enabling_brings_the_source_back(self):
        source_state.set_enabled(self.s, 1, "googlenews_rss", False)
        self.db.commit()
        self.assertNotIn("googlenews_rss", self._due())
        source_state.set_enabled(self.s, 1, "googlenews_rss", True)
        self.db.commit()
        self.assertIn("googlenews_rss", self._due())

    def test_the_opt_out_is_per_workspace(self):
        self.s.execute(sa.text(
            "INSERT INTO workspace(id,name,market,created_at) "
            "VALUES (2,'WS2','PK','now')"))
        source_state.set_enabled(self.s, 1, "googlenews_rss", False)
        self.db.commit()
        self.assertNotIn("googlenews_rss", set(schedule.due_sources(self.s, 1, now=self.now)))
        self.assertIn("googlenews_rss", set(schedule.due_sources(self.s, 2, now=self.now)))


class WorkspaceTickTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.commit()

    def test_registers_one_idempotent_tick(self):
        schedule.ensure_workspace_tick(self.db.session, 1)
        schedule.ensure_workspace_tick(self.db.session, 1)
        self.db.commit()
        rows = [dict(r) for r in scheduled_task.all_tasks(self.db.session)]
        ticks = [r for r in rows if r["name"] == "collection-tick:1"]
        self.assertEqual(len(ticks), 1)
        self.assertEqual(ticks[0]["kind"], "collection_tick")
        self.assertEqual(ticks[0]["cron"], "*/10 * * * *")


class TickHandlerTests(unittest.TestCase):
    """Plain unittest.TestCase (not DbTestCase): app.db_operator() commits for
    real, so each test must truncate on the way out too — not just the way in
    — or it leaks committed rows into whichever test runs next."""

    def test_handler_enqueues_a_source_scoped_collection_run(self):
        import app
        from tests import truncate_all
        truncate_all()
        self.addCleanup(truncate_all)
        conn = app.db_operator()
        try:
            conn.execute(
                "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
            conn.commit()
        finally:
            conn.close()

        out = app._collection_tick_job({"ws": 1})
        self.assertTrue(out["enqueued"])
        self.assertIn("googlenews_rss", out["due"])

        conn = app.db_operator()
        try:
            row = conn.execute(
                "SELECT kind, payload FROM job WHERE kind='collection' ORDER BY id DESC "
                "LIMIT 1").fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row[1]["run_id"], out["run_id"])

    def test_a_successful_collection_run_auto_bridges_new_care_cases(self):
        # so a real comment collected on a scheduled tick doesn't sit
        # invisible to Care until someone remembers to trigger the bridge.
        import uuid
        from unittest.mock import patch

        import app
        from db import repositories as repo
        from tests import truncate_all
        truncate_all()
        self.addCleanup(truncate_all)
        conn = app.db_operator()
        try:
            conn.execute(
                "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
            conn.commit()
            run_id = uuid.uuid4().hex[:12]
            repo.runs.create(conn.session, run_id=run_id, workspace_id=1, started_at=app.now())
            conn.commit()
        finally:
            conn.close()

        with patch("app.collector.run_collection", return_value=0), \
             patch("app.care_bridge.backfill",
                  return_value={"scanned": 1, "created": 1}) as bridge:
            app._worker(run_id, 1, only_sources=["googlenews_rss"])
        bridge.assert_called_once()
        self.assertEqual(bridge.call_args.kwargs.get("actor"), "system")

    def test_a_failed_collection_run_does_not_call_the_bridge(self):
        import uuid
        from unittest.mock import patch

        import app
        from db import repositories as repo
        from tests import truncate_all
        truncate_all()
        self.addCleanup(truncate_all)
        conn = app.db_operator()
        try:
            conn.execute(
                "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
            conn.commit()
            run_id = uuid.uuid4().hex[:12]
            repo.runs.create(conn.session, run_id=run_id, workspace_id=1, started_at=app.now())
            conn.commit()
        finally:
            conn.close()

        with patch("app.collector.run_collection", side_effect=RuntimeError("boom")), \
             patch("app.care_bridge.backfill") as bridge:
            with self.assertRaises(RuntimeError):
                app._worker(run_id, 1, only_sources=["googlenews_rss"])
        bridge.assert_not_called()

    def test_a_successful_collection_run_also_syncs_dms(self):
        # "how soon do live messages come in" -- Messenger/Instagram DMs are
        # a separate inbox from public comments (needs pages_messaging /
        # instagram_manage_messages, granted 2026-09-10) and need their own
        # sync, same posture as the care bridge: best-effort, every run.
        import uuid
        from unittest.mock import patch

        import app
        from db import repositories as repo
        from tests import truncate_all
        truncate_all()
        self.addCleanup(truncate_all)
        conn = app.db_operator()
        try:
            conn.execute(
                "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
            conn.commit()
            run_id = uuid.uuid4().hex[:12]
            repo.runs.create(conn.session, run_id=run_id, workspace_id=1, started_at=app.now())
            conn.commit()
        finally:
            conn.close()

        with patch("app.collector.run_collection", return_value=0), \
             patch("app.care_bridge.backfill", return_value={"scanned": 0, "created": 0}), \
             patch("app.dm_sync.sync",
                  return_value={"messenger": {"scanned": 1, "ingested": 1},
                                "instagram": {"scanned": 0, "ingested": 0}}) as dm:
            app._worker(run_id, 1, only_sources=["googlenews_rss"])
        dm.assert_called_once()
        self.assertEqual(dm.call_args.args[1], 1)   # workspace_id

    def test_a_failed_collection_run_does_not_call_dm_sync(self):
        import uuid
        from unittest.mock import patch

        import app
        from db import repositories as repo
        from tests import truncate_all
        truncate_all()
        self.addCleanup(truncate_all)
        conn = app.db_operator()
        try:
            conn.execute(
                "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
            conn.commit()
            run_id = uuid.uuid4().hex[:12]
            repo.runs.create(conn.session, run_id=run_id, workspace_id=1, started_at=app.now())
            conn.commit()
        finally:
            conn.close()

        with patch("app.collector.run_collection", side_effect=RuntimeError("boom")), \
             patch("app.dm_sync.sync") as dm:
            with self.assertRaises(RuntimeError):
                app._worker(run_id, 1, only_sources=["googlenews_rss"])
        dm.assert_not_called()

    def test_a_dm_sync_failure_does_not_fail_the_collection_run(self):
        import uuid
        from unittest.mock import patch

        import app
        from db import repositories as repo
        from tests import truncate_all
        truncate_all()
        self.addCleanup(truncate_all)
        conn = app.db_operator()
        try:
            conn.execute(
                "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
            conn.commit()
            run_id = uuid.uuid4().hex[:12]
            repo.runs.create(conn.session, run_id=run_id, workspace_id=1, started_at=app.now())
            conn.commit()
        finally:
            conn.close()

        with patch("app.collector.run_collection", return_value=0), \
             patch("app.care_bridge.backfill", return_value={"scanned": 0, "created": 0}), \
             patch("app.dm_sync.sync", side_effect=RuntimeError("no creds")):
            app._worker(run_id, 1, only_sources=["googlenews_rss"])   # must not raise
        conn = app.db_operator()
        try:
            state = conn.execute(
                "SELECT state FROM run WHERE id=?", (run_id,)).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(state, "done")

    def test_scheduled_dm_sync_job_skips_without_meta_creds(self):
        """A workspace with no Meta credentials must not raise -- a raise is
        retried 5x, every minute, and floods the single worker."""
        from unittest.mock import patch

        import app
        with patch("app.keys", return_value={}), patch("app.dm_sync.sync") as dm:
            out = app._dm_sync_job({"ws": 1})
        dm.assert_not_called()
        self.assertEqual(out, {"skipped": "Meta credentials not configured"})

    def test_a_running_run_in_one_workspace_does_not_starve_another(self):
        """P2.7 regression: Chase's collection_tick was silently skipped every
        cycle because Bank Alfalah's run held a GLOBAL "already running" lock
        (repo.runs.running_id had no workspace filter). Two workspaces on the
        same */10 cron must collect independently."""
        import app
        from db.repositories import runs
        from tests import truncate_all
        truncate_all()
        self.addCleanup(truncate_all)
        conn = app.db_operator()
        try:
            for wid in (1, 2):
                conn.execute(
                    "INSERT INTO workspace(id,name,market,created_at) "
                    "VALUES (?,?,'PK','now')", (wid, f"WS{wid}"))
            runs.create(conn.session, run_id="bafl-run", workspace_id=1,
                       started_at=app.now())
            conn.commit()
        finally:
            conn.close()

        out = app._collection_tick_job({"ws": 2})
        self.assertTrue(out["enqueued"], out)
        self.assertIn("googlenews_rss", out["due"])
        truncate_all()


if __name__ == "__main__":
    unittest.main()
