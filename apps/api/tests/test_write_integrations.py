"""P3.1 — the write-integration layer.

Each platform records every call in outbound_action; a mock-mode call "sends"
and records; a platform rejection surfaces a rework.
"""
import unittest

import sqlalchemy as sa

from db import repositories as repo
from integrations import write

from ._db import DbTestCase

_ACTION_ARGS = {
    "reply_public": {"target_ref": "post:1", "text": "hi"},
    "reply_dm": {"target_ref": "thread:1", "text": "hi"},
    "publish": {"text": "hello world"},
    "schedule": {"text": "later", "at": "2026-09-10T10:00:00Z"},
    "block": {"target_ref": "user:1"},
    "unblock": {"target_ref": "user:1"},
    "delete_reply": {"target_ref": "reply:1"},
}


class WriteLayerTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.commit()
        self.s = self.db.session

    def _rows(self):
        return self.s.execute(sa.text(
            "SELECT platform, action, state, external_id, request, actor, error "
            "FROM outbound_action WHERE workspace_id=1 ORDER BY id")).mappings().all()

    def test_every_platform_records_every_supported_action_in_mock_mode(self):
        for platform, cls in write.CLIENTS.items():
            c = cls({})                                  # no creds -> mock
            self.assertTrue(c.is_mock())
            for action in cls.SUPPORTED:
                fn = getattr(c, action)
                result = fn(self.s, 1, actor="agent-7", **_ACTION_ARGS[action])
                self.assertEqual(result.state, "sent")
                self.assertTrue(result.external_id.startswith(f"mock:{platform}:"))
        self.db.commit()
        rows = self._rows()
        expected = sum(len(cls.SUPPORTED) for cls in write.CLIENTS.values())
        self.assertEqual(len(rows), expected)
        self.assertTrue(all(r["state"] == "sent" for r in rows))
        self.assertTrue(all(r["actor"] == "agent-7" for r in rows))
        self.assertTrue(all(r["request"] is not None for r in rows))
        text_rows = [r for r in rows if r["action"] in ("reply_public", "publish")]
        self.assertTrue(all("text" in r["request"] for r in text_rows))

    def test_unsupported_action_raises(self):
        gr = write.GoogleReviewsWriteClient({})
        with self.assertRaises(write.WriteError):
            gr.publish(self.s, 1, text="nope")

    def test_rejection_moves_the_row_to_rework(self):
        def reject(_a, _t, _r):
            raise write.WriteRejected("Google policy: promotional content")

        gr = write.GoogleReviewsWriteClient({"GOOGLE_BUSINESS_TOKEN": "t"},
                                            transport=reject)
        self.assertFalse(gr.is_mock())
        result = gr.reply_public(self.s, 1, target_ref="review:9", text="thanks",
                                 actor="agent-1")
        self.db.commit()
        self.assertEqual(result.state, "rejected")
        pending = repo.outbound.pending_rework(self.s, 1)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["platform"], "google_reviews")
        self.assertIn("promotional", pending[0]["error"])

        repo.outbound.mark_reworked(self.s, result.action_id)
        self.db.commit()
        self.assertEqual(repo.outbound.pending_rework(self.s, 1), [])

    def test_transport_error_is_recorded_as_failed(self):
        def boom(_a, _t, _r):
            raise RuntimeError("network down")

        c = write.MetaWriteClient({"META_ACCESS_TOKEN": "t", "META_PAGE_ID": "p"},
                                  transport=boom)
        result = c.reply_public(self.s, 1, target_ref="post:1", text="x")
        self.db.commit()
        self.assertEqual(result.state, "failed")
        self.assertIn("network down", self._rows()[0]["error"])

    def test_transport_success_records_the_external_id(self):
        def ok(_a, _t, _r):
            return {"external_id": "fb_reply_555", "response": {"id": "fb_reply_555"}}

        c = write.MetaWriteClient({"META_ACCESS_TOKEN": "t", "META_PAGE_ID": "p"},
                                  transport=ok)
        result = c.reply_public(self.s, 1, target_ref="post:1", text="x")
        self.db.commit()
        self.assertEqual(result.state, "sent")
        self.assertEqual(result.external_id, "fb_reply_555")
        self.assertEqual(self._rows()[0]["external_id"], "fb_reply_555")

    def test_client_for_unknown_platform(self):
        with self.assertRaises(ValueError):
            write.client_for("myspace", {})

    def test_client_for_aliases_facebook_and_instagram_to_meta(self):
        # F7.5 — the read-side surfaces (core/sources.py) label these two
        # separately since they're collected separately; the write side
        # shares one Meta Graph client/credentials for both. A case's
        # channel/customer.platform is the surface name ("facebook"), and
        # that's what the reply route forwards straight into client_for —
        # this alias is what makes replying to a Facebook-channel case work.
        self.assertIsInstance(write.client_for("facebook", {}), write.MetaWriteClient)
        self.assertIsInstance(write.client_for("instagram", {}), write.MetaWriteClient)

    def test_mark_rejected_helper(self):
        c = write.XWriteClient({})
        r = c.reply_public(self.s, 1, target_ref="tweet:1", text="hi")
        self.db.commit()
        repo.outbound.mark_rejected(self.s, r.action_id, "duplicate content")
        self.db.commit()
        pending = repo.outbound.pending_rework(self.s, 1)
        self.assertEqual(pending[0]["id"], r.action_id)


class DryRunDefaultTests(DbTestCase):
    """§D — with real credentials but GURU_WRITE_LIVE off, a call builds and
    logs its request and records ``dry_run`` — it never reaches the platform."""

    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.commit()
        self.s = self.db.session
        self.creds = {"META_ACCESS_TOKEN": "t", "META_PAGE_ID": "p"}

    def _row(self, action_id):
        return self.s.execute(sa.text(
            "SELECT state, external_id, response FROM outbound_action WHERE id=:i"),
            {"i": action_id}).mappings().first()

    def test_creds_present_but_not_live_is_a_dry_run(self):
        c = write.MetaWriteClient(self.creds)                 # no transport, no flag
        self.assertFalse(c.is_mock())
        self.assertFalse(c.is_live())
        result = c.reply_public(self.s, 1, target_ref="12_34", text="hello")
        self.db.commit()
        self.assertEqual(result.state, "dry_run")
        self.assertFalse(result.ok)
        self.assertIsNone(result.external_id)
        row = self._row(result.action_id)
        self.assertEqual(row["state"], "dry_run")
        self.assertIsNone(row["external_id"])
        self.assertTrue(row["response"]["dry_run"])
        self.assertEqual(row["response"]["would_send"]["text"], "hello")

    def test_live_flag_in_the_key_dict_turns_sending_on(self):
        c = write.MetaWriteClient({**self.creds, "GURU_WRITE_LIVE": "1"})
        self.assertTrue(c.is_live())
        # no transport wired -> the live path is reached and raises -> failed,
        # which proves dry-run is no longer intercepting.
        result = c.reply_public(self.s, 1, target_ref="12_34", text="x")
        self.db.commit()
        self.assertEqual(result.state, "failed")

    def test_explicit_live_false_forces_dry_run_even_with_the_flag(self):
        c = write.MetaWriteClient({**self.creds, "GURU_WRITE_LIVE": "1"}, live=False)
        result = c.reply_public(self.s, 1, target_ref="12_34", text="x")
        self.db.commit()
        self.assertEqual(result.state, "dry_run")

    def test_deliver_of_a_pending_action_also_honours_dry_run(self):
        c = write.MetaWriteClient(self.creds)
        aid = c.create_pending(self.s, 1, action="reply_public",
                               target_ref="12_34", request={"text": "queued"})
        self.db.commit()
        result = c.deliver(self.s, aid)
        self.db.commit()
        self.assertEqual(result.state, "dry_run")
        self.assertEqual(self._row(aid)["response"]["would_send"]["text"], "queued")

    def test_mock_mode_is_unaffected_by_the_live_flag(self):
        c = write.MetaWriteClient({"GURU_WRITE_LIVE": "1"})   # no creds
        self.assertTrue(c.is_mock())
        result = c.reply_public(self.s, 1, target_ref="12_34", text="x")
        self.db.commit()
        self.assertEqual(result.state, "sent")
        self.assertTrue(result.external_id.startswith("mock:meta:"))

    def test_live_enabled_truth_table(self):
        self.assertTrue(write.base.live_enabled(True, {}))
        self.assertFalse(write.base.live_enabled(False, {"GURU_WRITE_LIVE": "1"}))
        self.assertTrue(write.base.live_enabled(None, {"GURU_WRITE_LIVE": "yes"}))
        self.assertTrue(write.base.live_enabled(None, {"GURU_WRITE_LIVE": "ON"}))
        self.assertFalse(write.base.live_enabled(None, {"GURU_WRITE_LIVE": "0"}))
        self.assertFalse(write.base.live_enabled(None, {"GURU_WRITE_LIVE": ""}))
        self.assertFalse(write.base.live_enabled(None, {}))


if __name__ == "__main__":
    unittest.main()
