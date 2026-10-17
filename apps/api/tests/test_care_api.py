"""P3.4 — the care console API (backend)."""
import unittest

from ._db import ApiTestCase


class CareApiTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self._login("admin", "admin123")

    def _login(self, user, pw):
        token = self.client.get("/api/v1/csrf").get_json()["token"]
        self.client.post("/api/v1/auth/login", json={"username": user, "password": pw},
                         headers={"X-CSRF-Token": token})
        with self.client.session_transaction() as s:
            self.csrf = s.get("csrf_token", "")

    def _post(self, path, body):
        return self.client.post(path, json=body, headers={"X-CSRF-Token": self.csrf})

    def _ingest(self, **b):
        b.setdefault("platform", "x")
        b.setdefault("handle", "@cust")
        b.setdefault("body", "I need help with a charge")
        return self._post("/api/v1/care/cases/ingest", b)

    def test_ingest_opens_a_case_visible_in_the_queue(self):
        resp = self._ingest()
        self.assertEqual(resp.status_code, 200)
        cid = resp.get_json()["case_id"]
        self.assertTrue(resp.get_json()["new"])

        queue = self.client.get("/api/v1/care/cases?tab=queue").get_json()
        self.assertIn(cid, [c["id"] for c in queue["cases"]])

    def test_case_detail_has_messages_customer_and_timeline(self):
        cid = self._ingest(handle="@sam", body="hello").get_json()["case_id"]
        body = self.client.get(f"/api/v1/care/cases/{cid}").get_json()
        self.assertEqual(body["customer"]["handle"], "@sam")
        self.assertEqual(len(body["messages"]), 1)
        self.assertEqual(body["messages"][0]["direction"], "inbound")
        self.assertEqual(body["timeline"][0]["kind"], "created")

    def test_timeline_resolves_assign_and_reassign_authorship_to_usernames(self):
        # Hamza: "with every message, assignment/reassignment authorship/
        # ownership is logged and displayed eg admin assigned this convo to
        # hamza_rep etc." -- actor/target ids were already recorded; this is
        # the resolve-to-real-usernames half.
        from werkzeug.security import generate_password_hash
        import app as _app
        conn = _app.db_operator()
        try:
            conn.execute(
                'INSERT INTO "user"(username,password_hash,role,workspace_id,created_at) '
                "VALUES('hamza_rep',?,'agent',1,'now')",
                (generate_password_hash("pw123456"),))
            rep_id = conn.execute(
                'SELECT id FROM "user" WHERE username=?', ("hamza_rep",)).fetchone()[0]
            conn.commit()
        finally:
            conn.close()

        cid = self._ingest(handle="@authtest").get_json()["case_id"]
        self.assertEqual(
            self._post(f"/api/v1/care/cases/{cid}/assign", {"user_id": rep_id}).status_code, 200)
        self.assertEqual(
            self._post(f"/api/v1/care/cases/{cid}/reassign",
                      {"user_id": rep_id, "reason": "coverage"}).status_code, 200)

        timeline = self.client.get(f"/api/v1/care/cases/{cid}").get_json()["timeline"]
        assigned = next(e for e in timeline if e["kind"] == "assigned")
        reassigned = next(e for e in timeline if e["kind"] == "reassigned")
        self.assertEqual(assigned["actor_username"], "admin")
        self.assertEqual(assigned["detail"]["assignee_username"], "hamza_rep")
        self.assertEqual(reassigned["actor_username"], "admin")
        self.assertEqual(reassigned["detail"]["to_username"], "hamza_rep")

    def test_note_author_is_resolved_to_a_username(self):
        cid = self._ingest(handle="@notetest").get_json()["case_id"]
        self._post(f"/api/v1/care/cases/{cid}/note", {"body": "internal note"})
        notes = self.client.get(f"/api/v1/care/cases/{cid}").get_json()["notes"]
        self.assertEqual(notes[0]["author_username"], "admin")

    def test_reply_sends_via_the_write_layer_and_advances_state(self):
        cid = self._ingest().get_json()["case_id"]
        resp = self._post(f"/api/v1/care/cases/{cid}/reply",
                          {"text": "We're looking into it", "platform": "x",
                           "target_ref": "dm:1"})
        self.assertEqual(resp.status_code, 200)
        j = resp.get_json()
        self.assertEqual(j["state"], "sent")
        self.assertIsNotNone(j["outbound_action_id"])

        detail = self.client.get(f"/api/v1/care/cases/{cid}").get_json()
        self.assertEqual(detail["case"]["state"], "in_progress")
        self.assertEqual(detail["messages"][-1]["direction"], "outbound")

        conn = self.app.db_operator()
        try:
            oa = conn.execute("SELECT platform, action, state FROM outbound_action "
                              "ORDER BY id DESC LIMIT 1").fetchone()
        finally:
            conn.close()
        self.assertEqual(oa, ("x", "reply_public", "sent"))

    def test_reply_on_a_facebook_channel_case_works(self):
        # F7.5 — a Playwright interaction test caught this 500ing: the case's
        # channel/customer.platform ("facebook", the read-side surface name)
        # was forwarded straight into write.client_for, which only knew
        # "meta". Fixed by aliasing in integrations/write/platforms.py.
        cid = self._ingest(platform="facebook").get_json()["case_id"]
        resp = self._post(f"/api/v1/care/cases/{cid}/reply",
                          {"text": "On it", "platform": "facebook", "target_ref": "post:1"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["state"], "sent")

    def test_dm_reply_records_the_platforms_own_message_id_not_the_recipient(self):
        # C-117 (Hamza, 2026-09-12): platform_ref on a DM reply must be the
        # Send API's own message id, not the recipient ref -- otherwise
        # dm_sync.py's next poll can't recognise this reply as already-seen
        # (core/dm_sync.py::_already_seen matches on platform_ref) and
        # re-ingests it, showing the same reply twice in the console.
        cid = self._ingest(platform="facebook", channel="messenger",
                           handle="psid_1").get_json()["case_id"]
        resp = self._post(f"/api/v1/care/cases/{cid}/reply",
                          {"text": "hi", "platform": "facebook"})
        self.assertEqual(resp.status_code, 200)

        detail = self.client.get(f"/api/v1/care/cases/{cid}").get_json()
        ref = detail["messages"][-1]["platform_ref"]
        self.assertNotEqual(ref, "psid_1")
        self.assertTrue(str(ref).startswith("mock:meta:reply_dm:"), ref)

    def test_reply_on_an_unsupported_platform_is_a_clean_400_not_a_500(self):
        cid = self._ingest(platform="whatsapp").get_json()["case_id"]
        resp = self._post(f"/api/v1/care/cases/{cid}/reply",
                          {"text": "On it", "platform": "whatsapp"})
        self.assertEqual(resp.status_code, 400)

    def test_note_and_transition(self):
        cid = self._ingest().get_json()["case_id"]
        self.assertEqual(
            self._post(f"/api/v1/care/cases/{cid}/note", {"body": "internal"}).status_code, 200)
        self.assertEqual(
            self._post(f"/api/v1/care/cases/{cid}/transition", {"state": "closed"}
                       ).status_code, 400)                       # needs a category
        ok = self._post(f"/api/v1/care/cases/{cid}/transition",
                        {"state": "closed", "closure_category": "resolved"})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(
            self.client.get(f"/api/v1/care/cases/{cid}").get_json()["case"]["state"],
            "closed")

    def test_bad_tab_is_rejected(self):
        self.assertEqual(self.client.get("/api/v1/care/cases?tab=nope").status_code, 400)

    def test_agents_endpoint(self):
        self.assertEqual(self.client.get("/api/v1/care/agents").status_code, 200)

    # --- customer profile edit (Hamza: "these details should be editable") --
    def _put(self, path, body):
        return self.client.put(path, json=body, headers={"X-CSRF-Token": self.csrf})

    def test_update_customer_edits_the_editable_fields(self):
        cid = self._ingest(handle="@editme").get_json()["case_id"]
        customer_id = self.client.get(f"/api/v1/care/cases/{cid}").get_json()["customer"]["id"]
        r = self._put(f"/api/v1/care/customers/{customer_id}", {
            "preferred_name": "Ali", "email": "ali@example.com", "vip": True,
            "tags": "priority, escalation",
        })
        self.assertEqual(r.status_code, 200)
        customer = self.client.get(f"/api/v1/care/cases/{cid}").get_json()["customer"]
        self.assertEqual(customer["preferred_name"], "Ali")
        self.assertEqual(customer["email"], "ali@example.com")
        self.assertTrue(customer["vip"])
        self.assertEqual(customer["tags"], "priority, escalation")

    def test_update_customer_never_touches_the_match_key(self):
        # platform/handle aren't in the request body's allowed field set at
        # all -- posting them must be silently ignored, not error, and must
        # not change the stored value core/cases.py::resolve_customer()
        # matches new inbound messages against.
        cid = self._ingest(handle="@keepme").get_json()["case_id"]
        customer_id = self.client.get(f"/api/v1/care/cases/{cid}").get_json()["customer"]["id"]
        r = self._put(f"/api/v1/care/customers/{customer_id}",
                      {"handle": "@hijacked", "platform": "instagram", "notes": "ok"})
        self.assertEqual(r.status_code, 200)
        customer = self.client.get(f"/api/v1/care/cases/{cid}").get_json()["customer"]
        self.assertEqual(customer["handle"], "@keepme")
        self.assertEqual(customer["platform"], "x")
        self.assertEqual(customer["notes"], "ok")

    def test_update_customer_requires_at_least_one_editable_field(self):
        cid = self._ingest(handle="@nofields").get_json()["case_id"]
        customer_id = self.client.get(f"/api/v1/care/cases/{cid}").get_json()["customer"]["id"]
        r = self._put(f"/api/v1/care/customers/{customer_id}", {})
        self.assertEqual(r.status_code, 400)

    def test_update_a_customer_in_another_workspace_is_404(self):
        r = self._put("/api/v1/care/customers/999999", {"notes": "x"})
        self.assertEqual(r.status_code, 404)

    def test_viewer_is_forbidden(self):
        self._login("bank", "viewer123")
        self.assertEqual(self.client.get("/api/v1/care/cases").status_code, 403)
        self.assertEqual(self._ingest().status_code, 403)


if __name__ == "__main__":
    unittest.main()
