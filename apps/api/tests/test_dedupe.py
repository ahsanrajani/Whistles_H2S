"""P2.1 — dedupe no longer folds on URL.

Identity is `(source, external_id)` (enforced at INSERT); the dedupe pass folds
only a story that genuinely arrives twice — byte-identical text, a feed
re-collected under a rotated id, or a near-verbatim re-report from another
source. Two items that merely share a URL are kept apart.
"""
import hashlib
import unittest

from collection import simhash as sh
from core import collector

from ._db import DbTestCase


def _hashes(title, body):
    text = collector.norm(" ".join(filter(None, [title, body])))
    return hashlib.sha256(text.encode()).hexdigest()[:32], sh.simhash(text)


class DedupeTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.commit()
        self._next_id = 1

    def _insert(self, *, source, external_id, url, title, body, outlet="Outlet"):
        content_hash, simhash = _hashes(title, body)
        iid = self._next_id
        self._next_id += 1
        self.db.execute(
            """INSERT INTO item
               (id,workspace_id,surface,source,source_kind,external_id,url,outlet,
                title,body,lang_guess,raw_json,collected_at,content_hash,simhash)
               VALUES (?,1,'news',?,'public',?,?,?,?,?,'en','{}','now',?,?)""",
            (iid, source, external_id, url, outlet, title, body, content_hash, simhash))
        self.db.commit()
        return iid

    def _edges(self):
        return self.db.execute(
            "SELECT item_id, canonical_id, method FROM dupe_edge WHERE workspace_id=1"
        ).fetchall()

    def _dedupe(self):
        collector.dedupe(self.db, 1, lambda _m: None)

    # --- the exit criterion ------------------------------------------------
    def test_hundred_items_sharing_a_base_url_all_survive(self):
        for n in range(100):
            self._insert(source="googlenews_rss", external_id=f"g{n}",
                         url="https://example.com/story",
                         title=f"Headline number {n}",
                         body=f"Distinct body text for item {n}, "
                              f"with its own words {n} {n * 7} {n * 13}.")
        self._dedupe()
        self.assertEqual(self._edges(), [])

    # --- what should still fold ------------------------------------------
    def test_byte_identical_text_folds_on_content_hash(self):
        a = self._insert(source="src_a", external_id="a1", url="https://a/1",
                         title="Same story", body="Exactly the same words here.")
        b = self._insert(source="src_b", external_id="b1", url="https://b/2",
                         title="Same story", body="Exactly the same words here.")
        self._dedupe()
        edges = self._edges()
        self.assertEqual(edges, [(b, a, "content_hash")])

    def test_rotated_feed_id_folds_on_normalised_title(self):
        a = self._insert(source="googlenews_rss", external_id="old", url="https://n/old",
                         title="Bank raises deposit rates", body="First crawl body.")
        b = self._insert(source="googlenews_rss", external_id="new", url="https://n/new",
                         title="  bank raises DEPOSIT rates ",
                         body="A totally different second-crawl body paragraph.")
        self._dedupe()
        self.assertIn((b, a, "norm_title"), self._edges())

    _ARTICLE = (
        "The central bank today announced a fresh round of monetary tightening, "
        "raising the policy rate by fifty basis points and signalling further "
        "increases through the rest of the quarter, citing persistent core "
        "inflation and a weaker exchange rate. Analysts had widely expected the "
        "move after last week inflation print came in above forecasts, though a "
        "minority had argued for a larger increase given currency pressure. The "
        "bank said it would remain data dependent and stood ready to act again "
        "if price expectations did not ease. Commercial lenders are expected to "
        "reprice deposits and loans within days.")

    def test_near_verbatim_from_another_source_folds_on_simhash(self):
        # distinct titles + outlets + a body differing by one token: only the
        # SimHash pass can catch this.
        a = self._insert(source="wire_a", external_id="a", url="https://a/x",
                         outlet="Wire A", title="Central bank tightens again",
                         body=self._ARTICLE)
        b = self._insert(source="wire_b", external_id="b", url="https://b/y",
                         outlet="Wire B", title="Policy rate up 50bps",
                         body=self._ARTICLE.replace("fifty", "50"))
        self._dedupe()
        self.assertEqual(self._edges(), [(b, a, "simhash")])

    def test_short_items_never_fold_on_simhash(self):
        # below MIN_TOKENS the hash is 0 and the pass skips them (distinct bodies
        # so content_hash / norm_title don't fold them either)
        for n in range(5):
            self._insert(source=f"s{n}", external_id=str(n), url="https://s/x",
                         title=f"Review {n}",
                         body=f"Quick and friendly staff at branch {n} on visit {n * 3}.")
        self._dedupe()
        self.assertEqual(self._edges(), [])

    def test_unrelated_text_is_not_folded(self):
        self._insert(source="s1", external_id="1", url="https://s/1",
                     title="Quarterly earnings beat expectations",
                     body="Revenue rose on strong retail lending and fee income.")
        self._insert(source="s2", external_id="2", url="https://s/1",
                     title="Branch network expansion in the south",
                     body="Twelve new outlets opened across three provinces this month.")
        self._dedupe()
        self.assertEqual(self._edges(), [])


class SimhashUnitTests(unittest.TestCase):
    def test_identical_text_same_hash_distance_zero(self):
        h = sh.simhash("the quick brown fox jumps over the lazy dog")
        self.assertEqual(sh.hamming(h, h), 0)

    _DOC = (
        "The central bank today announced a fresh round of monetary tightening, "
        "raising the policy rate by fifty basis points and signalling further "
        "increases through the rest of the quarter, citing persistent core "
        "inflation and a weaker exchange rate. Analysts had widely expected the "
        "move after last week inflation print came in above forecasts, though a "
        "minority had argued for a larger increase given currency pressure. The "
        "bank said it would remain data dependent and stood ready to act again "
        "if price expectations did not ease. Commercial lenders are expected to "
        "reprice deposits and loans within days, and equity markets slipped on "
        "the news before recovering by the close of trading.")

    def test_small_edit_of_a_document_is_close(self):
        a = sh.simhash(self._DOC)
        b = sh.simhash(self._DOC.replace("fifty", "50"))
        self.assertLessEqual(sh.hamming(a, b), sh.NEAR_DUP_MAX_DISTANCE)

    def test_different_documents_are_far(self):
        other = (
            "A new flagship branch opened downtown this morning with extended "
            "weekend hours, a dedicated business banking floor and a self service "
            "lounge. The outlet is the latest in a network expansion that has "
            "added twelve branches across three provinces since the start of the "
            "year. Management said the format focuses on advisory services rather "
            "than teller transactions, with more digital kiosks and fewer "
            "counters. Two more openings are planned before the quarter ends.")
        self.assertGreater(sh.hamming(sh.simhash(self._DOC), sh.simhash(other)),
                           sh.NEAR_DUP_MAX_DISTANCE)

    def test_short_text_hashes_to_zero(self):
        self.assertEqual(sh.simhash("quick and friendly staff at the branch today"), 0)

    def test_empty_text_hashes_to_zero(self):
        self.assertEqual(sh.simhash("   "), 0)

    def test_hash_fits_signed_bigint(self):
        h = sh.simhash("some ordinary sentence of several words in a row here")
        self.assertGreaterEqual(h, 0)
        self.assertLess(h, 2 ** 63)


if __name__ == "__main__":
    unittest.main()
