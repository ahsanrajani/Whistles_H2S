"""P4.6 — content calendar + approval workflow."""
import unittest
from datetime import date, datetime, timedelta, timezone

from core import content_calendar as cc

from ._db import ApiTestCase, DbTestCase

SLOT = datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc)


class ContentStateMachineTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        for uid, name in ((7, "writer"), (9, "editor")):
            self.db.execute(
                'INSERT INTO "user"(id,username,password_hash,role,created_at) '
                "VALUES (?,?,'x','agent','now')", (uid, name))
        self.db.commit()
        self.s = self.db.session

    def _new(self, **kw):
        cid = cc.create(self.s, 1, 7, title=kw.get("title", "Eid post"),
                        body=kw.get("body", "Eid Mubarak"),
                        channel=kw.get("channel", "meta"),
                        scheduled_for=kw.get("scheduled_for"))
        self.db.commit()
        return cid

    def test_happy_path_to_published(self):
        cid = self._new()
        self.assertEqual(cc.transition(self.s, 1, cid, "submit", 7), "in_review")
        self.assertEqual(cc.transition(self.s, 1, cid, "approve", 9), "approved")
        row = cc.get(self.s, 1, cid)["item"]
        self.assertEqual(row["approved_by"], 9)
        self.assertEqual(cc.transition(self.s, 1, cid, "schedule", 9, at=SLOT), "scheduled")
        self.assertEqual(cc.get(self.s, 1, cid)["item"]["scheduled_for"], SLOT)
        self.assertEqual(cc.transition(self.s, 1, cid, "publish", 9), "published")
        self.assertIsNotNone(cc.get(self.s, 1, cid)["item"]["published_at"])

    def test_reject_then_revise_returns_to_draft(self):
        cid = self._new()
        cc.transition(self.s, 1, cid, "submit", 7)
        self.assertEqual(cc.transition(self.s, 1, cid, "reject", 9,
                                       note="off brand"), "rejected")
        hist = cc.get(self.s, 1, cid)["history"]
        self.assertEqual(hist[-1]["note"], "off brand")
        self.assertEqual(cc.transition(self.s, 1, cid, "revise", 7), "draft")

    def test_editing_a_locked_item_is_refused(self):
        cid = self._new()
        cc.transition(self.s, 1, cid, "submit", 7)
        cc.transition(self.s, 1, cid, "approve", 9)
        with self.assertRaises(cc.ContentError):
            cc.update(self.s, 1, cid, 7, title="too late")

    def test_illegal_transition_is_refused(self):
        cid = self._new()
        with self.assertRaises(cc.ContentError):
            cc.transition(self.s, 1, cid, "publish", 9)

    def test_schedule_needs_a_time(self):
        cid = self._new()
        cc.transition(self.s, 1, cid, "submit", 7)
        cc.transition(self.s, 1, cid, "approve", 9)
        with self.assertRaises(cc.ContentError):
            cc.transition(self.s, 1, cid, "schedule", 9)

    def test_delete_only_draft_or_rejected(self):
        cid = self._new()
        cc.transition(self.s, 1, cid, "submit", 7)
        with self.assertRaises(cc.ContentError):
            cc.delete(self.s, 1, cid, 7)
        cc.transition(self.s, 1, cid, "reject", 9)
        cc.delete(self.s, 1, cid, 7)
        self.db.commit()

    def test_calendar_window_and_in_flight(self):
        scheduled = self._new(scheduled_for=SLOT)
        cc.transition(self.s, 1, scheduled, "submit", 7)
        cc.transition(self.s, 1, scheduled, "approve", 9)
        cc.transition(self.s, 1, scheduled, "schedule", 9, at=SLOT)
        self._new(title="idea only")             # draft, unscheduled
        self.db.commit()
        cal = cc.calendar(self.s, 1, datetime(2026, 6, 1, tzinfo=timezone.utc),
                          datetime(2026, 7, 31, tzinfo=timezone.utc))
        titles = {i["title"] for i in cal["items"]}
        self.assertEqual(titles, {"Eid post", "idea only"})


class ContentApiTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        token = self.client.get("/api/v1/csrf").get_json()["token"]
        self.client.post("/api/v1/auth/login",
                         json={"username": "admin", "password": "admin123"},
                         headers={"X-CSRF-Token": token})
        with self.client.session_transaction() as s:
            self.csrf = s.get("csrf_token", "")

    def _h(self):
        return {"X-CSRF-Token": self.csrf}

    def test_full_workflow_through_the_api(self):
        cid = self.client.post("/api/v1/content",
                               json={"title": "Launch", "body": "Big news",
                                     "channel": "meta"},
                               headers=self._h()).get_json()["id"]

        slot = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
        self.assertEqual(self.client.patch(f"/api/v1/content/{cid}",
                                           json={"scheduled_for": slot},
                                           headers=self._h()).status_code, 200)

        self.assertEqual(self.client.post(f"/api/v1/content/{cid}/transition",
                                          json={"action": "submit"},
                                          headers=self._h()).status_code, 200)
        # approve must go through /review
        self.assertEqual(self.client.post(f"/api/v1/content/{cid}/transition",
                                          json={"action": "approve"},
                                          headers=self._h()).status_code, 403)
        r = self.client.post(f"/api/v1/content/{cid}/review",
                             json={"decision": "approve"}, headers=self._h())
        self.assertEqual(r.get_json()["state"], "approved")

        self.client.post(f"/api/v1/content/{cid}/transition",
                         json={"action": "schedule"}, headers=self._h())
        pub = self.client.post(f"/api/v1/content/{cid}/transition",
                               json={"action": "publish"}, headers=self._h()).get_json()
        self.assertEqual(pub["state"], "published")
        self.assertIsNotNone(pub["outbound_action_id"])

        listed = self.client.get("/api/v1/content").get_json()["items"]
        self.assertTrue(any(i["id"] == cid for i in listed))

        conn = self.app.db_operator()
        try:
            actions = {r[0] for r in conn.execute(
                "SELECT action FROM audit_event WHERE action LIKE 'content.%'").fetchall()}
        finally:
            conn.close()
        self.assertTrue({"content.create", "content.submit", "content.approve",
                         "content.publish"} <= actions)

    def test_media_upload_round_trips_into_a_content_item(self):
        import shutil
        import tempfile
        from unittest.mock import patch

        from core import content_media
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        with patch.object(content_media, "UPLOAD_ROOT", tmp):
            up = self.client.post("/api/v1/content/media",
                                  files={"file": ("pic.jpg", b"\xff\xd8\xff fake", "image/jpeg")},
                                  headers=self._h())
            self.assertEqual(up.status_code, 200)
            url = up.get_json()["url"]
            self.assertTrue(url.startswith("/uploads/"))

            cid = self.client.post("/api/v1/content",
                                   json={"title": "With a picture", "body": "x",
                                         "channel": "meta", "media": [url]},
                                   headers=self._h()).get_json()["id"]
        item = self.client.get(f"/api/v1/content/{cid}").get_json()["item"]
        self.assertEqual(item["media"], [url])

    def test_media_upload_rejects_an_unsupported_type(self):
        r = self.client.post("/api/v1/content/media",
                             files={"file": ("x.exe", b"MZ", "application/x-msdownload")},
                             headers=self._h())
        self.assertEqual(r.status_code, 400)

    def test_content_assist_returns_a_caption_and_hashtags(self):
        from unittest.mock import patch

        from integrations.llm import panel
        # the route calls _app.keys(ws), which picks up a real key from the
        # environment if one is set -- stub the model call so this is
        # deterministic and never leaves the process (see test_ai_assist.py).
        with patch.object(panel, "ask", return_value=(
                "openrouter", "anthropic/claude-haiku-4.5",
                "A great new way to save.\nHASHTAGS: #Savings #Pakistan\n")):
            r = self.client.post("/api/v1/content/assist",
                                 json={"topic": "a new savings account", "channel": "instagram"},
                                 headers=self._h())
        self.assertEqual(r.status_code, 200)
        out = r.get_json()
        self.assertEqual(out["caption"], "A great new way to save.")
        self.assertEqual(out["hashtags"], ["#Savings", "#Pakistan"])

    def test_content_assist_400s_with_neither_topic_nor_draft(self):
        r = self.client.post("/api/v1/content/assist", json={}, headers=self._h())
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
