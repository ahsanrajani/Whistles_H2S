import unittest

from core import insights

from ._db import ApiTestCase


class MentionsApiTests(ApiTestCase):
    """Behavioural coverage for the Mentions surface, over /api/v1/mentions."""

    def setUp(self):
        super().setUp()
        self.c = self.client
        self._seed()

    def _seed(self):
        connection = self.app.db_operator()
        focus = connection.execute(
            "SELECT id FROM brand WHERE workspace_id=1 AND is_focus=1").fetchone()[0]
        for i in range(12):
            store = "App Store" if i % 2 else "Google Play"
            connection.execute(
                """INSERT INTO item(workspace_id,surface,source,source_kind,external_id,url,
                   outlet,published_at,body,rating,lang_guess,raw_json,collected_at,content_hash)
                   VALUES(1,'app_reviews','appstore_reviews','public',?,?,?,?,?,?,'en','{}','now',?)""",
                (f"rv{i}", f"https://x/{i}", store, f"2026-08-{10 + i:02d}T09:00:00Z",
                 "app crashes on login" if i % 3 else "fast and clean", (1 if i % 3 else 5),
                 f"rvh{i}"))
            item_id = connection.execute(
                "SELECT id FROM item WHERE external_id=?", (f"rv{i}",)).fetchone()[0]
            connection.execute(
                "INSERT INTO mention(workspace_id,item_id,brand_id,rule) "
                "VALUES(1,?,?,'app_review')",
                (item_id, focus))
        for (mention_id,) in connection.execute(
                "SELECT m.id FROM mention m JOIN item i ON i.id=m.item_id "
                "WHERE i.lang_guess='en' LIMIT 40").fetchall():
            connection.execute(
                "INSERT INTO sentiment(workspace_id,mention_id,label,model_id,scored_lang,scored_at) "
                "VALUES(1,?,?,?,?,?) ON CONFLICT (mention_id) DO UPDATE SET label=EXCLUDED.label",
                (mention_id, "neg" if mention_id % 2 else "pos", "t", "en", "now"))
        connection.commit()
        connection.close()

    def _login(self, username, password):
        token = self.c.get("/api/v1/csrf").get_json()["token"]
        self.c.post("/api/v1/auth/login",
                    json={"username": username, "password": password},
                    headers={"X-CSRF-Token": token})
        with self.c.session_transaction() as session:
            self.token = session["csrf_token"]

    def _total(self, query=""):
        return self.c.get(f"/api/v1/mentions{query}").get_json()["total"]

    def test_sentiment_filter_partitions_the_set(self):
        self._login("bank", "viewer123")
        base = self._total()
        neg = self._total("?sentiment=neg")
        pos = self._total("?sentiment=pos")
        neu = self._total("?sentiment=neu")
        self.assertGreater(neg, 0)
        self.assertLess(neg, base)
        self.assertEqual(neg + pos + neu, base)

    def test_free_text_search_narrows_and_matches(self):
        self._login("bank", "viewer123")
        base = self._total()
        hits = self._total("?q=crashes")
        self.assertGreater(hits, 0)
        self.assertLess(hits, base)
        rows = self.c.get("/api/v1/mentions?q=crashes").get_json()["rows"]
        self.assertTrue(all("fast and clean" not in row["text"] for row in rows))

    def test_type_filter_narrows_the_stream(self):
        connection = self.app.db_operator()
        ids = [row[0] for row in connection.execute("SELECT id FROM mention LIMIT 3")]
        for mention_id in ids:
            connection.execute(
                """INSERT INTO mention_class
                   (workspace_id,mention_id,category,confidence,model_id,classified_at)
                   VALUES (1,?,?,?,?,?)
                   ON CONFLICT (mention_id) DO UPDATE SET category=EXCLUDED.category""", (mention_id, "complaint", 0.9, "t", "now"))
        connection.commit()
        connection.close()
        self._login("bank", "viewer123")
        self.assertEqual(self._total("?type=complaint"), 3)
        self.assertLess(self._total("?type=complaint"), self._total())

    def test_rating_band_and_sort(self):
        self._login("bank", "viewer123")
        base = self._total("?surface=app_reviews")
        high = self._total("?surface=app_reviews&rating=high")
        low = self._total("?surface=app_reviews&rating=low")
        self.assertGreater(high, 0)
        self.assertGreater(low, 0)
        self.assertEqual(high + low, base)
        # exact-star click-through (e.g. from the Reviews histogram)
        five = self._total("?surface=app_reviews&rating=5")
        one = self._total("?surface=app_reviews&rating=1")
        self.assertGreater(five, 0)
        self.assertGreater(one, 0)
        self.assertLessEqual(five, high)
        rows = self.c.get("/api/v1/mentions?surface=app_reviews&rating=1").get_json()["rows"]
        self.assertTrue(all(row["rating"] == 1 for row in rows))
        top = self.c.get("/api/v1/mentions?surface=app_reviews&sort=top").get_json()["rows"]
        bottom = self.c.get("/api/v1/mentions?surface=app_reviews&sort=low").get_json()["rows"]
        self.assertEqual(top[0]["rating"], 5)
        self.assertEqual(bottom[0]["rating"], 1)

    def test_conversation_mix_sums_to_the_mention_total(self):
        connection = self.app.db_operator()
        mix = insights.mention_mix(connection, 1)
        total = connection.execute(
            """SELECT COUNT(*) FROM mention m JOIN item i ON i.id=m.item_id
               JOIN brand b ON b.id=m.brand_id
               LEFT JOIN dupe_edge dd ON dd.item_id=i.id
               WHERE b.workspace_id=1 AND m.excluded=0 AND dd.item_id IS NULL
                     AND i.source_kind IN ('public','licensed')""").fetchone()[0]
        connection.close()
        self.assertEqual(mix["total"], total)
        self.assertEqual(sum(cat["n"] for cat in mix["cats"]), total)

    def test_comparison_story_collapses_to_one_row_with_also_names(self):
        connection = self.app.db_operator()
        focus = connection.execute(
            "SELECT id FROM brand WHERE workspace_id=1 AND is_focus=1").fetchone()[0]
        competitor = connection.execute(
            "SELECT id FROM brand WHERE workspace_id=1 AND is_focus=0 LIMIT 1").fetchone()[0]
        connection.execute(
            """INSERT INTO item(workspace_id,surface,source,source_kind,external_id,url,
               outlet,published_at,title,body,lang_guess,raw_json,collected_at,content_hash)
               VALUES(1,'news','googlenews_rss','public','cmp1','https://n/cmp1','Dawn',
               '2026-08-30T09:00:00Z','Two banks weighed against each other',
               'detail','en','{}','now','cmph1')""")
        item_id = connection.execute(
            "SELECT id FROM item WHERE external_id='cmp1'").fetchone()[0]
        for brand_id in (focus, competitor):
            connection.execute(
                "INSERT INTO mention(workspace_id,item_id,brand_id,rule) "
                "VALUES(1,?,?,'exact_name')",
                (item_id, brand_id))
        connection.commit()
        connection.close()
        self._login("bank", "viewer123")
        rows = self.c.get("/api/v1/mentions?q=weighed").get_json()["rows"]
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["other_brands"])

    def test_admin_hide_removes_a_mention_from_viewer_view_and_aggregates(self):
        connection = self.app.db_operator()
        mention_id = connection.execute("SELECT id FROM mention LIMIT 1").fetchone()[0]
        base_sov = sum(brand["n"] for brand in insights.share_of_voice(connection, 1))
        connection.close()

        self._login("admin", "admin123")
        hidden = self.c.post(f"/api/v1/mentions/{mention_id}/hide",
                             headers={"X-CSRF-Token": self.token})
        self.assertEqual(hidden.status_code, 200)

        connection = self.app.db_operator()
        self.assertEqual(
            connection.execute("SELECT hidden FROM mention WHERE id=?",
                               (mention_id,)).fetchone()[0], 1)
        self.assertEqual(
            sum(brand["n"] for brand in insights.share_of_voice(connection, 1)),
            base_sov - 1)
        connection.close()

        self._login("bank", "viewer123")
        viewer_ids = [row["id"] for row in
                      self.c.get("/api/v1/mentions").get_json()["rows"]]
        self.assertNotIn(mention_id, viewer_ids)

        self._login("admin", "admin123")
        self.c.post(f"/api/v1/mentions/{mention_id}/show",
                    headers={"X-CSRF-Token": self.token})
        connection = self.app.db_operator()
        self.assertEqual(
            connection.execute("SELECT hidden FROM mention WHERE id=?",
                               (mention_id,)).fetchone()[0], 0)
        connection.close()

    def test_review_batch_excludes_identity_rules(self):
        connection = self.app.db_operator()
        rules = {row[7] for row in insights.review_batch(connection, 1)}
        connection.close()
        self.assertNotIn("app_review", rules)

    def test_csv_export_carries_the_derived_columns(self):
        self._login("bank", "viewer123")
        response = self.c.get("/api/v1/mentions/export.csv?surface=app_reviews")
        self.assertEqual(response.status_code, 200)
        header = response.get_data(as_text=True).splitlines()[0]
        for column in ("sentiment", "rating", "type", "also_names", "source_class"):
            self.assertIn(column, header)


if __name__ == "__main__":
    unittest.main()
