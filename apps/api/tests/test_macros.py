"""Macros: library + placeholders + actions, auto-macro rules, and the API gate.

Nothing here touches a platform: reply text goes through the write layer in its
credential-less mock mode.
"""
import unittest
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from werkzeug.security import generate_password_hash

from core import cases, macro_rules, macros, routing
from db import repositories as repo

from ._db import ApiTestCase, DbTestCase


def _now():
    return datetime.now(timezone.utc)


class MacroCoreTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        for uid in (1, 2):
            self.db.execute(
                "INSERT INTO \"user\"(id,username,password_hash,role,created_at) "
                "VALUES (?,?, 'x','agent','now')", (uid, f"agent{uid}"))
        self.db.commit()
        self.s = self.db.session
        for uid in (1, 2):
            routing.upsert_agent(self.s, 1, uid, capacity=5)

    def _case(self, *, body="hello", channel="facebook", name="Sara Khan", ago=0, handle="sara"):
        return cases.ingest_message(
            self.s, 1, platform="facebook", handle=handle, display_name=name, body=body,
            channel=channel, platform_ref=f"ref-{handle}-{ago}",
            sent_at=_now() - timedelta(minutes=ago))

    def _macro(self, **kw):
        data = {"name": "Refund ack", "body": "Hi {{customer.first_name}}, we're on it.",
                "actions": [{"type": "add_tags", "tags": ["refund"]}], **kw}
        return macros.save_macro(self.s, 1, data)

    def _jobs(self):
        return self.s.execute(sa.text("SELECT count(*) FROM job WHERE kind='macro_rule'")).scalar_one()

    # --- library / rendering -----------------------------------------------
    def test_render_uses_fallbacks_and_never_leaks_a_raw_placeholder(self):
        cid = self._case(name="Sara Khan")["case_id"]
        ctx = macros.context(self.s, 1, cid, agent_id=1)
        self.assertEqual(macros.render("Hi {{customer.first_name}} — {{agent.name}}", ctx),
                         "Hi Sara — agent1")
        anon = self._case(name=None, handle="anon")["case_id"]
        ctx = macros.context(self.s, 1, anon)
        self.assertEqual(macros.render("Hi {{customer.first_name}}!", ctx), "Hi there!")
        self.assertEqual(macros.render("Hi {{customer.first_name|friend}}!", ctx), "Hi friend!")
        self.assertEqual(macros.render("From {{agent.name}}", ctx), "From our team")
        with self.assertRaises(macros.MacroError):
            self._macro(body="Hi {{customer.shoe_size}}")

    def test_save_validates_shortcut_actions_and_quick_limit(self):
        self._macro(shortcut="/Refund")
        self.assertEqual(macros.list_macros(self.s, 1)[0]["shortcut"], "refund")
        with self.assertRaises(macros.MacroConflict):
            self._macro(name="Other", shortcut="refund")
        with self.assertRaises(macros.MacroError):
            macros.save_macro(self.s, 1, {"name": "empty", "body": "", "actions": []})
        with self.assertRaises(macros.MacroError):
            self._macro(name="bad", actions=[{"type": "set_status", "status": "closed"}])
        for n in range(macros.MAX_QUICK):
            self._macro(name=f"q{n}", is_quick=True)
        with self.assertRaises(macros.MacroError):
            self._macro(name="one too many", is_quick=True)
        order = [m["quick_order"] for m in macros.list_macros(self.s, 1, quick_only=True)]
        self.assertEqual(order, sorted(order))

    def test_partial_update_keeps_other_fields(self):
        mid = self._macro(shortcut="ack")
        macros.save_macro(self.s, 1, {"active": False}, macro_id=mid)
        row = macros.get_macro(self.s, 1, mid)
        self.assertFalse(row["active"])
        self.assertEqual(row["shortcut"], "ack")
        self.assertEqual(row["actions"], [{"type": "add_tags", "tags": ["refund"]}])
        self.assertEqual(macros.list_macros(self.s, 1), [])        # inactive hidden

    # --- actions -----------------------------------------------------------
    def test_apply_runs_every_action_and_logs_one_timeline_event(self):
        cid = self._case()["case_id"]
        mid = self._macro(actions=[
            {"type": "set_priority", "priority": "urgent"},
            {"type": "add_tags", "tags": ["Refund", "vip"]},
            {"type": "add_note", "body": "Refund for {{customer.first_name}}"},
            {"type": "assign", "mode": "agent", "user_id": 2},
            {"type": "set_status", "status": "in_progress"}])
        out = macros.apply_actions(self.s, 1, cid, macros.get_macro(self.s, 1, mid), actor=1)
        self.assertTrue(all(r["ok"] for r in out), out)
        row = self.s.execute(sa.text(
            'SELECT priority, tags, assignee_id, state FROM "case" WHERE id=:c'),
            {"c": cid}).one()
        self.assertEqual((row[0], row[1], row[2], row[3]), ("urgent", ["refund", "vip"], 2, "in_progress"))
        note = self.s.execute(sa.text("SELECT body FROM case_note WHERE case_id=:c"),
                              {"c": cid}).scalar_one()
        self.assertEqual(note, "Refund for Sara")
        kinds = [e["kind"] for e in cases.timeline(self.s, cid)]
        self.assertEqual(kinds.count("macro_applied"), 1)

    def test_a_failing_action_does_not_stop_the_others(self):
        cid = self._case()["case_id"]
        mid = self._macro(actions=[
            {"type": "assign", "mode": "agent", "user_id": 99},          # not a care agent
            {"type": "set_priority", "priority": "high"}])
        out = macros.apply_actions(self.s, 1, cid, macros.get_macro(self.s, 1, mid), actor=1)
        self.assertEqual([r["ok"] for r in out], [False, True])
        self.assertIn("care agent", out[0]["error"])
        self.assertEqual(self.s.execute(sa.text('SELECT priority FROM "case" WHERE id=:c'),
                                        {"c": cid}).scalar_one(), "high")

    def test_indexes_apply_only_the_ticked_actions(self):
        cid = self._case()["case_id"]
        mid = self._macro(actions=[{"type": "set_priority", "priority": "high"},
                                   {"type": "add_tags", "tags": ["x"]}])
        out = macros.apply_actions(self.s, 1, cid, macros.get_macro(self.s, 1, mid),
                                   actor=1, indexes={1})
        self.assertEqual([r["type"] for r in out], ["add_tags"])
        self.assertIsNone(self.s.execute(sa.text('SELECT priority FROM "case" WHERE id=:c'),
                                         {"c": cid}).scalar_one())

    # --- rules: validation --------------------------------------------------
    def _rule(self, macro_id=None, **kw):
        data = {"name": "Nudge", "macro_id": macro_id or self._macro(),
                "triggers": [{"type": "no_response", "minutes": 5}], **kw}
        return macro_rules.save_rule(self.s, 1, data)

    def test_rule_validation(self):
        with self.assertRaises(macros.MacroError):
            self._rule(triggers=[])
        with self.assertRaises(macros.MacroError):
            self._rule(triggers=[{"type": "no_response", "minutes": 0}])
        with self.assertRaises(macros.MacroError):
            self._rule(triggers=[{"type": "keyword", "words": []}])
        with self.assertRaises(macros.MacroError):
            self._rule(triggers=[{"type": "new_case"}, {"type": "new_case"}])
        selfy = self._macro(name="mine", actions=[{"type": "assign", "mode": "self"}])
        with self.assertRaises(macros.MacroError):
            self._rule(macro_id=selfy)
        actions_only = self._macro(name="tag only", body="")
        with self.assertRaises(macros.MacroError):                   # default hold needs a body
            self._rule(macro_id=actions_only)
        self._rule(macro_id=actions_only, reply_mode="none")

    # --- rules: triggers ----------------------------------------------------
    def test_multiple_triggers_each_start_the_rule(self):
        self._rule(triggers=[{"type": "new_case"},
                             {"type": "keyword", "words": ["refund"]},
                             {"type": "no_response", "minutes": 5}])
        first = self._case(body="Where is my REFUND?")
        self.assertEqual(self._jobs(), 2)                            # new_case + keyword
        self.assertEqual(self.s.execute(sa.text(
            "SELECT count(*) FROM scheduled_task WHERE name LIKE 'macro:no_response:%'")).scalar_one(), 1)
        cases.ingest_message(self.s, 1, platform="facebook", handle="sara",
                             body="still waiting", platform_ref="r2")
        self.assertEqual(self._jobs(), 2)                            # neither new nor keyword
        self.assertFalse(first["case_id"] is None)

    def test_channel_filter_and_stale_messages_never_arm(self):
        self._rule(triggers=[{"type": "new_case"}], filters={"channels": ["instagram"]})
        self._case(channel="facebook", handle="a")
        self.assertEqual(self._jobs(), 0)
        self._rule(name="all", triggers=[{"type": "new_case"}])
        self._case(handle="b", ago=180)                             # a backfilled old comment
        self.assertEqual(self._jobs(), 0)
        self._case(handle="c")
        self.assertEqual(self._jobs(), 1)

    def test_inactive_rule_does_nothing(self):
        rid = self._rule(triggers=[{"type": "new_case"}])
        macro_rules.save_rule(self.s, 1, {"active": False}, rule_id=rid)
        self._case()
        self.assertEqual(self._jobs(), 0)

    def test_sla_breach_starts_a_rule(self):
        self._rule(triggers=[{"type": "sla_breach"}])
        cid = self._case()["case_id"]
        routing.check_sla(self.s, {"ws": 1, "case_id": cid, "check": "first_response"})
        self.assertEqual(self._jobs(), 1)

    # --- rules: running -----------------------------------------------------
    def _payload(self, rid, cid, trigger="no_response", minutes=5):
        return {"ws": 1, "rule_id": rid, "case_id": cid, "trigger": trigger, "minutes": minutes}

    def test_no_response_fires_once_then_replies_are_held_for_approval(self):
        rid = self._rule(reply_mode="hold")
        cid = self._case(ago=6)["case_id"]
        out = macro_rules.run(self.s, self._payload(rid, cid), keys={})
        self.assertEqual(out["reply"]["state"], "pending")
        self.assertEqual(self.s.execute(sa.text('SELECT tags FROM "case" WHERE id=:c'),
                                        {"c": cid}).scalar_one(), ["refund"])
        self.assertEqual(self.s.execute(sa.text(
            "SELECT state FROM outbound_action WHERE id=:i"),
            {"i": out["reply"]["outbound_action_id"]}).scalar_one(), "pending")
        self.assertEqual(macro_rules.run(self.s, self._payload(rid, cid), keys={}),
                         {"skipped": "already_ran"})
        self.assertEqual(macro_rules.list_rules(self.s, 1)[0]["fired_count"], 1)

    def test_an_agent_reply_in_time_cancels_the_timer(self):
        rid = self._rule()
        cid = self._case(ago=6)["case_id"]
        cases.post_reply(self.s, cid, 1, body="on it", channel="facebook", actor=1)
        self.assertEqual(macro_rules.run(self.s, self._payload(rid, cid), keys={}),
                         {"skipped": "condition_cleared"})

    def test_too_early_closed_and_vip_filtered_are_skipped(self):
        rid = self._rule()
        cid = self._case(ago=1)["case_id"]
        self.assertEqual(macro_rules.run(self.s, self._payload(rid, cid), keys={}),
                         {"skipped": "condition_cleared"})
        vip = self._rule(name="vip only", filters={"vip_only": True})
        self.assertEqual(macro_rules.run(self.s, self._payload(vip, cid, "new_case"), keys={}),
                         {"skipped": "filtered"})
        cases.transition(self.s, cid, "closed", actor=1, closure_category="resolved")
        self.assertEqual(macro_rules.run(self.s, self._payload(rid, cid), keys={}),
                         {"skipped": "case_closed"})

    def test_unassigned_for_and_auto_assign(self):
        routing.set_policy(self.s, 1, assign_strategy="manual")      # else ingest assigns it first
        mid = self._macro(name="route", body="", actions=[{"type": "assign", "mode": "auto"}])
        rid = self._rule(macro_id=mid, reply_mode="none",
                         triggers=[{"type": "unassigned_for", "minutes": 5}])
        cid = self._case(ago=6)["case_id"]
        out = macro_rules.run(self.s, self._payload(rid, cid, "unassigned_for"), keys={})
        self.assertTrue(out["actions"][0]["ok"], out)
        self.assertIsNotNone(self.s.execute(sa.text('SELECT assignee_id FROM "case" WHERE id=:c'),
                                            {"c": cid}).scalar_one())

    def test_a_broken_hook_never_breaks_ingestion(self):
        self._rule(triggers=[{"type": "new_case"}])
        self.s.execute(sa.text("UPDATE care_macro_rule SET triggers = '[{\"type\": \"keyword\"}]'"))
        out = self._case(body="anything")                           # keyword trigger has no words
        self.assertTrue(out["new"])


class MacroApiTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        conn = self.app.db_operator()
        try:
            for name, role in (("u_agent", "agent"), ("u_lead", "team_lead")):
                repo.users.create(conn.session, username=name,
                                  password_hash=generate_password_hash("pw"),
                                  role=role, created_at=self.app.now())
                uid = conn.execute('SELECT id FROM "user" WHERE username=?', (name,)).fetchone()[0]
                repo.rbac.set_user_roles(conn.session, uid, [role])
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

    def test_lead_authors_agent_uses(self):
        self._login("u_lead", "pw")
        res = self._send("post", "/api/v1/macros", {
            "name": "Refund", "body": "Hi {{customer.first_name|there}}", "shortcut": "refund",
            "is_quick": True, "actions": [{"type": "set_priority", "priority": "high"}]})
        self.assertEqual(res.status_code, 200, res.get_data(as_text=True))
        mid = res.get_json()["id"]
        self.assertEqual(self._send("post", "/api/v1/macros",
                                    {"name": "Dup", "body": "x", "shortcut": "refund"}).status_code, 409)
        self.assertEqual(self._send("post", "/api/v1/macros",
                                    {"name": "Bad", "body": "{{nope.x}}"}).status_code, 400)

        self._login("admin", "admin123")
        case_id = self._send("post", "/api/v1/care/cases/ingest", {
            "platform": "facebook", "handle": "sara", "display_name": "Sara Khan",
            "body": "help"}).get_json()["case_id"]

        self._login("u_agent", "pw")
        listed = self._send("get", "/api/v1/macros").get_json()["macros"]
        self.assertEqual([m["id"] for m in listed], [mid])
        self.assertEqual(self._send("post", "/api/v1/macros", {"name": "x", "body": "y"}).status_code, 403)
        self.assertEqual(self._send("put", f"/api/v1/macros/{mid}", {"body": "z"}).status_code, 403)
        self.assertEqual(self._send("delete", f"/api/v1/macros/{mid}").status_code, 403)
        self.assertEqual(self._send("get", "/api/v1/macro-rules").status_code, 403)
        self.assertEqual(self._send("post", "/api/v1/macro-rules", {"name": "r"}).status_code, 403)

        self._login("admin", "admin123")
        prev = self._send("post", f"/api/v1/care/cases/{case_id}/macros/{mid}/preview").get_json()
        self.assertEqual(prev["text"], "Hi Sara")
        self.assertEqual(prev["actions"][0]["summary"], "Set priority to high")
        done = self._send("post", f"/api/v1/care/cases/{case_id}/macros/{mid}/apply", {}).get_json()
        self.assertTrue(done["ok"], done)
        detail = self._send("get", f"/api/v1/care/cases/{case_id}").get_json()
        self.assertEqual(detail["case"]["priority"], "high")
        self.assertIn("macro_applied", [e["kind"] for e in detail["timeline"]])
        queue = self._send("get", "/api/v1/care/cases?tab=queue").get_json()["cases"]
        self.assertEqual([c["priority"] for c in queue if c["id"] == case_id], ["high"])   # macro-set beats SLA-derived
        self.assertEqual(self._send("delete", f"/api/v1/macros/{mid}").status_code, 200)
        self.assertEqual(self._send("post", f"/api/v1/care/cases/{case_id}/macros/{mid}/apply",
                                    {}).status_code, 404)

    def test_rule_crud_over_the_api(self):
        self._login("u_lead", "pw")
        mid = self._send("post", "/api/v1/macros", {"name": "Nudge", "body": "Still there?"}).get_json()["id"]
        res = self._send("post", "/api/v1/macro-rules", {
            "name": "5 min nudge", "macro_id": mid, "reply_mode": "hold",
            "triggers": [{"type": "no_response", "minutes": 5}, {"type": "sla_breach"}]})
        self.assertEqual(res.status_code, 200, res.get_data(as_text=True))
        rid = res.get_json()["id"]
        rules = self._send("get", "/api/v1/macro-rules").get_json()["rules"]
        self.assertEqual(rules[0]["macro_name"], "Nudge")
        self.assertEqual(len(rules[0]["triggers"]), 2)
        self.assertEqual(self._send("put", f"/api/v1/macro-rules/{rid}", {"active": False}).status_code, 200)
        self.assertEqual(self._send("post", "/api/v1/macro-rules", {
            "name": "bad", "macro_id": mid, "triggers": []}).status_code, 400)
        self.assertEqual(self._send("delete", f"/api/v1/macro-rules/{rid}").status_code, 200)
        self.assertEqual(self._send("delete", f"/api/v1/macro-rules/{rid}").status_code, 404)


if __name__ == "__main__":
    unittest.main()
