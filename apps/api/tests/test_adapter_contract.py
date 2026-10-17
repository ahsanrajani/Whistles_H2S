"""P2.2 — adapter contract v2: token bucket, circuit breaker, source_state.

The circuit-breaker exit criterion: 5 consecutive failures open it; it
half-opens after the cooldown and closes on the next success.
"""
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from core import collector, sources
from integrations.adapters.contract import (CLOSED, HALF_OPEN, OPEN,
                                            SOURCE_CLASSES, CircuitBreaker,
                                            CURSOR_KINDS, TokenBucket, bucket_for)

from ._db import DbTestCase


class _Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


class TokenBucketTests(unittest.TestCase):
    def test_starts_full_and_drains(self):
        clock = _Clock()
        b = TokenBucket(per_second=10, burst=3, clock=clock)
        self.assertTrue(b.try_take())
        self.assertTrue(b.try_take())
        self.assertTrue(b.try_take())
        self.assertFalse(b.try_take())

    def test_refills_over_time(self):
        clock = _Clock()
        b = TokenBucket(per_second=2, burst=2, clock=clock)
        self.assertTrue(b.try_take(2))
        self.assertFalse(b.try_take())
        clock.advance(1.0)                 # +2 tokens/s * 1s
        self.assertTrue(b.try_take())
        self.assertTrue(b.try_take())
        self.assertFalse(b.try_take())

    def test_take_blocks_until_available(self):
        clock = _Clock()
        b = TokenBucket(per_second=100, burst=1, clock=clock)
        self.assertTrue(b.try_take())
        slept = []

        def fake_sleep(s):
            slept.append(s)
            clock.advance(s)

        waited = b.take(1, sleep=fake_sleep)
        self.assertGreater(waited, 0)
        self.assertTrue(slept)

    def test_bucket_for_none_is_none(self):
        self.assertIsNone(bucket_for(None))
        self.assertIsInstance(bucket_for({"per_second": 1}), TokenBucket)


class CircuitBreakerTests(unittest.TestCase):
    def _breaker(self, clock=None):
        return CircuitBreaker(fail_threshold=5, cooldown_seconds=300,
                              clock=clock or _Clock())

    def test_opens_after_five_consecutive_failures(self):
        cb = self._breaker()
        for _ in range(4):
            cb.record_failure()
            self.assertTrue(cb.allow())
            self.assertEqual(cb.state, CLOSED)
        cb.record_failure()
        self.assertEqual(cb.state, OPEN)
        self.assertFalse(cb.allow())

    def test_success_resets_the_failure_count(self):
        cb = self._breaker()
        for _ in range(4):
            cb.record_failure()
        cb.record_success()
        for _ in range(4):
            cb.record_failure()
        self.assertEqual(cb.state, CLOSED)
        self.assertTrue(cb.allow())

    def test_half_opens_after_cooldown_then_closes_on_success(self):
        clock = _Clock()
        cb = self._breaker(clock)
        for _ in range(5):
            cb.record_failure()
        self.assertFalse(cb.allow())
        clock.advance(300)
        self.assertTrue(cb.allow())
        self.assertEqual(cb.state, HALF_OPEN)
        cb.record_success()
        self.assertEqual(cb.state, CLOSED)
        self.assertTrue(cb.allow())

    def test_failure_while_half_open_reopens_immediately(self):
        clock = _Clock()
        cb = self._breaker(clock)
        for _ in range(5):
            cb.record_failure()
        clock.advance(301)
        self.assertTrue(cb.allow())          # half-open trial
        cb.record_failure()
        self.assertEqual(cb.state, OPEN)
        self.assertFalse(cb.allow())         # clock not advanced -> still open

    def test_snapshot_restore_round_trip(self):
        clock = _Clock()
        cb = self._breaker(clock)
        for _ in range(5):
            cb.record_failure()
        restored = CircuitBreaker.restore(cb.snapshot(), fail_threshold=5,
                                          cooldown_seconds=300, clock=clock)
        self.assertEqual(restored.state, OPEN)
        self.assertFalse(restored.allow())
        clock.advance(300)
        self.assertTrue(restored.allow())


class ContractCompletenessTests(unittest.TestCase):
    def test_every_source_declares_the_v2_contract(self):
        for sid, meta in sources.SOURCES.items():
            with self.subTest(source=sid):
                self.assertIsInstance(meta["cadence"], int)
                self.assertGreaterEqual(meta["cadence"], 0)
                self.assertIn(meta["cursor"], CURSOR_KINDS)
                self.assertIn(meta["source_class"], SOURCE_CLASSES)
                rl = meta["rate_limit"]
                self.assertTrue(rl is None or ("per_second" in rl))

    def test_platform_apis_are_official(self):
        for sid in ("meta_facebook", "meta_instagram", "appstore_reviews",
                    "playstore_reviews", "google_maps_reviews"):
            self.assertEqual(sources.SOURCES[sid]["source_class"], "official")

    def test_scrapers_are_third_party(self):
        for sid in ("googlenews_rss", "arctic_shift", "dataforseo_serp",
                    "brightdata_facebook_posts", "x_recent"):
            self.assertEqual(sources.SOURCES[sid]["source_class"], "third_party")


class _StubAdapter(collector.Adapter):
    ID = "googlenews_rss"          # borrow an existing, credential-free source
    raised = False
    yielded = False

    def available(self):
        return True

    def fetch(self, terms):
        type(self).yielded = True
        if type(self).raised:
            raise RuntimeError("stub boom")
        return iter(())


class SourceStateRepoTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.commit()

    def test_save_and_load_round_trip(self):
        from db.repositories import source_state
        opened = datetime.now(timezone.utc).timestamp()
        source_state.save(self.db.session, 1, "googlenews_rss",
                          cursor_kind="timestamp", cursor_value="2026-09-01T00:00:00Z",
                          circuit_state=OPEN, consecutive_failures=5,
                          opened_at=opened, last_error="boom")
        self.db.commit()
        row = source_state.load(self.db.session, 1, "googlenews_rss")
        self.assertEqual(row["cursor_value"], "2026-09-01T00:00:00Z")
        self.assertEqual(row["circuit_state"], OPEN)
        self.assertEqual(row["consecutive_failures"], 5)
        self.assertAlmostEqual(row["opened_at"], opened, delta=1.0)
        self.assertIsNone(source_state.load(self.db.session, 1, "nope"))


class CircuitInRunCollectionTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.execute(
            "INSERT INTO brand(id,workspace_id,name,is_focus) VALUES (1,1,'Acme',1)")
        self.db.commit()
        _StubAdapter.raised = False
        _StubAdapter.yielded = False

    def _run(self):
        lines = []
        collector.run_collection(self.db, 1, "run-x", {}, lines.append)
        return lines

    @patch("core.collector.sentiment.score_pending", return_value={})
    @patch("core.collector.REGISTRY", [_StubAdapter])
    def test_open_circuit_skips_the_adapter(self, *_):
        self.db.execute("""
            INSERT INTO source_state(workspace_id, source, circuit_state,
                consecutive_failures, opened_at)
            VALUES (1, 'googlenews_rss', 'open', 5, now())""")
        self.db.commit()
        lines = self._run()
        self.assertFalse(_StubAdapter.yielded)
        self.assertTrue(any("circuit open" in ln for ln in lines))

    @patch("core.collector.sentiment.score_pending", return_value={})
    @patch("core.collector.REGISTRY", [_StubAdapter])
    def test_a_source_disabled_for_the_workspace_is_skipped(self, *_):
        from db.repositories import source_state
        source_state.set_enabled(self.db.session, 1, "googlenews_rss", False)
        self.db.commit()
        lines = self._run()
        self.assertFalse(_StubAdapter.yielded)
        self.assertTrue(any("disabled for this workspace" in ln for ln in lines))

    @patch("core.collector.sentiment.score_pending", return_value={})
    @patch("core.collector.REGISTRY", [_StubAdapter])
    def test_a_clean_run_records_success(self, *_):
        self._run()
        row = self.db.execute(
            "SELECT circuit_state, consecutive_failures, last_success_at "
            "FROM source_state WHERE source='googlenews_rss'").fetchone()
        self.assertEqual(row[0], "closed")
        self.assertEqual(row[1], 0)
        self.assertIsNotNone(row[2])

    @patch("core.collector.sentiment.score_pending", return_value={})
    @patch("core.collector.REGISTRY", [_StubAdapter])
    def test_five_failing_runs_open_the_circuit(self, *_):
        _StubAdapter.raised = True
        for _ in range(5):
            self._run()
        row = self.db.execute(
            "SELECT circuit_state, consecutive_failures, last_error "
            "FROM source_state WHERE source='googlenews_rss'").fetchone()
        self.assertEqual(row[0], "open")
        self.assertEqual(row[1], 5)
        self.assertIn("boom", row[2])


if __name__ == "__main__":
    unittest.main()
