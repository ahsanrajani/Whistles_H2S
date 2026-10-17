import unittest

from ._db import DbTestCase
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core import incidents

ROOT = Path(__file__).resolve().parents[1]


def _day(offset):
    return (datetime.now(timezone.utc) - timedelta(days=offset)).strftime("%Y-%m-%dT12:00:00Z")


class MeanStdevTests(unittest.TestCase):
    def test_sample_stdev(self):
        mean, stdev = incidents._mean_stdev([2, 4, 4, 4, 5, 5, 7, 9])
        self.assertEqual(mean, 5.0)
        self.assertAlmostEqual(stdev, 2.138, places=2)

    def test_keyword_hits_are_deduped_and_sorted(self):
        self.assertEqual(incidents._keyword_hits("APP CRASH and another app crash, plus outage"),
                         ["app crash", "outage"])


class ScanTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.execute(
            "INSERT INTO brand(id,workspace_id,name,is_focus) VALUES (1,1,'Focus Bank',1)")
        self.db.execute(
            "INSERT INTO brand(id,workspace_id,name,is_focus) VALUES (2,1,'Rival Bank',0)")
        self._iid = self._mid = 0


    def _mention(self, brand_id, body, offset):
        self._iid += 1
        self._mid += 1
        self.db.execute(
            """INSERT INTO item(id,workspace_id,surface,source,source_kind,external_id,
                                url,outlet,published_at,body,raw_json,collected_at,content_hash)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (self._iid, 1, "x", "x_recent", "licensed", f"e{self._iid}",
             f"https://x/{self._iid}", "Wire", _day(offset), body, "{}", "now",
             f"h{self._iid}"))
        self.db.execute(
            "INSERT INTO mention(id,item_id,brand_id,rule) VALUES (?,?,?,?)",
            (self._mid, self._iid, brand_id, "x_search"))
        self.db.commit()

    def _baseline(self, brand_id, per_day=1):
        for offset in range(6, 22):                 # inside the baseline window
            for _ in range(per_day):
                self._mention(brand_id, "normal chatter about the bank", offset)

    def test_keyword_gated_spike_is_an_incident(self):
        self._baseline(1)
        self._baseline(2)
        for n in range(8):                          # spike 2 days ago for the rival
            body = "the app crash outage is back" if n < 4 else "just a normal comment"
            self._mention(2, body, 2)

        report = incidents.scan(self.db, 1)

        by_name = {b["brand"]: b for b in report["brands"]}
        rival = by_name["Rival Bank"]
        self.assertEqual(rival["status"], "incident")
        self.assertEqual(report["incident_count"], 1)
        self.assertEqual(len(rival["incidents"]), 1)
        inc = rival["incidents"][0]
        self.assertEqual(inc["date"], _day(2)[:10])
        self.assertGreaterEqual(inc["z"], report["params"]["z_threshold"])
        self.assertEqual(inc["keyword_share"], 0.5)
        self.assertIn("outage", inc["keywords"])
        self.assertTrue(inc["gated_in"])
        self.assertEqual(by_name["Focus Bank"]["status"], "normal")
        self.assertEqual(report["params"]["baseline_days"], 28)
        self.assertIn("outage", report["lexicon"])

    def test_spike_without_keywords_is_only_elevated(self):
        self._baseline(1)
        for _ in range(9):
            self._mention(1, "great new campaign everyone loves it", 1)

        report = incidents.scan(self.db, 1)
        focus = next(b for b in report["brands"] if b["brand"] == "Focus Bank")
        self.assertEqual(focus["status"], "elevated")
        self.assertEqual(report["incident_count"], 0)
        self.assertEqual(len(focus["incidents"]), 1)
        self.assertFalse(focus["incidents"][0]["gated_in"])

    def test_small_spike_below_min_count_is_normal(self):
        self._baseline(1)
        for _ in range(3):                          # below _MIN_COUNT
            self._mention(1, "app crash outage", 1)

        report = incidents.scan(self.db, 1)
        focus = next(b for b in report["brands"] if b["brand"] == "Focus Bank")
        self.assertEqual(focus["incidents"], [])
        self.assertEqual(focus["status"], "normal")

    def test_series_covers_the_full_lookback(self):
        self._baseline(1)
        report = incidents.scan(self.db, 1)
        focus = next(b for b in report["brands"] if b["brand"] == "Focus Bank")
        self.assertEqual(len(focus["series"]), report["params"]["lookback_days"])
        self.assertEqual(len(report["axis"]), report["params"]["lookback_days"])


if __name__ == "__main__":
    unittest.main()
