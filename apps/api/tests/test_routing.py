"""P3.3 — routing engine.

Exit criterion: 5 agents, capacity 5, 40 cases → distribution is even and no
agent exceeds cap; an SLA breach fires an event at the configured threshold.
"""
import unittest
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa

from core import cases, routing
from jobs import scheduler

from ._db import DbTestCase


class RoutingTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        for uid in range(1, 6):
            self.db.execute(
                "INSERT INTO \"user\"(id,username,password_hash,role,created_at) "
                "VALUES (?,?, 'x','agent','now')", (uid, f"a{uid}"))
        self.db.commit()
        self.s = self.db.session
        for uid in range(1, 6):
            routing.upsert_agent(self.s, 1, uid, capacity=5)
        self.db.commit()

    def _open_case(self, n):
        # Relative to real "now", not a hardcoded date -- a fixed past date
        # eventually drifts more than cases.CONSOLIDATION_WINDOW (2h) behind
        # whatever "now" a later default-sent_at ingest_message() call uses,
        # so that call silently opens a second case instead of consolidating.
        return cases.ingest_message(
            self.s, 1, platform="x", handle=f"@c{n}", body="hi",
            sent_at=datetime.now(timezone.utc) - timedelta(hours=2) + timedelta(minutes=n)
        )["case_id"]

    def _assigned_counts(self):
        rows = self.s.execute(sa.text(
            'SELECT assignee_id, count(*) FROM "case" '
            'WHERE workspace_id=1 AND assignee_id IS NOT NULL AND state <> \'closed\' '
            'GROUP BY assignee_id')).all()
        return {uid: n for uid, n in rows}

    def test_five_agents_cap_five_forty_cases(self):
        for n in range(40):                               # ingest auto-assigns (least busy)
            self._open_case(n)
        self.db.commit()

        counts = self._assigned_counts()
        self.assertEqual(sum(counts.values()), 25)        # 5 agents x cap 5
        self.assertEqual(set(counts.values()), {5})       # perfectly even
        self.assertTrue(all(v <= 5 for v in counts.values()))
        unassigned = self.s.execute(sa.text(
            'SELECT count(*) FROM "case" WHERE workspace_id=1 AND assignee_id IS NULL'
        )).scalar_one()
        self.assertEqual(unassigned, 15)

    def test_auto_issue_on_closure(self):
        for n in range(40):                               # ingest auto-assigns; 15 keep waiting
            self._open_case(n)
        self.db.commit()

        # agent 1 closes one of their cases -> gets a waiting one back
        mine = self.s.execute(sa.text(
            'SELECT id FROM "case" WHERE assignee_id=1 LIMIT 1')).scalar_one()
        cases.transition(self.s, mine, "closed", actor="a1", closure_category="resolved")
        issued = routing.on_case_closed(self.s, 1, 1, actor="routing")
        self.db.commit()
        self.assertIsNotNone(issued)
        self.assertEqual(self._assigned_counts()[1], 5)   # back to full

    def test_reassign_needs_a_reason(self):
        cid = self._open_case(0)                          # auto-assigned on ingest
        with self.assertRaises(cases.CaseError):
            routing.reassign(self.s, cid, 2, actor="sup", reason="")
        routing.reassign(self.s, cid, 2, actor="sup", reason="agent 1 went offline")
        self.db.commit()
        assignee = self.s.execute(sa.text(
            'SELECT assignee_id FROM "case" WHERE id=:c'), {"c": cid}).scalar_one()
        self.assertEqual(assignee, 2)
        kinds = [e["kind"] for e in cases.timeline(self.s, cid)]
        self.assertIn("reassigned", kinds)

    def test_sla_breach_fires_an_event(self):
        routing.set_policy(self.s, 1, first_response_sla=60, resolution_sla=120,
                           escalation_after=90)
        self.db.commit()
        cid = self._open_case(0)
        # arm with an already-past "now" so the timers are immediately due
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        routing.arm_sla_timers(self.s, 1, cid, now=past)
        self.db.commit()

        fired = scheduler.tick(self.s, now=datetime.now(timezone.utc))
        self.db.commit()
        self.assertTrue(any(name.startswith("sla:first_response:") for name, _ in fired))

        # the one-shot task disabled itself
        still_enabled = self.s.execute(sa.text(
            "SELECT enabled FROM scheduled_task WHERE name=:n"),
            {"n": f"sla:first_response:{cid}"}).scalar_one()
        self.assertEqual(still_enabled, 0)

        # run the check: no first response -> breach event
        routing.check_sla(self.s, {"ws": 1, "case_id": cid, "check": "first_response"})
        self.db.commit()
        kinds = [e["kind"] for e in cases.timeline(self.s, cid)]
        self.assertIn("sla_breach", kinds)

    def test_no_breach_when_responded_in_time(self):
        cid = self._open_case(0)
        # An explicit sent_at close to the case's own opened_at -- a default
        # (real-"now") sent_at here only lands the reply on the same case
        # (`cid`) as long as _open_case's base timestamp is still within the
        # 2h consolidation window; once it isn't, this opens a *second* case
        # instead, leaving cid's first_response_at unset -- so the very check
        # this test exists for reports a false breach.
        cases.ingest_message(self.s, 1, platform="x", handle="@c0", body="reply",
                             direction="outbound", actor="agent",
                             sent_at=datetime.now(timezone.utc) - timedelta(hours=2) + timedelta(minutes=5))
        self.db.commit()
        out = routing.check_sla(self.s, {"ws": 1, "case_id": cid,
                                         "check": "first_response"})
        self.assertFalse(out["breached"])


if __name__ == "__main__":
    unittest.main()
