"""collection/status.py::write_status -- P2.7 per-source scheduling means most
runs are partial by design; a surface absent from `used` should carry its
last real status forward, not flip to "failed" just because this tick
didn't happen to touch it."""
import unittest

import sqlalchemy as sa

from collection.status import write_status
from db import pipeline as p

from ._db import DbTestCase


class _StubAdapter:
    def __init__(self, surface, label, *, independent=True, sampled=False):
        self.meta = {"surface": surface, "label": label, "independent": independent,
                    "sampled": sampled, "client_safe": True}


class WriteStatusTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.execute(
            "INSERT INTO run(id,workspace_id,started_at,state) "
            "VALUES ('run-1',1,'2026-09-01T00:00:00Z','done')")
        self.db.execute(
            "INSERT INTO run(id,workspace_id,started_at,state) "
            "VALUES ('run-2',1,'2026-09-02T00:00:00Z','done')")
        self.db.commit()
        self.s = self.db.session

    def _row(self, run_id, surface):
        return self.s.execute(sa.text(
            "SELECT state, note FROM surface_status "
            "WHERE run_id=:r AND workspace_id=1 AND surface=:sf"),
            {"r": run_id, "sf": surface}).first()

    def test_a_surface_not_touched_this_run_carries_its_last_state_forward(self):
        write_status(self.db, 1, "run-1", [_StubAdapter("news", "Google News RSS")], {})
        self.db.commit()
        self.assertEqual(self._row("run-1", "news").state, "collected")

        # run-2: news wasn't due this tick (per-source scheduling) -- `used`
        # doesn't include it, but it has no credential requirement at all.
        write_status(self.db, 1, "run-2", [], {})
        self.db.commit()
        self.assertEqual(self._row("run-2", "news").state, "collected")

    def test_a_surface_with_real_missing_credentials_still_shows_failed(self):
        write_status(self.db, 1, "run-1", [], {})
        self.db.commit()
        row = self._row("run-1", "facebook")
        self.assertEqual(row.state, "failed")
        self.assertIn("META_ACCESS_TOKEN", row.note)

    def test_a_credentialled_surface_never_yet_collected_is_left_off_the_ledger(self):
        # meta_facebook is credentialled here but never actually ran (not in
        # `used`, and no prior run ever collected it) -- should not appear
        # as "failed" (that would be a false negative for a working source).
        write_status(self.db, 1, "run-1", [], {"META_ACCESS_TOKEN": "t", "META_PAGE_ID": "1"})
        self.db.commit()
        self.assertIsNone(self._row("run-1", "facebook"))

    def test_latest_surface_status_picks_the_most_recent_run(self):
        write_status(self.db, 1, "run-1", [_StubAdapter("news", "Google News RSS")], {})
        self.db.commit()
        write_status(self.db, 1, "run-2",
                    [_StubAdapter("news", "Google News RSS", sampled=True)], {})
        self.db.commit()
        latest = p.latest_surface_status(self.s, 1)
        self.assertEqual(latest["news"]["state"], "sampled")


if __name__ == "__main__":
    unittest.main()
