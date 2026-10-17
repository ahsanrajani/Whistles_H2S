"""P2.4 — author identity + retention.

Exit criterion: flipping a tenant to `hashed` nulls author names and profile
URLs while preserving the salted hash, and repeat-author detection still works.
"""
import unittest

import sqlalchemy as sa

from collection import authors
from db.repositories import retention

from ._db import ApiTestCase, DbTestCase


class AuthorUpsertTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.commit()

    def _row(self, aid):
        return self.db.session.execute(sa.text(
            "SELECT name, profile_url, author_hash, retention_mode "
            "FROM item_author WHERE id = :i"), {"i": aid}).one()

    def test_full_mode_keeps_pii(self):
        aid = authors.upsert_author(self.db.session, 1, platform="reddit",
                                    name="u/someone", profile_url="https://r/u/someone",
                                    source_class="third_party", retention_mode="full",
                                    at="now")
        self.db.commit()
        name, url, h, mode = self._row(aid)
        self.assertEqual(name, "u/someone")
        self.assertEqual(url, "https://r/u/someone")
        self.assertTrue(h)
        self.assertEqual(mode, "full")

    def test_hashed_mode_drops_pii_but_keeps_the_hash(self):
        full = authors.upsert_author(self.db.session, 1, platform="x", name="@handle",
                                     source_class="third_party", retention_mode="full",
                                     at="now")
        self.db.commit()
        full_hash = self._row(full)[2]
        self.db.session.execute(sa.text("DELETE FROM item_author"))
        self.db.commit()
        hid = authors.upsert_author(self.db.session, 1, platform="x", name="@handle",
                                    source_class="third_party", retention_mode="hashed",
                                    at="now")
        self.db.commit()
        name, url, h, mode = self._row(hid)
        self.assertIsNone(name)
        self.assertIsNone(url)
        self.assertEqual(h, full_hash)          # same identity -> same hash
        self.assertEqual(mode, "hashed")

    def test_same_author_upserts_to_one_row(self):
        a = authors.upsert_author(self.db.session, 1, platform="reddit", name="Bob",
                                  retention_mode="full", at="t1")
        b = authors.upsert_author(self.db.session, 1, platform="reddit", name=" bob ",
                                  retention_mode="full", at="t2")
        self.db.commit()
        self.assertEqual(a, b)                  # name normalisation folds them

    def test_no_identity_returns_none(self):
        self.assertIsNone(authors.upsert_author(
            self.db.session, 1, platform="news", name=None, at="now"))


class RehashWorkspaceTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.commit()
        self.s = self.db.session

    def _item(self, iid, author_id, source_class):
        self.db.execute(
            """INSERT INTO item(id,workspace_id,surface,source,source_kind,external_id,
               raw_json,collected_at,content_hash,author_id,source_class)
               VALUES (?,1,'reddit','reddit_free','noncommercial',?,'{}','now',?,?,?)""",
            (iid, str(iid), str(iid), author_id, source_class))

    def test_flip_to_hashed_strips_pii_and_keeps_repeat_detection(self):
        tp = authors.upsert_author(self.s, 1, platform="reddit", name="RepeatGuy",
                                   profile_url="https://r/u/RepeatGuy",
                                   source_class="third_party", retention_mode="full",
                                   at="now")
        off = authors.upsert_author(self.s, 1, platform="facebook", name="Page Admin",
                                    source_class="official", retention_mode="full",
                                    at="now")
        self._item(1, tp, "third_party")
        self._item(2, tp, "third_party")          # same author, second item
        self._item(3, off, "official")
        self.db.commit()

        before = self.s.execute(sa.text(
            "SELECT author_hash FROM item_author WHERE id = :i"), {"i": tp}).scalar_one()

        retention.set_mode(self.s, 1, "third_party", "hashed")
        self.db.commit()
        result = authors.rehash_workspace(self.s, 1)
        self.db.commit()

        self.assertEqual(result["hashed"], 1)
        name, url, h, mode = self.s.execute(sa.text(
            "SELECT name, profile_url, author_hash, retention_mode "
            "FROM item_author WHERE id = :i"), {"i": tp}).one()
        self.assertIsNone(name)
        self.assertIsNone(url)
        self.assertEqual(h, before)              # hash unchanged
        self.assertEqual(mode, "hashed")

        # both third_party items still resolve to the one author row
        linked = self.s.execute(sa.text(
            "SELECT DISTINCT author_id FROM item WHERE id IN (1, 2)")).scalars().all()
        self.assertEqual(linked, [tp])

        # the official-class author is untouched (policy still full)
        off_name = self.s.execute(sa.text(
            "SELECT name FROM item_author WHERE id = :i"), {"i": off}).scalar_one()
        self.assertEqual(off_name, "Page Admin")

    def test_rehash_is_idempotent(self):
        tp = authors.upsert_author(self.s, 1, platform="reddit", name="X",
                                   source_class="third_party", retention_mode="full",
                                   at="now")
        retention.set_mode(self.s, 1, "third_party", "hashed")
        self.db.commit()
        self.assertEqual(authors.rehash_workspace(self.s, 1)["hashed"], 1)
        self.db.commit()
        self.assertEqual(authors.rehash_workspace(self.s, 1)["hashed"], 0)


class RetentionRepoTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.commit()

    def test_default_policy_is_full(self):
        self.assertEqual(retention.policy(self.db.session, 1),
                         {"official": "full", "third_party": "full"})

    def test_set_and_read(self):
        retention.set_mode(self.db.session, 1, "third_party", "hashed")
        self.db.commit()
        self.assertEqual(retention.policy(self.db.session, 1)["third_party"], "hashed")

    def test_rejects_bad_values(self):
        with self.assertRaises(ValueError):
            retention.set_mode(self.db.session, 1, "nonsense", "hashed")
        with self.assertRaises(ValueError):
            retention.set_mode(self.db.session, 1, "official", "deleted")


class AdminRetentionEndpointTests(ApiTestCase):
    def _login(self, user, pw):
        token = self.client.get("/api/v1/csrf").get_json()["token"]
        self.client.post("/api/v1/auth/login", json={"username": user, "password": pw},
                         headers={"X-CSRF-Token": token})
        with self.client.session_transaction() as s:
            return s.get("csrf_token", "")

    def test_get_returns_the_policy(self):
        self._login("admin", "admin123")
        body = self.client.get("/api/v1/admin/retention").get_json()
        self.assertEqual(body["policy"], {"official": "full", "third_party": "full"})

    def test_put_hashed_queues_a_rehash_job(self):
        token = self._login("admin", "admin123")
        resp = self.client.put("/api/v1/admin/retention",
                               json={"source_class": "third_party",
                                     "retention_mode": "hashed"},
                               headers={"X-CSRF-Token": token})
        self.assertEqual(resp.status_code, 200)
        self.assertIsNotNone(resp.get_json()["rehash_job"])
        conn = self.app.db_operator()
        try:
            kinds = [r[0] for r in conn.execute("SELECT kind FROM job").fetchall()]
        finally:
            conn.close()
        self.assertIn("rehash_authors", kinds)

    def test_put_rejects_a_bad_class(self):
        token = self._login("admin", "admin123")
        resp = self.client.put("/api/v1/admin/retention",
                               json={"source_class": "bogus", "retention_mode": "full"},
                               headers={"X-CSRF-Token": token})
        self.assertEqual(resp.status_code, 400)

    def test_viewer_is_forbidden(self):
        token = self._login("bank", "viewer123")
        self.assertEqual(self.client.get("/api/v1/admin/retention").status_code, 403)
        self.assertEqual(
            self.client.put("/api/v1/admin/retention",
                            json={"source_class": "official", "retention_mode": "hashed"},
                            headers={"X-CSRF-Token": token}).status_code, 403)


if __name__ == "__main__":
    unittest.main()
