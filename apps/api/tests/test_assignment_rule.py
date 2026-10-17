"""Auto-assignment: the rule a supervisor picks, who is eligible, and the API.

Nothing here touches a platform -- cases are ingested straight into the DB.
"""
import unittest
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from werkzeug.security import generate_password_hash

from core import cases, routing
from db import repositories as repo

from ._db import ApiTestCase, DbTestCase


def _now():
    return datetime.now(timezone.utc)


class AssignmentRuleTests(DbTestCase):
    # users 1-3 agents, 4 supervisor, 5 team lead, 6 senior agent
    ROLES = {1: "agent", 2: "agent", 3: "agent", 4: "supervisor", 5: "team_lead", 6: "senior_agent"}

    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        for uid, role in self.ROLES.items():
            self.db.execute(
                "INSERT INTO \"user\"(id,username,password_hash,role,created_at) "
                "VALUES (?,?, 'x',?,'now')", (uid, f"u{uid}", role))
        self.db.commit()
        self.s = self.db.session
        for uid in self.ROLES:
            routing.upsert_agent(self.s, 1, uid, capacity=5)
        self.n = 0

    def _new_case(self, *, direction="inbound"):
        self.n += 1
        return cases.ingest_message(
            self.s, 1, platform="facebook", handle=f"c{self.n}", body="hi",
            platform_ref=f"ref{self.n}", direction=direction,
            sent_at=_now() - timedelta(minutes=60 - self.n))["case_id"]

    def _assignee(self, case_id):
        return self.s.execute(sa.text('SELECT assignee_id FROM "case" WHERE id=:c'),
                              {"c": case_id}).scalar_one()

    def _rule(self, rule):
        routing.set_policy(self.s, 1, assign_strategy=rule)

    def _park(self, user_id, n):
        """Give ``user_id`` n live cases without touching the rotation clock."""
        for _ in range(n):
            self.n += 1
            cid = self.s.execute(sa.text("""
                INSERT INTO customer (workspace_id, platform, handle) VALUES (1,'x',:h)
                RETURNING id"""), {"h": f"p{self.n}"}).scalar_one()
            self.s.execute(sa.text("""
                INSERT INTO "case" (workspace_id, customer_id, channel, state, assignee_id,
                                    opened_at, last_activity_at)
                VALUES (1, :c, 'x', 'assigned', :u, now(), now())"""), {"c": cid, "u": user_id})

    # --- who is eligible -----------------------------------------------
    def test_default_rule_is_least_busy_and_new_case_is_assigned(self):
        self.assertEqual(routing.policy(self.s, 1)["assign_strategy"], "least_busy")
        cid = self._new_case()
        self.assertIn(self._assignee(cid), (1, 2, 3, 6))
        state = self.s.execute(sa.text('SELECT state FROM "case" WHERE id=:c'), {"c": cid}).scalar_one()
        self.assertEqual(state, "assigned")

    def test_never_a_supervisor_or_team_lead(self):
        self._rule("least_busy")
        for uid in (1, 2, 3, 6):                    # every agent busy, supervisor/lead idle
            self._park(uid, 4)
        got = [self._assignee(self._new_case()) for _ in range(4)]
        self.assertTrue(set(got) <= {1, 2, 3, 6}, got)
        # full agents -> the case waits; it is NOT handed to the idle supervisor / lead
        for _ in range(4):
            self._new_case()
        waiting = self.s.execute(sa.text(
            'SELECT count(*) FROM "case" WHERE assignee_id IS NULL')).scalar_one()
        self.assertEqual(waiting, 4)
        assigned_to = {r[0] for r in self.s.execute(sa.text(
            'SELECT DISTINCT assignee_id FROM "case" WHERE assignee_id IS NOT NULL')).all()}
        self.assertTrue(assigned_to.isdisjoint({4, 5}))

    def test_agent_who_also_holds_an_oversight_role_is_skipped(self):
        self.s.execute(sa.text("INSERT INTO user_role (user_id, role_key) VALUES (1,'team_lead')"))
        self._rule("round_robin")
        got = {self._assignee(self._new_case()) for _ in range(6)}
        self.assertNotIn(1, got)

    def test_away_and_deactivated_agents_are_skipped(self):
        routing.upsert_agent(self.s, 1, 1, available=False)
        self.s.execute(sa.text('UPDATE "user" SET active = 0 WHERE id = 2'))
        self._rule("round_robin")
        got = {self._assignee(self._new_case()) for _ in range(6)}
        self.assertEqual(got, {3, 6})

    # --- the rules ------------------------------------------------------
    def test_round_robin_takes_turns_regardless_of_load(self):
        self._rule("round_robin")
        self._park(1, 3)                             # agent 1 is busier; RR ignores that
        got = [self._assignee(self._new_case()) for _ in range(8)]
        self.assertEqual(got, [1, 2, 3, 6, 1, 2, 3, 6])

    def test_round_robin_continues_after_the_last_agent_even_if_they_leave(self):
        self._rule("round_robin")
        first = [self._assignee(self._new_case()) for _ in range(2)]
        self.assertEqual(first, [1, 2])
        routing.upsert_agent(self.s, 1, 2, available=False)      # agent 2 goes away
        self.assertEqual(self._assignee(self._new_case()), 3)    # carries on after 2

    def test_least_busy_picks_fewest_live_cases(self):
        self._rule("least_busy")
        self._park(1, 2)
        self._park(2, 1)
        self._park(6, 1)
        self.assertEqual(self._assignee(self._new_case()), 3)    # 0 live
        self.assertEqual(self._assignee(self._new_case()), 2)    # 2, 3, 6 tie on 1 live; 3 was just assigned
        # 6 (never assigned) now beats 3 (just assigned) on the tie-break
        self.assertEqual(self._assignee(self._new_case()), 6)

    def test_longest_idle_goes_to_who_waited_longest(self):
        self._rule("longest_idle")
        self._park(1, 3)                             # load only breaks ties among the never-assigned
        got = [self._assignee(self._new_case()) for _ in range(5)]
        self.assertEqual(got, [2, 3, 6, 1, 2])       # never-assigned first, then oldest assignment

    def test_manual_leaves_new_cases_in_the_queue(self):
        self._rule("manual")
        cid = self._new_case()
        self.assertIsNone(self._assignee(cid))
        state = self.s.execute(sa.text('SELECT state FROM "case" WHERE id=:c'), {"c": cid}).scalar_one()
        self.assertEqual(state, "open")
        # an explicit "assign to next available" still works (least busy)
        self.assertIsNotNone(routing.assign_next(self.s, 1, cid, actor="sup"))
        self.assertEqual(routing.drain_queue(self.s, 1), 0)      # and nothing drains automatically

    def test_unknown_rule_is_rejected(self):
        with self.assertRaises(ValueError):
            routing.set_policy(self.s, 1, assign_strategy="random")

    # --- edges ------------------------------------------------------------
    def test_only_a_new_inbound_case_is_auto_assigned(self):
        out = self._new_case(direction="outbound")               # agent-initiated: not routed
        self.assertIsNone(self._assignee(out))
        cid = self._new_case()
        owner = self._assignee(cid)
        cases.ingest_message(self.s, 1, platform="facebook", handle=f"c{self.n}", body="again",
                             sent_at=_now())                     # same customer -> same case
        self.assertEqual(self._assignee(cid), owner)             # not re-routed
        kinds = [e["kind"] for e in cases.timeline(self.s, cid)]
        self.assertEqual(kinds.count("assigned"), 1)

    def test_assigned_event_records_the_rule(self):
        self._rule("round_robin")
        cid = self._new_case()
        ev = [e for e in cases.timeline(self.s, cid) if e["kind"] == "assigned"][0]
        self.assertEqual(ev["actor"], "routing")
        self.assertEqual(ev["detail"]["rule"], "round_robin")

    def test_full_agents_leave_the_case_waiting_then_drain_oldest_first(self):
        for uid in (1, 2, 3, 6):
            self._park(uid, 5)
        first, second = self._new_case(), self._new_case()
        self.assertIsNone(self._assignee(first))
        self.assertIsNone(self._assignee(second))
        self.s.execute(sa.text(
            "UPDATE care_agent SET capacity = 6 WHERE workspace_id = 1 AND user_id = 3"))
        self.assertEqual(routing.drain_queue(self.s, 1), 1)      # one free slot
        self.assertEqual(self._assignee(first), 3)               # FIFO: oldest waiting case
        self.assertIsNone(self._assignee(second))

    def test_closing_a_case_only_issues_work_to_an_eligible_agent(self):
        for uid in (1, 2, 3, 6):
            self._park(uid, 5)
        old = self._new_case()                                   # waits
        self.assertIsNone(routing.on_case_closed(self.s, 1, 4))  # supervisor: never
        self.assertIsNone(self._assignee(old))
        self._rule("manual")
        self.assertIsNone(routing.on_case_closed(self.s, 1, 2))  # manual: never
        self._rule("least_busy")
        cid = self._new_case()                                   # arrives under the new rule
        self.s.execute(sa.text("UPDATE \"case\" SET state = 'closed' "
                               'WHERE id = (SELECT min(id) FROM "case" WHERE assignee_id = 2)'))
        self.assertEqual(routing.on_case_closed(self.s, 1, 2), cid)   # not `old`: it predates the rule
        self.assertIsNone(self._assignee(old))

    # --- the backlog stays put -----------------------------------------
    def test_cases_waiting_before_a_rule_change_stay_unassigned(self):
        for uid in (1, 2, 3, 6):
            self._park(uid, 5)
        older = [self._new_case(), self._new_case()]             # waiting: everyone is full
        self._rule("round_robin")                                # the rule changes now
        newer = self._new_case()                                 # waiting too
        info = routing.assignment_rule(self.s, 1)
        self.assertEqual((info["waiting_cases"], info["held_back_cases"]), (1, 2))
        self.s.execute(sa.text("UPDATE care_agent SET capacity = 8 WHERE workspace_id = 1"))
        self.assertEqual(routing.drain_queue(self.s, 1), 1)      # only the newer case
        self.assertIsNotNone(self._assignee(newer))
        self.assertTrue(all(self._assignee(c) is None for c in older))
        # a person can still hand an old one out explicitly
        self.assertIsNotNone(routing.assign_next(self.s, 1, older[0], actor="sup"))

    def test_choosing_the_same_rule_again_does_not_move_the_line(self):
        for uid in (1, 2, 3, 6):
            self._park(uid, 5)
        self._rule("round_robin")
        waiting = self._new_case()
        self._rule("round_robin")                                # no change
        self.s.execute(sa.text("UPDATE care_agent SET capacity = 8 WHERE workspace_id = 1"))
        self.assertEqual(routing.drain_queue(self.s, 1), 1)
        self.assertIsNotNone(self._assignee(waiting))

    def test_a_workspace_without_a_floor_drains_everything(self):
        for uid in (1, 2, 3, 6):
            self._park(uid, 5)
        waiting = self._new_case()
        self.s.execute(sa.text("UPDATE care_agent SET capacity = 8 WHERE workspace_id = 1"))
        self.assertEqual(routing.drain_queue(self.s, 1), 1)      # no rule change yet -> no floor
        self.assertIsNotNone(self._assignee(waiting))

    def test_a_failing_assignment_never_breaks_ingestion(self):
        real = routing.auto_assign_new_case
        routing.auto_assign_new_case = lambda *a, **k: 1 / 0
        try:
            cid = self._new_case()
        finally:
            routing.auto_assign_new_case = real
        self.assertIsNone(self._assignee(cid))
        self.assertEqual(len(cases.messages(self.s, cid)), 1)

    def test_assignment_rule_summary(self):
        self._park(1, 5)
        self._new_case()
        info = routing.assignment_rule(self.s, 1)
        self.assertEqual(info["strategy"], "least_busy")
        self.assertEqual([x["key"] for x in info["strategies"]],
                         ["manual", "round_robin", "least_busy", "longest_idle"])
        self.assertTrue(all(x["description"] for x in info["strategies"]))
        self.assertEqual(info["roles"], ["agent", "senior_agent"])
        self.assertEqual(info["available_agents"], 4)
        self.assertEqual(info["free_agents"], 3)                 # agent 1 is full


class AssignmentRuleApiTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        conn = self.app.db_operator()
        try:
            ws = conn.execute("SELECT id FROM workspace ORDER BY id LIMIT 1").fetchone()[0]
            self.ws = ws
            for name, role in (("u_agent", "agent"), ("u_lead", "team_lead")):
                repo.users.create(conn.session, username=name,
                                  password_hash=generate_password_hash("pw"), role=role,
                                  created_at=self.app.now(), workspace_id=ws)
                uid = conn.execute('SELECT id FROM "user" WHERE username=?', (name,)).fetchone()[0]
                repo.rbac.set_user_roles(conn.session, uid, [role])
                routing.upsert_agent(conn.session, ws, uid, capacity=5)
                setattr(self, name, uid)
            conn.commit()
        finally:
            conn.close()

    def _login(self, user, pw):
        token = self.client.get("/api/v1/csrf").get_json()["token"]
        self.client.post("/api/v1/auth/login", json={"username": user, "password": pw},
                         headers={"X-CSRF-Token": token})
        with self.client.session_transaction() as s:
            self.csrf = s.get("csrf_token", "")

    def _send(self, method, path, body=None):
        return getattr(self.client, method)(path, json=body, headers={"X-CSRF-Token": self.csrf})

    def test_supervisor_reads_and_sets_the_rule(self):
        self._login("u_lead", "pw")
        got = self._send("get", "/api/v1/care/assignment-rule")
        self.assertEqual(got.status_code, 200, got.get_data(as_text=True))
        self.assertEqual(got.get_json()["strategy"], "least_busy")
        put = self._send("put", "/api/v1/care/assignment-rule", {"strategy": "round_robin"})
        self.assertEqual(put.status_code, 200, put.get_data(as_text=True))
        self.assertEqual(put.get_json()["strategy"], "round_robin")
        self.assertEqual(self._send("get", "/api/v1/care/assignment-rule").get_json()["strategy"],
                         "round_robin")
        self.assertEqual(self._send("put", "/api/v1/care/assignment-rule", {"strategy": "random"}).status_code, 400)
        self.assertEqual(self._send("put", "/api/v1/care/assignment-rule", {}).status_code, 400)

    def test_an_agent_cannot_read_or_change_it(self):
        self._login("u_agent", "pw")
        self.assertEqual(self._send("get", "/api/v1/care/assignment-rule").status_code, 403)
        self.assertEqual(self._send("put", "/api/v1/care/assignment-rule",
                                    {"strategy": "manual"}).status_code, 403)

    def test_change_is_audited(self):
        self._login("admin", "admin123")
        self._send("put", "/api/v1/care/assignment-rule", {"strategy": "manual"})
        conn = self.app.db_operator()
        try:
            actions = [r[0] for r in conn.execute("SELECT action FROM audit_event").fetchall()]
        finally:
            conn.close()
        self.assertIn("care.assignment_rule", actions)

    def test_ingest_route_assigns_once_to_an_agent(self):
        self._login("admin", "admin123")
        cid = self._send("post", "/api/v1/care/cases/ingest", {
            "platform": "facebook", "handle": "sara", "body": "help"}).get_json()["case_id"]
        detail = self._send("get", f"/api/v1/care/cases/{cid}").get_json()
        self.assertEqual(detail["case"]["assignee_id"], self.u_agent)   # the agent, not the team lead
        self.assertEqual([e["kind"] for e in detail["timeline"]].count("assigned"), 1)


if __name__ == "__main__":
    unittest.main()
