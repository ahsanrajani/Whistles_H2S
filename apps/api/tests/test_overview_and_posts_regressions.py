"""Two bugs found while loading a realistic corpus:

* the admin Overview 500'd as soon as any mention had been excluded, because
  ``insights.exclusions`` returned raw DB rows that FastAPI cannot serialise;
* ``owned_posts.recent`` took the newest N rows of each source and then kept
  the posts, so a comment section newer than the posts hid every post."""
import json

from core import insights, owned_posts

from ._db import DbTestCase


class _Corpus(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute("INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.execute("INSERT INTO brand(id,workspace_id,name,is_focus) VALUES (1,1,'Focus Bank',1)")
        self.n = 0

    def _item(self, *, source="meta_facebook", surface="facebook", kind="licensed", raw=None, when="2026-10-01T09:00:00Z"):
        self.n += 1
        self.db.execute(
            """INSERT INTO item(id,workspace_id,surface,source,source_kind,external_id,url,outlet,published_at,body,raw_json,collected_at,content_hash)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (self.n, 1, surface, source, kind, f"e{self.n}", f"https://x/{self.n}", "o", when, f"text {self.n}",
             json.dumps(raw or {}), "now", f"h{self.n}"))
        self.db.commit()
        return self.n


class ExclusionsAreJsonSafe(_Corpus):
    def test_exclusions_are_plain_reason_count_pairs(self):
        iid = self._item(surface="x", source="x_recent")
        self.db.execute("INSERT INTO mention(id,item_id,brand_id,workspace_id,rule,excluded,exclude_reason) "
                        "VALUES (1,?,1,1,'t',1,'ambiguous name')", (iid,))
        self.db.commit()
        out = insights.exclusions(self.db, 1)
        self.assertEqual(out, [["ambiguous name", 1]])
        json.dumps(out)                       # a raw Row here is what broke the Overview


class PostsAreNotCrowdedOutByComments(_Corpus):
    def test_a_post_older_than_a_busy_comment_section_is_still_listed(self):
        post = self._item(raw={"kind": "post", "metrics": {"likes": 5}}, when="2026-09-01T09:00:00Z")
        for i in range(150):                  # newer than the post, more than the fetch window
            self._item(raw={"kind": "comment", "parent_id": f"e{post}"}, when=f"2026-10-0{1 + i % 9}T10:00:00Z")
        posts = owned_posts.recent(self.db.session, 1, limit=10)
        self.assertEqual([p["external_id"] for p in posts], [f"e{post}"])
