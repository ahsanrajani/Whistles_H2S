"""`location` table + repo + the Jubilee importer's row shape."""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, "scripts")))

import seed_jubilee_locations as seed  # noqa: E402
from db.repositories import locations as repo  # noqa: E402
from ._db import DbTestCase  # noqa: E402


class SeedRowTests(unittest.TestCase):
    def test_keys_unique_and_client_coordinates_all_land(self):
        rows = seed.build_rows()
        keys = [r["key"] for r in rows]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(sum(1 for r in rows if r["lat"] is not None), len(seed.XLSX))

    def test_website_rows_never_invent_coordinates(self):
        for r in seed.build_rows():
            if r["source"] == "website":
                self.assertIsNone(r["lat"])
                self.assertIsNone(r["lng"])

    def test_twin_merges_keep_the_website_address(self):
        row = next(r for r in seed.build_rows() if r["name"] == "Ayesha Manzil (Galaxy Branch)")
        self.assertEqual(row["lat"], 24.9271287)
        self.assertIn("Anar Kali", row["address"])

    def test_no_atms(self):
        self.assertFalse(any(r["kind"] == "atm" for r in seed.build_rows()))


class LocationRepoTests(DbTestCase):
    def setUp(self):
        super().setUp()
        for i in (1, 2):
            self.db.execute("INSERT INTO workspace(id,name,market,created_at) "
                            f"VALUES ({i},'W{i}','PK','now')")
        self.db.commit()

    def test_upsert_never_erases_a_known_coordinate_and_is_tenant_scoped(self):
        s = self.db.session
        repo.upsert_many(s, 1, [{"key": "a", "name": "A", "lat": 1.5, "lng": 2.5}])
        repo.upsert_many(s, 1, [{"key": "a", "name": "A renamed", "address": "x"}])
        repo.upsert_many(s, 2, [{"key": "a", "name": "Other"}])
        rows = repo.list_all(s, 1)
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["name"], rows[0]["lat"], rows[0]["lng"], rows[0]["address"]),
                         ("A renamed", 1.5, 2.5, "x"))
        self.assertEqual(repo.list_all(s, 2)[0]["name"], "Other")
        self.assertEqual(repo.list_all(s, 1, kind="atm"), [])

    def test_google_reviews_import_rates_location_and_skips_rating_only_and_excluded(self):
        from core import google_reviews_import as gri
        s = self.db.session
        self.db.execute("INSERT INTO brand(workspace_id,name,is_focus,active) VALUES (1,'B',1,1)")
        self.db.commit()
        bid = self.db.execute("SELECT id FROM brand WHERE workspace_id=1").fetchone()[0]
        repo.upsert_many(s, 1, [{"key": "a", "name": "A"}, {"key": "b", "name": "B"}])
        base = {"maps_link": "https://maps/x", "approx_review_date": "2026-01-02"}
        rows = [
            {**base, "place_id": "P1", "branch_rating": "3.5", "branch_review_count": "40",
             "review_id": "r1", "star_rating": "1", "review_text": "claim rejected"},
            {**base, "place_id": "P1", "branch_rating": "3.5", "branch_review_count": "40",
             "review_id": "r2", "star_rating": "5", "review_text": ""},
            {**base, "place_id": "P2", "branch_rating": "", "branch_review_count": "",
             "review_id": "r3", "star_rating": "5", "review_text": "promo"},
        ]
        st = gri.import_reviews(s, 1, bid, rows, {"P1": "a", "P2": "b"}, exclude={"P2"})
        self.assertEqual((st["reviews"], st["rating_only"], st["excluded"]), (1, 1, 1))
        got = {r["key"]: r for r in repo.list_all(s, 1)}
        self.assertEqual((got["a"]["rating"], got["a"]["review_count"], got["a"]["place_id"]),
                         (3.5, 40, "P1"))
        self.assertIsNone(got["b"]["rating"])          # unknown stays null
        st2 = gri.import_reviews(s, 1, bid, rows, {"P1": "a", "P2": "b"}, exclude={"P2"})
        self.assertEqual(st2["reviews"], 0)            # idempotent

    def test_location_enrichment_preserves_pins_and_blank_ratings(self):
        from core import location_enrichment_import as enrichment
        s = self.db.session
        repo.upsert_many(s, 1, [
            {"key": "pinned", "name": "Pinned", "lat": 1.5, "lng": 2.5},
            {"key": "missing", "name": "Missing"},
        ])
        rows = [
            {"key": "pinned", "google_place_id": "P1",
             "google_match_status": "verified_exact_address",
             "google_latitude": "9.1", "google_longitude": "9.2",
             "google_rating": "", "google_review_count": ""},
            {"key": "missing", "google_place_id": "P2",
             "google_match_status": "probable_exact_location",
             "google_latitude": "3.1", "google_longitude": "3.2",
             "google_rating": "4.2", "google_review_count": "19",
             "google_checked_at": "2026-09-25T00:00:00Z"},
            {"key": "ignored", "google_place_id": "P3",
             "google_match_status": "no_exact_match_found"},
        ]
        stats = enrichment.import_rows(s, 1, rows, apply=True)
        self.assertEqual(
            (stats["accepted"], stats["rated"], stats["pins_filled"],
             stats["skipped_unverified"], stats["unknown_keys"]),
            (2, 1, 1, 1, []))
        got = {r["key"]: r for r in repo.list_all(s, 1)}
        self.assertEqual((got["pinned"]["lat"], got["pinned"]["lng"]), (1.5, 2.5))
        self.assertEqual(got["pinned"]["place_id"], "P1")
        self.assertIsNone(got["pinned"]["rating"])
        self.assertEqual(
            (got["missing"]["lat"], got["missing"]["lng"],
             got["missing"]["rating"], got["missing"]["review_count"]),
            (3.1, 3.2, 4.2, 19))

    def test_mentions_import_surfaces_dates_and_shared_urls(self):
        from core import mentions_import as mi
        self.assertEqual(mi.surface_for("Facebook - Voice Of Customer")[0], "facebook")
        self.assertEqual(mi.surface_for("LinkedIn comment")[0], "linkedin")
        self.assertEqual(mi.surface_for("Pakistan Case Law / Peshawar High Court record")[0], "regulatory")
        self.db.execute("INSERT INTO brand(workspace_id,name,is_focus,active) VALUES (1,'B',1,1)")
        self.db.commit()
        bid = self.db.execute("SELECT id FROM brand WHERE workspace_id=1").fetchone()[0]
        recs = [{"post_text": "bad claim service", "source": "LinkedIn comment", "name": "A",
                 "date": None, "link": "https://x/post"},
                {"post_text": "no payout received", "source": "LinkedIn comment", "name": "B",
                 "date": "2026-01-02", "link": "https://x/post"},
                {"post_text": "skip me", "source": "Trustpilot", "link": "https://tp/1"}]
        res = mi.import_mentions(self.db.session, 1, bid, recs, skip_links={"https://tp/1"})
        self.assertEqual((res["inserted"], res["skipped"]), (2, 1))
        urls = [r[0] for r in self.db.execute("SELECT url FROM item WHERE workspace_id=1").fetchall()]
        self.assertEqual(len(set(urls)), 2)
        self.assertEqual(mi.import_mentions(self.db.session, 1, bid, recs, skip_links={"https://tp/1"})["duplicate"], 2)


if __name__ == "__main__":
    unittest.main()
