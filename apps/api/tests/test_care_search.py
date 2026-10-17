"""P3.9 — cross-entity care search / autocomplete."""
import unittest

import sqlalchemy as sa

from core import cases, care_search

from ._db import DbTestCase


class CareSearchTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.commit()
        self.s = self.db.session
        self.cid = cases.ingest_message(
            self.s, 1, platform="x", handle="@ayeshak", display_name="Ayesha Khan",
            email="ayesha.khan@example.com", phone="03001234567",
            body="My debit card keeps getting declined at the ATM near Gulberg")["case_id"]
        cases.ingest_message(self.s, 1, platform="facebook", handle="bilal.fb",
                             display_name="Bilal Ahmed",
                             body="Loan repayment schedule question")
        self.db.commit()

    def _search(self, q, limit=10):
        return care_search.search(self.s, 1, q, limit=limit)["results"]

    def test_name_lookup(self):
        r = self._search("ayesha")
        self.assertTrue(any(x["type"] == "customer" and "Ayesha" in x["label"] for x in r))

    def test_handle_lookup(self):
        self.assertTrue(any(x["type"] == "customer" for x in self._search("ayeshak")))

    def test_email_lookup(self):
        self.assertTrue(any(x["type"] == "customer" for x in self._search("ayesha.khan@example")))

    def test_phone_lookup(self):
        self.assertTrue(any(x["type"] == "customer" for x in self._search("0300123")))

    def test_case_reference_lookup(self):
        r = self._search(f"C-{self.cid}")
        self.assertEqual(r[0]["type"], "case")
        self.assertEqual(r[0]["case_id"], self.cid)

    def test_bare_multi_digit_number_resolves_a_case(self):
        # open cases until the id has >= 2 digits, then search the bare number
        cid = self.cid
        while cid < 10:
            cid = cases.ingest_message(self.s, 1, platform="x", handle=f"@z{cid}",
                                       body="x")["case_id"]
        self.db.commit()
        self.assertTrue(any(x["type"] == "case" for x in self._search(str(cid))))

    def test_message_body_full_text(self):
        r = self._search("declined ATM Gulberg")
        self.assertTrue(any(x["type"] == "message" and x["case_id"] == self.cid for x in r))

    def test_short_query_returns_nothing(self):
        self.assertEqual(self._search("a"), [])

    def test_fuzzy_typo_still_matches_a_name(self):
        # trigram similarity tolerates a small typo
        self.assertTrue(any(x["type"] == "customer" for x in self._search("ayesa khan")))

    def test_the_expected_indexes_exist(self):
        idx = {r[0] for r in self.s.execute(sa.text(
            "SELECT indexname FROM pg_indexes WHERE tablename IN ('customer','case_message')"
        )).all()}
        self.assertIn("ix_customer_trgm_handle", idx)
        self.assertIn("ix_customer_trgm_email", idx)
        self.assertIn("ix_case_message_fts", idx)


if __name__ == "__main__":
    unittest.main()
