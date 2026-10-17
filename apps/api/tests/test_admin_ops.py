"""F6 admin ops — source retry/circuit-reset, routing policy, job/scheduler
console. All new admin endpoints backing the F6 UI packets."""
import unittest

import app as _app
from core import sources
from jobs import runner

from ._db import ApiTestCase


class AdminOpsApiTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        token = self.client.get("/api/v1/csrf").get_json()["token"]
        self.client.post("/api/v1/auth/login",
                         json={"username": "admin", "password": "admin123"},
                         headers={"X-CSRF-Token": token})
        with self.client.session_transaction() as s:
            self.csrf = s.get("csrf_token", "")

    def _post(self, path, body=None):
        return self.client.post(path, json=body or {}, headers={"X-CSRF-Token": self.csrf})

    def test_source_retry_and_reset_circuit(self):
        sid = next(iter(sources.SOURCES))
        r = self._post(f"/api/v1/admin/sources/{sid}/retry")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["queued"])

        r2 = self._post(f"/api/v1/admin/sources/{sid}/reset-circuit")
        self.assertEqual(r2.status_code, 200)

        self.assertEqual(self._post("/api/v1/admin/sources/nope/retry").status_code, 404)
        self.assertEqual(self._post("/api/v1/admin/sources/nope/reset-circuit").status_code, 404)

    def test_roles_catalogue_lists_the_six_rbac_roles(self):
        r = self.client.get("/api/v1/admin/roles", headers={"X-CSRF-Token": self.csrf})
        keys = {row["key"] for row in r.get_json()["roles"]}
        self.assertEqual(keys, {"bank_viewer", "agent", "senior_agent",
                                "supervisor", "team_lead", "admin"})

    def test_create_an_agent_is_scoped_to_its_workspace_and_can_use_care(self):
        r = self._post("/api/v1/admin/users",
                       {"username": "agent1", "password": "pw123456",
                        "role": "agent", "workspace_id": 1})
        self.assertEqual(r.status_code, 200)
        users = self.client.get("/api/v1/admin/users",
                                headers={"X-CSRF-Token": self.csrf}).get_json()["users"]
        row = next(u for u in users if u["username"] == "agent1")
        self.assertEqual(row["role"], "agent")

        # logs in and actually holds the agent grant (care:view), not admin's
        self.client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": self.csrf})
        token = self.client.get("/api/v1/csrf").get_json()["token"]
        login = self.client.post("/api/v1/auth/login",
                                 json={"username": "agent1", "password": "pw123456"},
                                 headers={"X-CSRF-Token": token})
        self.assertEqual(login.status_code, 200)
        self.assertEqual(self.client.get("/api/v1/admin/users",
                         headers={"X-CSRF-Token": token}).status_code, 403)

    def test_a_new_agent_is_immediately_assignable_in_the_care_roster(self):
        # real bug: creating an agent granted the role but never added a
        # care_agent row, so they were invisible in every "Assign to" picker.
        r = self._post("/api/v1/admin/users",
                       {"username": "agent2", "password": "pw123456",
                        "role": "senior_agent", "workspace_id": 1})
        self.assertEqual(r.status_code, 200)
        roster = self.client.get("/api/v1/care/roster",
                                 headers={"X-CSRF-Token": self.csrf}).get_json()["agents"]
        self.assertIn("agent2", [a["username"] for a in roster])

    def test_a_new_viewer_is_not_added_to_the_care_roster(self):
        self._post("/api/v1/admin/users",
                   {"username": "viewer9", "password": "pw123456",
                    "role": "bank_viewer", "workspace_id": 1})
        roster = self.client.get("/api/v1/care/roster",
                                 headers={"X-CSRF-Token": self.csrf}).get_json()["agents"]
        self.assertNotIn("viewer9", [a["username"] for a in roster])

    def test_a_workspace_is_required_for_every_role_but_admin(self):
        r = self._post("/api/v1/admin/users",
                       {"username": "orphan", "password": "pw123456", "role": "agent"})
        self.assertEqual(r.status_code, 400)

        r2 = self._post("/api/v1/admin/users",
                        {"username": "admin2", "password": "pw123456", "role": "admin"})
        self.assertEqual(r2.status_code, 200)
        users = self.client.get("/api/v1/admin/users",
                                headers={"X-CSRF-Token": self.csrf}).get_json()["users"]
        row = next(u for u in users if u["username"] == "admin2")
        self.assertIsNone(row["workspace"])

    # --- edit / deactivate / password / delete (Hamza, 2026-09-11: "option
    # to edit access type/workspace of a user, delete, deactivate, and
    # change pw") -----------------------------------------------------
    def _user_id(self, username):
        users = self.client.get("/api/v1/admin/users",
                                headers={"X-CSRF-Token": self.csrf}).get_json()["users"]
        return next(u["id"] for u in users if u["username"] == username)

    def _create(self, username, role="agent", workspace_id=1):
        r = self._post("/api/v1/admin/users",
                       {"username": username, "password": "pw123456",
                        "role": role, "workspace_id": workspace_id})
        self.assertEqual(r.status_code, 200, r.get_json())
        return self._user_id(username)

    def test_edit_access_changes_role_and_workspace(self):
        uid = self._create("edituser", role="agent")
        r = self.client.put(f"/api/v1/admin/users/{uid}",
                            json={"role": "senior_agent"},
                            headers={"X-CSRF-Token": self.csrf})
        self.assertEqual(r.status_code, 200)
        row = next(u for u in self.client.get(
            "/api/v1/admin/users", headers={"X-CSRF-Token": self.csrf}
        ).get_json()["users"] if u["id"] == uid)
        self.assertEqual(row["role"], "senior_agent")
        self.assertEqual(row["workspace_id"], 1)  # unspecified -> kept

    def test_edit_access_rejects_an_unknown_role(self):
        uid = self._create("edituser2")
        r = self.client.put(f"/api/v1/admin/users/{uid}", json={"role": "overlord"},
                            headers={"X-CSRF-Token": self.csrf})
        self.assertEqual(r.status_code, 400)

    def test_edit_access_on_a_missing_user_is_404(self):
        r = self.client.put("/api/v1/admin/users/999999", json={"role": "agent"},
                            headers={"X-CSRF-Token": self.csrf})
        self.assertEqual(r.status_code, 404)

    def test_deactivate_then_reactivate(self):
        uid = self._create("deactme")
        off = self._post(f"/api/v1/admin/users/{uid}/active", {"active": False})
        self.assertEqual(off.status_code, 200)
        row = next(u for u in self.client.get(
            "/api/v1/admin/users", headers={"X-CSRF-Token": self.csrf}
        ).get_json()["users"] if u["id"] == uid)
        self.assertFalse(row["active"])

        on = self._post(f"/api/v1/admin/users/{uid}/active", {"active": True})
        self.assertEqual(on.status_code, 200)
        row2 = next(u for u in self.client.get(
            "/api/v1/admin/users", headers={"X-CSRF-Token": self.csrf}
        ).get_json()["users"] if u["id"] == uid)
        self.assertTrue(row2["active"])

    def test_a_deactivated_user_cannot_log_in(self):
        uid = self._create("deactlogin")
        self._post(f"/api/v1/admin/users/{uid}/active", {"active": False})
        token = self.client.get("/api/v1/csrf").get_json()["token"]
        login = self.client.post("/api/v1/auth/login",
                                 json={"username": "deactlogin", "password": "pw123456"},
                                 headers={"X-CSRF-Token": token})
        self.assertEqual(login.status_code, 401)

    def test_cannot_deactivate_own_account(self):
        r = self._post(f"/api/v1/admin/users/{self._user_id('admin')}/active",
                       {"active": False})
        self.assertEqual(r.status_code, 400)

    def test_set_password_then_login_with_it(self):
        uid = self._create("pwuser")
        r = self._post(f"/api/v1/admin/users/{uid}/password", {"password": "newpassword1"})
        self.assertEqual(r.status_code, 200)
        token = self.client.get("/api/v1/csrf").get_json()["token"]
        login = self.client.post("/api/v1/auth/login",
                                 json={"username": "pwuser", "password": "newpassword1"},
                                 headers={"X-CSRF-Token": token})
        self.assertEqual(login.status_code, 200)

    def test_set_password_rejects_a_short_password(self):
        uid = self._create("pwuser2")
        r = self._post(f"/api/v1/admin/users/{uid}/password", {"password": "short"})
        self.assertEqual(r.status_code, 400)

    def test_delete_a_never_used_account(self):
        uid = self._create("neverused")
        r = self.client.delete(f"/api/v1/admin/users/{uid}",
                               headers={"X-CSRF-Token": self.csrf})
        self.assertEqual(r.status_code, 200)
        users = self.client.get("/api/v1/admin/users",
                                headers={"X-CSRF-Token": self.csrf}).get_json()["users"]
        self.assertNotIn(uid, [u["id"] for u in users])

    def test_cannot_delete_own_account(self):
        r = self.client.delete(f"/api/v1/admin/users/{self._user_id('admin')}",
                               headers={"X-CSRF-Token": self.csrf})
        self.assertEqual(r.status_code, 400)

    def test_cannot_delete_a_user_with_real_activity(self):
        from core import cases as cases_core
        uid = self._create("busyagent")
        conn = self.app.db_operator()
        try:
            cid = cases_core.ingest_message(
                conn.session, 1, platform="x", handle="@c1", body="help")["case_id"]
            cases_core.assign(conn.session, cid, uid, actor=uid)
            conn.commit()
        finally:
            conn.close()
        r = self.client.delete(f"/api/v1/admin/users/{uid}",
                               headers={"X-CSRF-Token": self.csrf})
        self.assertEqual(r.status_code, 409)
        # still there, untouched
        users = self.client.get("/api/v1/admin/users",
                                headers={"X-CSRF-Token": self.csrf}).get_json()["users"]
        self.assertIn(uid, [u["id"] for u in users])

    def test_an_unknown_role_is_rejected(self):
        r = self._post("/api/v1/admin/users",
                       {"username": "x", "password": "pw123456",
                        "role": "superuser", "workspace_id": 1})
        self.assertEqual(r.status_code, 400)

    def test_duplicate_username_is_409(self):
        r = self._post("/api/v1/admin/users",
                       {"username": "dup1", "password": "pw123456", "workspace_id": 1})
        self.assertEqual(r.status_code, 200)
        r2 = self._post("/api/v1/admin/users",
                        {"username": "dup1", "password": "pw123456", "workspace_id": 1})
        self.assertEqual(r2.status_code, 409)

    def test_care_bridge_run_ingests_a_complaint_mention_into_a_case(self):
        conn = self.app.db_operator()
        try:
            focus = conn.execute(
                "SELECT id FROM brand WHERE workspace_id=1 AND is_focus=1").fetchone()[0]
            conn.execute(
                """INSERT INTO item(workspace_id,surface,source,source_kind,external_id,
                   url,author,published_at,body,raw_json,collected_at,content_hash)
                   VALUES(1,'youtube','youtube_v3','public','comment:cb1',
                   'https://x/1','A Customer','2026-09-01T00:00:00Z',
                   'Branch service was terrible.','{}','now','cb1')""")
            item_id = conn.execute(
                "SELECT id FROM item WHERE external_id='comment:cb1'").fetchone()[0]
            conn.execute(
                "INSERT INTO mention(workspace_id,item_id,brand_id,rule) VALUES(1,?,?,'exact_name')",
                (item_id, focus))
            mention_id = conn.execute(
                "SELECT id FROM mention WHERE item_id=?", (item_id,)).fetchone()[0]
            conn.execute(
                """INSERT INTO mention_class(workspace_id,mention_id,category,model_id,classified_at)
                   VALUES (1,?,?,'rule','now')""", (mention_id, "complaint"))
            conn.commit()
        finally:
            conn.close()

        r = self._post("/api/v1/admin/care/bridge/run")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"scanned": 1, "created": 1})

        # idempotent — a second run finds nothing new
        r2 = self._post("/api/v1/admin/care/bridge/run")
        self.assertEqual(r2.get_json(), {"scanned": 0, "created": 0})

    def test_web_backfill_queues_a_collection_job_scoped_to_that_source(self):
        r = self._post("/api/v1/admin/backfill/web/run")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["queued"])
        conn = self.app.db_operator()
        try:
            row = conn.execute(
                "SELECT kind, payload FROM job WHERE kind='collection' ORDER BY id DESC "
                "LIMIT 1").fetchone()
        finally:
            conn.close()
        self.assertEqual(row[1]["only_sources"], ["web_backfill"])

    def test_web_backfill_conflicts_while_a_run_is_already_in_progress(self):
        from db.repositories import runs
        conn = self.app.db_operator()
        try:
            runs.create(conn.session, run_id="already-running", workspace_id=1,
                       started_at=_app.now())
            conn.commit()
        finally:
            conn.close()
        self.assertEqual(self._post("/api/v1/admin/backfill/web/run").status_code, 409)

    def test_source_enable_disable_round_trip(self):
        sid = "googlenews_rss"
        listing = self.client.get("/api/v1/admin/sources").get_json()["sources"]
        self.assertTrue(next(s for s in listing if s["id"] == sid)["enabled"])

        r = self.client.put(f"/api/v1/admin/sources/{sid}/enabled",
                            json={"enabled": False}, headers={"X-CSRF-Token": self.csrf})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.get_json()["enabled"])

        listing = self.client.get("/api/v1/admin/sources").get_json()["sources"]
        self.assertFalse(next(s for s in listing if s["id"] == sid)["enabled"])
        # unrelated sources stay on
        self.assertTrue(next(s for s in listing if s["id"] == "regulatory_watch")["enabled"])

        self.client.put(f"/api/v1/admin/sources/{sid}/enabled",
                        json={"enabled": True}, headers={"X-CSRF-Token": self.csrf})
        listing = self.client.get("/api/v1/admin/sources").get_json()["sources"]
        self.assertTrue(next(s for s in listing if s["id"] == sid)["enabled"])

    def test_source_enable_unknown_source_is_404(self):
        self.assertEqual(
            self.client.put("/api/v1/admin/sources/nope/enabled", json={"enabled": False},
                            headers={"X-CSRF-Token": self.csrf}).status_code, 404)

    def test_routing_policy_get_and_set(self):
        got = self.client.get("/api/v1/admin/routing-policy").get_json()
        self.assertIn("first_response_sla", got["policy"])
        self.assertIn("closure_categories_in_use", got)

        r = self.client.put("/api/v1/admin/routing-policy",
                            json={"first_response_sla": 600},
                            headers={"X-CSRF-Token": self.csrf})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["policy"]["first_response_sla"], 600)

    def test_jobs_queue_and_scheduled(self):
        q = self.client.get("/api/v1/admin/jobs/queue").get_json()
        self.assertIn("by_state", q)
        for state in ("queued", "running", "done", "dead"):
            self.assertIn(state, q["by_state"])

        self.assertEqual(self._post("/api/v1/admin/jobs/999999999/retry").status_code, 404)

        sched = self.client.get("/api/v1/admin/jobs/scheduled").get_json()
        self.assertIn("scheduled", sched)

    def test_retry_a_dead_job(self):
        conn = self.app.db_operator()
        try:
            jid = runner.enqueue(conn.session, "collection", {}, max_attempts=1)
            conn.execute("UPDATE job SET state='dead', attempts=1 WHERE id=?", (jid,))
            conn.commit()
        finally:
            conn.close()
        r = self._post(f"/api/v1/admin/jobs/{jid}/retry")
        self.assertEqual(r.status_code, 200)
        conn = self.app.db_operator()
        try:
            state = conn.execute("SELECT state FROM job WHERE id=?", (jid,)).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(state, "queued")

    def test_dm_sync_run_400s_with_no_meta_creds_configured(self):
        r = self._post("/api/v1/admin/dm/sync/run")
        self.assertEqual(r.status_code, 400)
        self.assertIn("META_", r.get_json()["error"])

    def test_dm_sync_run_ingests_a_new_dm_into_care(self):
        from unittest.mock import patch

        from core import collector

        _app.persist_key(1, "META_ACCESS_TOKEN", "user-token")
        _app.persist_key(1, "META_PAGE_ID", "999")
        accounts = '{"data": [{"id": "999", "access_token": "page-token"}]}'
        convs = ('{"data": [{"id": "t_1", "participants": {"data": '
                '[{"id": "1", "name": "A Customer"}, {"id": "999"}]}}]}')
        msgs = ('{"data": [{"id": "m_1", "from": {"id": "1"}, '
               '"message": "hi", "created_time": "2026-09-08T05:11:39+0000"}]}')
        empty = '{"data": []}'

        def fake_get(url, timeout=30):
            if "me/accounts" in url:
                return accounts
            if "platform=messenger" in url:
                return convs
            if "/t_1/messages" in url:
                return msgs
            return empty

        with patch.object(collector, "_get", side_effect=fake_get):
            r = self._post("/api/v1/admin/dm/sync/run")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["messenger"]["ingested"], 1)

    def test_media_backfill_run_fills_in_real_media_on_a_stale_post(self):
        from unittest.mock import patch

        from core import collector
        conn = self.app.db_operator()
        try:
            conn.execute(
                """INSERT INTO item(workspace_id,surface,source,source_kind,external_id,
                   url,published_at,body,raw_json,collected_at,content_hash)
                   VALUES(1,'x','meta_facebook','public','fb:p1','https://s',
                   '2026-09-01T00:00:00Z','body','{"kind":"post"}','now','p1')""")
            conn.commit()
        finally:
            conn.close()

        accounts = '{"data": [{"id": "999", "access_token": "page-token"}]}'
        post = ('{"full_picture": "https://x/p1.jpg", '
               '"attachments": {"data": [{"media_type": "photo"}]}}')
        _app.persist_key(1, "META_ACCESS_TOKEN", "user-token")
        _app.persist_key(1, "META_PAGE_ID", "999")
        with patch.object(collector, "_get", side_effect=[accounts, post]):
            r = self._post("/api/v1/admin/owned-posts/media-backfill/run")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"checked": 1, "updated": 1})

        import json
        conn = self.app.db_operator()
        try:
            raw = json.loads(conn.execute(
                "SELECT raw_json FROM item WHERE external_id='fb:p1'").fetchone()[0])
        finally:
            conn.close()
        self.assertEqual(raw["media"], {"type": "photo", "image": "https://x/p1.jpg"})


if __name__ == "__main__":
    unittest.main()
