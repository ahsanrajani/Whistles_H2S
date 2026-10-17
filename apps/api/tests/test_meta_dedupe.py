"""P2.5 — where a post exists from both the Graph API and Bright Data, the
Graph (``source_class = official``) row is canonical and the scrape folds onto
it, even when the scrape has the lower id.
"""
import hashlib
import unittest

from collection import simhash as sh
from core import collector

from ._db import DbTestCase

_DOC = (
    "Our customer support hours are extending from next Monday. Branches in the "
    "three largest cities will now open at eight in the morning and the phone "
    "line will run until midnight on weekdays. Weekend chat support is unchanged. "
    "We are hiring more agents and expect wait times to fall over the coming "
    "weeks as the new team completes training and comes online.")


def _hashes(title, body):
    text = collector.norm(" ".join(filter(None, [title, body])))
    return hashlib.sha256(text.encode()).hexdigest()[:32], sh.simhash(text)


class GraphWinsDedupeTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.commit()
        self._id = 0

    def _insert(self, *, source, source_class, title, body, external_id=None):
        self._id += 1
        ch, simhash = _hashes(title, body)
        self.db.execute(
            """INSERT INTO item
               (id,workspace_id,surface,source,source_kind,external_id,outlet,title,body,
                lang_guess,raw_json,collected_at,content_hash,simhash,source_class)
               VALUES (?,1,'facebook',?,'licensed',?,'Facebook',?,?,'en','{}','now',?,?,?)""",
            (self._id, source, external_id or f"e{self._id}", title, body, ch,
             simhash, source_class))
        self.db.commit()
        return self._id

    def _edges(self):
        return self.db.execute(
            "SELECT item_id, canonical_id, method FROM dupe_edge WHERE workspace_id=1"
        ).fetchall()

    def _dedupe(self):
        collector.dedupe(self.db, 1, lambda _m: None)

    def test_scrape_folds_onto_the_graph_row_on_identical_content(self):
        scrape = self._insert(source="brightdata_facebook_posts",
                              source_class="third_party",
                              title="Support hours", body=_DOC)      # lower id
        graph = self._insert(source="meta_facebook", source_class="official",
                             title="Support hours", body=_DOC)       # higher id
        self._dedupe()
        self.assertEqual(self._edges(), [(scrape, graph, "content_hash")])

    def test_graph_wins_via_simhash_when_text_differs_slightly(self):
        scrape = self._insert(source="brightdata_facebook_posts",
                              source_class="third_party", title="Hours update",
                              body=_DOC.replace("eight", "8"))
        graph = self._insert(source="meta_facebook", source_class="official",
                             title="Extended support hours", body=_DOC)
        self._dedupe()
        edges = self._edges()
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0][:2], (scrape, graph))

    def test_no_official_row_falls_back_to_lowest_id(self):
        a = self._insert(source="brightdata_facebook_posts", source_class="third_party",
                         title="Support hours", body=_DOC)
        b = self._insert(source="dataforseo_serp", source_class="third_party",
                         title="Support hours", body=_DOC)
        self._dedupe()
        self.assertEqual(self._edges(), [(b, a, "content_hash")])

    def test_two_official_rows_fold_to_the_earliest(self):
        a = self._insert(source="meta_facebook", source_class="official",
                         title="Support hours", body=_DOC)
        b = self._insert(source="meta_instagram", source_class="official",
                         title="Support hours", body=_DOC)
        self._dedupe()
        self.assertEqual(self._edges(), [(b, a, "content_hash")])


if __name__ == "__main__":
    unittest.main()
