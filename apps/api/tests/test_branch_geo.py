import unittest

from ._db import DbTestCase
from pathlib import Path

from core import branch_geo

ROOT = Path(__file__).resolve().parents[1]


class CatalogTests(unittest.TestCase):
    def test_real_branches_load_with_coordinates(self):
        cat = branch_geo.catalog()
        self.assertGreater(len(cat), 1000)                 # ~1,186 real branches
        for row in cat[:20]:
            self.assertTrue(row["code"])
            self.assertTrue(row["name"])
            self.assertIsInstance(row["lat"], float)
            self.assertIsInstance(row["lng"], float)
            self.assertTrue(24 < row["lat"] < 37)           # Pakistan's latitude band
            self.assertTrue(60 < row["lng"] < 78)

    def test_a_known_analysis_branch_is_in_the_real_catalog(self):
        # 0442 = Bahria Town Phase 7, Rawalpindi in core/branches.py's alias table.
        codes = {row["code"] for row in branch_geo.catalog()}
        self.assertIn("0442", codes)

    def test_cached_across_calls(self):
        self.assertIs(branch_geo.catalog(), branch_geo.catalog())


class WithPerformanceTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.execute(
            "INSERT INTO brand(id,workspace_id,name,is_focus) VALUES (1,1,'Bank Alfalah',1)")
        self.db.commit()


    def test_unscored_branches_come_back_with_a_none_band(self):
        merged = branch_geo.with_performance(self.db, 1)
        self.assertEqual(len(merged), len(branch_geo.catalog()))
        # 0004 (Federal B Area Karachi) isn't in core/branches.py's ~20-branch
        # alias table, so it should come back with no performance data.
        sample = next(row for row in merged if row["code"] == "0004")
        self.assertIsNone(sample["key"])
        self.assertEqual(sample["band"], "none")
        self.assertEqual(sample["score"], 0)

    def test_a_scored_branch_carries_its_branch_perf_numbers(self):
        for i in range(6):
            self.db.execute(
                """INSERT INTO item(id,workspace_id,surface,source,source_kind,external_id,
                                    url,outlet,published_at,body,rating,raw_json,collected_at,
                                    content_hash)
                   VALUES (?,1,'branch_review','google_maps_reviews','licensed',?,?,?,?,?,?,?,?,?)""",
                (i + 1, f"e{i}", f"https://x/{i}", "Google Maps",
                 "2026-08-01T09:00:00Z", "ATM out of cash again, unacceptable.", 1,
                 '{"branch_key": "bahria-ph7-rwp"}', "now", f"h{i}"))
            self.db.execute(
                "INSERT INTO mention(id,item_id,brand_id,rule) VALUES (?,?,1,'branch_seed')",
                (i + 1, i + 1))
            self.db.execute(
                """INSERT INTO sentiment(mention_id,label,model_id,scored_lang,scored_at)
                   VALUES (?,?,?,?,?)""", (i + 1, "neg", "seed", "en", "now"))
            self.db.execute(
                """INSERT INTO mention_class(mention_id,category,model_id,classified_at)
                   VALUES (?,?,?,?)""", (i + 1, "complaint", "seed", "now"))
        self.db.commit()

        merged = branch_geo.with_performance(self.db, 1)
        bahria = next(row for row in merged if row["code"] == "0442")
        self.assertEqual(bahria["key"], "bahria-ph7-rwp")
        self.assertIn(bahria["band"], ("high", "elevated"))
        self.assertGreater(bahria["score"], 0)
        self.assertEqual(bahria["reviews"], 6)


if __name__ == "__main__":
    unittest.main()


class OwnLocationsTests(DbTestCase):
    """A workspace with `location` rows is plotted from them, never from the
    Bank Alfalah CSV; only rows with coordinates are plotted."""

    def setUp(self):
        super().setUp()
        from db.repositories import locations
        self.db.execute("INSERT INTO workspace(id,name,market,created_at) VALUES (1,'J','PK','now')")
        self.db.execute("INSERT INTO workspace(id,name,market,created_at) VALUES (2,'B','PK','now')")
        self.db.commit()
        locations.upsert_many(self.db.session, 1, [
            {"key": "a", "name": "A", "city": "Karachi", "lat": 24.8, "lng": 67.0,
             "geo_precision": "street", "source": "website"},
            {"key": "b", "name": "B", "city": "Lahore", "source": "website"},   # no coords
        ])
        self.db.commit()

    def test_own_rows_with_coordinates_only(self):
        merged = branch_geo.with_performance(self.db, 1)
        self.assertEqual([r["code"] for r in merged], ["a"])
        self.assertEqual(merged[0]["precision"], "street")
        self.assertEqual(merged[0]["band"], "none")

    def test_workspace_without_locations_keeps_the_csv_catalog(self):
        self.assertEqual(len(branch_geo.with_performance(self.db, 2)), len(branch_geo.catalog()))
