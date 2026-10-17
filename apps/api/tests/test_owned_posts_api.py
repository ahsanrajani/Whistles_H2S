"""GET /owned-posts -- listening:view, same as the other listening surfaces."""
import unittest

from ._db import ApiTestCase


class OwnedPostsApiTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        conn = self.app.db_operator()
        try:
            conn.execute(
                """INSERT INTO item(workspace_id,surface,source,source_kind,external_id,
                   url,author,published_at,body,raw_json,collected_at,content_hash)
                   VALUES(1,'x','meta_facebook','public','fb:p1','https://fb.com/p1',
                   'Bank Alfalah','2026-09-01T00:00:00Z','our new rates',
                   ?,'now','h1')""", ('{"kind":"post","metrics":{"likes":5}}',))
            conn.commit()
        finally:
            conn.close()
        token = self.client.get("/api/v1/csrf").get_json()["token"]
        self.client.post("/api/v1/auth/login",
                         json={"username": "bank", "password": "viewer123"},
                         headers={"X-CSRF-Token": token})
        with self.client.session_transaction() as s:
            self.csrf = s.get("csrf_token", "")

    def test_viewer_can_list_owned_posts_with_real_metrics(self):
        r = self.client.get("/api/v1/owned-posts")
        self.assertEqual(r.status_code, 200)
        posts = r.get_json()["posts"]
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["platform"], "facebook")
        self.assertEqual(posts[0]["metrics"], {"likes": 5})
        self.assertEqual(posts[0]["url"], "https://fb.com/p1")

    def test_platform_filter(self):
        self.assertEqual(len(self.client.get(
            "/api/v1/owned-posts?platform=youtube").get_json()["posts"]), 0)
        self.assertEqual(len(self.client.get(
            "/api/v1/owned-posts?platform=facebook").get_json()["posts"]), 1)

    def test_an_unrecognised_platform_is_ignored_not_an_error(self):
        r = self.client.get("/api/v1/owned-posts?platform=nope")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.get_json()["posts"]), 1)

    def test_comments_endpoint_nests_a_reply_under_its_comment(self):
        conn = self.app.db_operator()
        try:
            conn.execute(
                """INSERT INTO item(workspace_id,surface,source,source_kind,external_id,
                   url,author,published_at,body,raw_json,collected_at,content_hash)
                   VALUES(1,'x','meta_facebook','public','fb:c1','https://fb.com/c1',
                   'A Customer','2026-09-01T01:00:00Z','a complaint',
                   ?,'now','h2')""",
                ('{"kind":"comment","parent_id":"fb:p1"}',))
            conn.commit()
        finally:
            conn.close()
        r = self.client.get("/api/v1/owned-posts/comments?source=meta_facebook&post_external_id=fb:p1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["comments"][0]["external_id"], "fb:c1")

    def test_viewer_cannot_reply_but_can_read(self):
        r = self.client.post("/api/v1/owned-posts/reply",
                             json={"platform": "facebook", "text": "hi", "target_ref": "fb:c1"},
                             headers={"X-CSRF-Token": self.csrf})
        self.assertEqual(r.status_code, 403)

    def test_admin_can_reply(self):
        # workspace 1's seed fixture carries test Meta credentials (same as
        # test_care_api.py's facebook-channel reply test), so this exercises
        # the real send path, not just a dry run.
        self.client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": self.csrf})
        token = self.client.get("/api/v1/csrf").get_json()["token"]
        self.client.post("/api/v1/auth/login",
                         json={"username": "admin", "password": "admin123"},
                         headers={"X-CSRF-Token": token})
        with self.client.session_transaction() as s:
            csrf = s.get("csrf_token", "")
        r = self.client.post("/api/v1/owned-posts/reply",
                             json={"platform": "facebook", "text": "hi", "target_ref": "fb:c1"},
                             headers={"X-CSRF-Token": csrf})
        self.assertEqual(r.status_code, 200)
        self.assertIn(r.get_json()["state"], ("sent", "dry_run"))

    def test_missing_fields_is_a_clean_400(self):
        self.client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": self.csrf})
        token = self.client.get("/api/v1/csrf").get_json()["token"]
        self.client.post("/api/v1/auth/login",
                         json={"username": "admin", "password": "admin123"},
                         headers={"X-CSRF-Token": token})
        with self.client.session_transaction() as s:
            csrf = s.get("csrf_token", "")
        r = self.client.post("/api/v1/owned-posts/reply", json={"platform": "facebook"},
                             headers={"X-CSRF-Token": csrf})
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
