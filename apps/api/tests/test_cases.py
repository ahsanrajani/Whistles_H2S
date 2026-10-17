"""P3.2 — the case engine.

Exit criterion: same customer, a DM plus a comment within two hours → one case
with two messages; outside the window → two cases.
"""
import unittest
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa

from core import cases

from ._db import DbTestCase

T0 = datetime(2026, 9, 10, 9, 0, tzinfo=timezone.utc)


class CaseEngineTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.execute(
            "INSERT INTO \"user\"(id,username,password_hash,role,created_at) "
            "VALUES (1,'agent','x','agent','now')")
        self.db.commit()
        self.s = self.db.session

    def _in(self, *, platform="x", handle="@cust", body="hi", when, ref=None,
            email=None):
        return cases.ingest_message(self.s, 1, platform=platform, handle=handle,
                                    body=body, sent_at=when, platform_ref=ref,
                                    email=email)

    def _messages(self, case_id):
        return list(cases.messages(self.s, case_id))

    # --- the exit criterion --------------------------------------------
    def test_same_handle_and_platform_consolidates_within_window(self):
        a = self._in(handle="@sam", when=T0, ref="dm:1")
        b = self._in(handle="@sam", when=T0 + timedelta(minutes=90), ref="cmt:2")
        self.db.commit()
        self.assertEqual(a["case_id"], b["case_id"])
        self.assertFalse(b["new"])
        self.assertEqual(len(self._messages(a["case_id"])), 2)

    def test_outside_the_window_opens_a_second_case(self):
        a = self._in(handle="@sam", when=T0)
        b = self._in(handle="@sam", when=T0 + timedelta(hours=3))
        self.db.commit()
        self.assertNotEqual(a["case_id"], b["case_id"])
        self.assertTrue(b["new"])

    def test_a_closed_case_does_not_consolidate(self):
        a = self._in(handle="@sam", when=T0)
        cases.transition(self.s, a["case_id"], "closed", actor="agent",
                         closure_category="resolved")
        b = self._in(handle="@sam", when=T0 + timedelta(minutes=10))
        self.db.commit()
        self.assertNotEqual(a["case_id"], b["case_id"])

    # --- identity resolution -----------------------------------------
    def test_email_links_a_customer_across_platforms(self):
        a = self._in(platform="x", handle="@sam", when=T0, email="sam@e.com")
        b = cases.ingest_message(self.s, 1, platform="facebook", handle="sam.fb",
                                 email="sam@e.com", body="fb", channel="facebook",
                                 sent_at=T0 + timedelta(minutes=30))
        self.db.commit()
        self.assertEqual(a["customer_id"], b["customer_id"])
        self.assertEqual(a["case_id"], b["case_id"])

    # --- state machine ---------------------------------------------
    def test_state_machine_happy_path(self):
        c = self._in(handle="@sam", when=T0)["case_id"]
        cases.assign(self.s, c, 1, actor="sup")
        self.assertEqual(cases._state(self.s, c), "assigned")
        for to in ("in_progress", "pending_approval", "in_progress", "closed"):
            kw = {"closure_category": "resolved"} if to == "closed" else {}
            cases.transition(self.s, c, to, actor="agent", **kw)
        self.assertEqual(cases._state(self.s, c), "closed")

    def test_illegal_transition_raises(self):
        c = self._in(handle="@sam", when=T0)["case_id"]
        with self.assertRaises(cases.CaseError):
            cases.transition(self.s, c, "pending_approval", actor="a")  # not from open

    def test_closing_requires_a_category(self):
        c = self._in(handle="@sam", when=T0)["case_id"]
        with self.assertRaises(cases.CaseError):
            cases.transition(self.s, c, "closed", actor="a")

    def test_reopen_clears_the_closure_category(self):
        c = self._in(handle="@sam", when=T0)["case_id"]
        cases.transition(self.s, c, "closed", actor="a", closure_category="dupe")
        cases.transition(self.s, c, "open", actor="a")
        self.db.commit()
        row = self.s.execute(sa.text(
            'SELECT state, closure_category, closed_at FROM "case" WHERE id=:c'),
            {"c": c}).one()
        self.assertEqual(row.state, "open")
        self.assertIsNone(row.closure_category)
        self.assertIsNone(row.closed_at)

    # --- events + first response -----------------------------------
    def test_first_outbound_sets_first_response_at(self):
        c = self._in(handle="@sam", when=T0)["case_id"]
        cases.ingest_message(self.s, 1, platform="x", handle="@sam", body="reply",
                             direction="outbound", actor="agent",
                             sent_at=T0 + timedelta(minutes=20))
        self.db.commit()
        fr = self.s.execute(sa.text(
            'SELECT first_response_at FROM "case" WHERE id=:c'), {"c": c}).scalar_one()
        self.assertIsNotNone(fr)

    def test_timeline_records_every_mutation(self):
        c = self._in(handle="@sam", when=T0)["case_id"]
        cases.add_note(self.s, c, 1, "internal note")
        cases.assign(self.s, c, 1, actor="sup")
        kinds = [e["kind"] for e in cases.timeline(self.s, c)]
        self.assertEqual(kinds[0], "created")
        self.assertIn("message_in", kinds)
        self.assertIn("note", kinds)
        self.assertIn("assigned", kinds)


if __name__ == "__main__":
    unittest.main()
