"""Per-workspace branch resolver, insurance vocabulary and the vertical rule."""
import unittest

from core import branch_perf, branch_resolver, branches, places_lookup, product_lines, vertical
from db.repositories import locations
from ._db import DbTestCase

ROWS = [
    {"key": "johar-town-lahore", "kind": "branch", "name": "Johar Town, Lahore",
     "city": "Lahore", "address": "Block G, Johar Town, Lahore"},
    {"key": "gulberg-lahore", "kind": "branch", "name": "Gulberg Branch", "city": "Lahore",
     "address": "MM Alam Road, Gulberg III, Lahore"},
    {"key": "chitral", "kind": "branch", "name": "Chitral Branch", "city": "Chitral", "address": None},
    {"key": "atm-1", "kind": "atm", "name": "Some ATM", "city": "Lahore", "address": None},
]


class ResolverTests(unittest.TestCase):
    def setUp(self):
        self.r = branch_resolver.from_locations(ROWS)

    def test_name_and_city_resolve(self):
        self.assertEqual(self.r.resolve("Terrible service at Johar Town branch in Lahore")[0],
                         "johar-town-lahore")
        self.assertEqual(self.r.resolve("the Chitral branch never answers")[0], "chitral")

    def test_a_bare_city_is_never_enough(self):
        self.assertIsNone(self.r.resolve("I live in Lahore and want a policy"))

    def test_atms_are_not_branches(self):
        self.assertNotIn("atm-1", [e[0] for e in self.r.entries])

    def test_bank_alfalah_default_is_unchanged(self):
        self.assertEqual(len(branches.catalog()), len(branches.BRANCHES))
        self.assertEqual(branches.resolve("Bahria Town Phase 7 Rawalpindi branch")[0], "bahria-ph7-rwp")

    def test_exact_name_match(self):
        self.assertEqual(self.r.resolve_by_name("Gulberg Branch")[1], "exact_name")


class VerticalTests(unittest.TestCase):
    def test_rule(self):
        self.assertEqual(vertical.of_name("Jubilee Life Insurance"), "insurance")
        self.assertEqual(vertical.of_name("Bank Alfalah"), "banking")
        self.assertEqual(vertical.of_name(None), "banking")

    def test_insurance_lines_and_issues(self):
        self.assertIn("claims", product_lines.classify_text("my claim was rejected", "insurance"))
        self.assertIn("surrender", product_lines.classify_text("surrender value was tiny", "insurance"))
        self.assertEqual(product_lines.classify_text("my claim was rejected"), [])
        self.assertIn("claim_delay", branch_perf._issue_hits("claim rejected again", "insurance"))
        self.assertNotIn("atm_cash", [k for k, _l, _r in branch_perf._COMPILED_BY["insurance"]])


class PlacesLookupTests(unittest.TestCase):
    def test_only_a_jubilee_listing_near_the_city_is_accepted(self):
        centre = (24.86, 67.0)
        good = {"id": "P1", "displayName": {"text": "Jubilee Life Insurance - Saddar"},
                "location": {"latitude": 24.85, "longitude": 67.02}}
        other = {"id": "P2", "displayName": {"text": "Habib Bank"},
                 "location": {"latitude": 24.85, "longitude": 67.02}}
        far = {"id": "P3", "displayName": {"text": "Jubilee Life Insurance"},
               "location": {"latitude": 31.5, "longitude": 74.3}}
        self.assertEqual(places_lookup._accept([other, far, good], "Karachi", centre)[2], "P1")
        self.assertIsNone(places_lookup._accept([other, far], "Karachi", centre))


class WorkspacePerfTests(DbTestCase):
    def test_workspace_with_locations_gets_its_own_catalogue(self):
        self.db.execute("INSERT INTO workspace(id,name,market,created_at) VALUES (1,'J','PK','now')")
        self.db.commit()
        locations.upsert_many(self.db.session, 1, [
            {"key": "chitral", "name": "Chitral Branch", "city": "Chitral"}])
        self.db.commit()
        self.assertEqual([e[0] for e in branch_resolver.for_workspace(self.db, 1).entries], ["chitral"])
        self.assertIs(branch_resolver.for_workspace(self.db, 99), branches.DEFAULT)
        report = branch_perf.scan(self.db, 1)
        self.assertEqual(report["coverage"]["branches"], 1)


if __name__ == "__main__":
    unittest.main()
