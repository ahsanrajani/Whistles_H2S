"""Vantage AI-visibility panel — the admin-gated API surface. Every LLM call
is mocked; nothing here reaches the network."""
import unittest
from unittest.mock import patch

from integrations import llm
from jobs import worker

from ._db import ApiTestCase


class VantageApiTests(ApiTestCase):
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

    def test_prompts_auto_seed_on_first_call(self):
        resp = self.client.get("/api/v1/vantage/prompts")
        self.assertEqual(resp.status_code, 200)
        prompts = resp.get_json()["prompts"]
        self.assertGreater(len(prompts), 0)
        self.assertTrue(all(p["active"] for p in prompts))
        # idempotent — a second call doesn't duplicate
        again = self.client.get("/api/v1/vantage/prompts").get_json()["prompts"]
        self.assertEqual(len(again), len(prompts))

    def test_add_toggle_and_delete_a_prompt(self):
        pid = self._post("/api/v1/vantage/prompts",
                         {"prompt_text": "Is Chase Securities regulated?"}).get_json()["id"]
        listing = self.client.get("/api/v1/vantage/prompts").get_json()["prompts"]
        self.assertIn(pid, [p["id"] for p in listing])

        r = self.client.patch(f"/api/v1/vantage/prompts/{pid}", json={"active": False},
                              headers={"X-CSRF-Token": self.csrf})
        self.assertEqual(r.status_code, 200)
        listing = self.client.get("/api/v1/vantage/prompts").get_json()["prompts"]
        self.assertFalse(next(p for p in listing if p["id"] == pid)["active"])

        r = self.client.delete(f"/api/v1/vantage/prompts/{pid}",
                               headers={"X-CSRF-Token": self.csrf})
        self.assertEqual(r.status_code, 200)
        listing = self.client.get("/api/v1/vantage/prompts").get_json()["prompts"]
        self.assertNotIn(pid, [p["id"] for p in listing])

    def test_empty_prompt_text_is_400(self):
        self.assertEqual(
            self._post("/api/v1/vantage/prompts", {"prompt_text": "  "}).status_code, 400)

    def test_run_asks_every_active_prompt_and_model_then_insights_reflect_it(self):
        with patch.object(llm, "ask",
                          return_value=("google", "gemini-3.5-flash",
                                       "Bank Alfalah is a well-known bank.")):
            resp = self._post("/api/v1/vantage/panel/run")
            self.assertEqual(resp.status_code, 200)
            queued = resp.get_json()
            self.assertTrue(queued["ok"])
            # enqueued, not run inline: 30 sequential LLM calls outlived the
            # proxy's socket when this ran on the request thread
            self.assertTrue(queued["job_id"].startswith("vantage-"))
            self.assertTrue(worker.run_one(kinds=["vantage_panel"]))
        status = self.client.get(f"/api/v1/jobs/{queued['job_id']}").get_json()
        self.assertEqual(status["state"], "done")
        from db.session import get_operator_session
        s = get_operator_session()
        try:
            from sqlalchemy import text
            out = dict(s.execute(text("SELECT result FROM job WHERE kind='vantage_panel' "
                                      "ORDER BY id DESC LIMIT 1")).scalar_one())
        finally:
            s.close()
        self.assertEqual(out["asked"], out["prompts"] * out["models"])
        self.assertEqual(out["failed"], 0)

        insights = self.client.get("/api/v1/vantage/insights").get_json()
        self.assertEqual(insights["total_responses"], out["asked"])
        self.assertTrue(any(b["is_focus"] for b in insights["brands"]))
        self.assertIn("headline", insights)
        self.assertIn("improvements", insights)

        evidence = self.client.get("/api/v1/vantage/evidence").get_json()["responses"]
        self.assertEqual(len(evidence), out["asked"])
        self.assertTrue(all(r["prompt_text"] for r in evidence))
        self.assertTrue(all("response_text" in r for r in evidence))

    def _login_viewer(self):
        self.client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": self.csrf})
        token = self.client.get("/api/v1/csrf").get_json()["token"]
        self.client.post("/api/v1/auth/login",
                         json={"username": "bank", "password": "viewer123"},
                         headers={"X-CSRF-Token": token})
        with self.client.session_transaction() as s:
            return s.get("csrf_token", "")

    def test_viewer_role_cannot_run_or_edit_the_panel(self):
        csrf = self._login_viewer()
        resp = self.client.post("/api/v1/vantage/panel/run", json={},
                                headers={"X-CSRF-Token": csrf})
        self.assertEqual(resp.status_code, 403)
        resp = self.client.post("/api/v1/vantage/prompts", json={"prompt_text": "x"},
                                headers={"X-CSRF-Token": csrf})
        self.assertEqual(resp.status_code, 403)
        resp = self.client.post("/api/v1/vantage/seo/run", json={},
                                headers={"X-CSRF-Token": csrf})
        self.assertEqual(resp.status_code, 403)
        resp = self.client.post("/api/v1/vantage/seo/crawl/run", json={},
                                headers={"X-CSRF-Token": csrf})
        self.assertEqual(resp.status_code, 403)
        resp = self.client.post("/api/v1/vantage/seo/suggestions/run", json={},
                                headers={"X-CSRF-Token": csrf})
        self.assertEqual(resp.status_code, 403)
        resp = self.client.get(
            "/api/v1/vantage/seo/crawl/pages?task_id=t1&check=no_h1_tag",
            headers={"X-CSRF-Token": csrf})
        self.assertEqual(resp.status_code, 403)

    def test_seo_run_skips_brands_with_no_domain_and_report_reflects_it(self):
        from unittest.mock import patch

        import core.seo_report as seo_report_mod
        with patch.object(seo_report_mod, "_ranked_keywords", return_value=[
                {"keyword": "chase securities", "search_volume": 100, "rank": 3,
                 "url": "https://x/"}]), \
             patch.object(seo_report_mod, "_backlinks_summary", return_value={
                "backlinks": 10, "referring_domains": 5,
                "referring_main_domains": 4, "rank": 100}), \
             patch.object(seo_report_mod, "resolve_domains", return_value=[
                {"id": 1, "name": "Bank Alfalah", "is_focus": True, "domain": "example.com"},
                {"id": 2, "name": "A Competitor", "is_focus": False, "domain": "rival.com"}]):
            r = self._post("/api/v1/vantage/seo/run")
        self.assertEqual(r.status_code, 200)
        out = r.get_json()
        # C-118 (Hamza, 2026-09-12): the paid SEO run must never spend budget
        # on a competitor domain, even when resolve_domains() knows one --
        # 1 pull, not 2, proves the route filtered to the focus brand only.
        self.assertEqual(out["keywords_pulled"], 1)

        report = self.client.get("/api/v1/vantage/seo/report").get_json()
        self.assertEqual(len(report["brands"]), 1)
        self.assertEqual(report["brands"][0]["keywords"][0]["keyword"], "chase securities")
        self.assertEqual(report["brands"][0]["backlinks"]["referring_domains"], 5)

    def test_seo_crawl_run_skips_brands_with_no_domain(self):
        from unittest.mock import patch

        from jobs import worker

        import core.seo_crawl as seo_crawl_mod
        with patch.object(seo_crawl_mod, "_crawl_site", return_value=({
                "domain_info": {"crawl_status": {"pages_crawled": 10}},
                "page_metrics": {"onpage_score": 88.0, "checks": {"no_h1_tag": 1}}}, "t1")) as crawl, \
             patch.object(seo_crawl_mod, "_lighthouse", return_value={
                "categories": {"performance": {"score": 0.7}},
                "audits": {"largest-contentful-paint": {"numericValue": 3000}}}), \
             patch("core.seo_report.resolve_domains", return_value=[
                {"id": 1, "name": "Bank Alfalah", "is_focus": True, "domain": "example.com"},
                {"id": 2, "name": "A Competitor", "is_focus": False, "domain": "rival.com"}]):
            r = self._post("/api/v1/vantage/seo/crawl/run", {"max_pages": 10})
            self.assertEqual(r.status_code, 200)
            job_id = r.get_json()["job_id"]
            # C-118: crawl/run is now enqueued (P4.x async fix, 2026-09-12) --
            # a browser-held synchronous connection can't survive the up-to
            # ~6.5-minute worst case, so it runs on the background worker and
            # the frontend polls /jobs/{job_id} instead.
            for _ in range(4):
                if not worker.run_one(kinds=["seo_crawl"]):
                    break
            # the site crawl + Lighthouse run must never spend budget on a
            # competitor domain -- 1 call, not 2, proves the job filtered to
            # the focus brand only.
            crawl.assert_called_once()

        status = self.client.get(f"/api/v1/jobs/{job_id}").get_json()
        self.assertEqual(status["state"], "done")

        report = self.client.get("/api/v1/vantage/seo/crawl").get_json()
        self.assertEqual(len(report["brands"]), 1)
        b = report["brands"][0]
        self.assertEqual(b["onpage_score"], 88.0)
        self.assertEqual(b["cwv"]["lcp_ms"], 3000)
        self.assertEqual(b["task_id"], "t1")

    def test_seo_crawl_run_already_running_returns_the_same_job_id(self):
        import app as _app
        # nothing drains the worker queue here, so the first job stays
        # "queued" -- the second POST must reuse it, not spend budget twice.
        r1 = self._post("/api/v1/vantage/seo/crawl/run", {"max_pages": 10})
        r2 = self._post("/api/v1/vantage/seo/crawl/run", {"max_pages": 10})
        job_id = r1.get_json()["job_id"]
        try:
            self.assertEqual(job_id, r2.get_json()["job_id"])
            self.assertFalse(r1.get_json()["already"])
            self.assertTrue(r2.get_json()["already"])
        finally:
            # the module-level `_jobs` dict outlives the DB rollback -- drop
            # this test's job so it doesn't shadow a later test's crawl run
            # for the same workspace as a false "already running".
            with _app._lock:
                _app._jobs.pop(job_id, None)

    def test_panel_run_already_running_returns_the_same_job_id(self):
        import app as _app
        r1 = self._post("/api/v1/vantage/panel/run")
        r2 = self._post("/api/v1/vantage/panel/run")
        job_id = r1.get_json()["job_id"]
        try:
            self.assertEqual(job_id, r2.get_json()["job_id"])
            self.assertTrue(r2.get_json()["already"])
        finally:
            with _app._lock:
                _app._jobs.pop(job_id, None)

    def test_in_process_worker_drains_seo_crawl_jobs(self):
        import app as _app

        self.assertIn("seo_crawl", _app._IN_PROCESS_JOB_KINDS)

    def test_seo_crawl_pages_returns_the_real_page_list_for_a_check(self):
        import core.seo_crawl as seo_crawl_mod
        with patch.object(seo_crawl_mod, "pages_for_check", return_value=[
                {"url": "https://example.com/about", "status_code": 200},
                {"url": "https://example.com/contact", "status_code": 200}]) as mocked:
            resp = self.client.get(
                "/api/v1/vantage/seo/crawl/pages?task_id=t1&check=no_h1_tag",
                headers={"X-CSRF-Token": self.csrf})
        self.assertEqual(resp.status_code, 200)
        pages = resp.get_json()["pages"]
        self.assertEqual(len(pages), 2)
        self.assertEqual(pages[0]["url"], "https://example.com/about")
        mocked.assert_called_once()
        self.assertEqual(mocked.call_args[0][:2], ("t1", "no_h1_tag"))

    def test_seo_crawl_pages_error_surfaces_as_502_not_silent_empty_data(self):
        import core.seo_crawl as seo_crawl_mod
        with patch.object(seo_crawl_mod, "pages_for_check",
                          side_effect=RuntimeError("task expired")):
            resp = self.client.get(
                "/api/v1/vantage/seo/crawl/pages?task_id=stale&check=no_h1_tag",
                headers={"X-CSRF-Token": self.csrf})
        self.assertEqual(resp.status_code, 502)

    def test_seo_suggestions_run_400s_with_no_seo_data_on_file(self):
        resp = self._post("/api/v1/vantage/seo/suggestions/run")
        self.assertEqual(resp.status_code, 400)

    def test_seo_suggestions_run_then_read_the_latest(self):
        from unittest.mock import patch

        from jobs import worker

        import core.seo_crawl as seo_crawl_mod
        with patch.object(seo_crawl_mod, "_crawl_site", return_value=({
                "domain_info": {"crawl_status": {"pages_crawled": 10}},
                "page_metrics": {"onpage_score": 88.0, "checks": {}}}, "t1")), \
             patch.object(seo_crawl_mod, "_lighthouse", return_value={
                "categories": {"performance": {"score": 0.7}},
                "audits": {"largest-contentful-paint": {"numericValue": 3000}}}), \
             patch("core.seo_report.resolve_domains", return_value=[
                {"id": 1, "name": "Bank Alfalah", "is_focus": True, "domain": "example.com"}]):
            self._post("/api/v1/vantage/seo/crawl/run", {"max_pages": 10})
            for _ in range(4):
                if not worker.run_one(kinds=["seo_crawl"]):
                    break

        from integrations.llm import panel
        with patch.object(panel, "ask", return_value=(
                "openrouter", "anthropic/claude-haiku-4.5",
                "HIGH: The onpage score of 88 has room to improve.\n")):
            resp = self._post("/api/v1/vantage/seo/suggestions/run")
        self.assertEqual(resp.status_code, 200)
        out = resp.get_json()["suggestion"]
        self.assertIsNone(out["error"])
        self.assertEqual(out["suggestions"][0]["priority"], "HIGH")

        latest = self.client.get("/api/v1/vantage/seo/suggestions").get_json()["suggestion"]
        self.assertEqual(latest["id"], out["id"])

    def test_viewer_role_can_read_prompts_and_insights(self):
        self._login_viewer()
        self.assertEqual(self.client.get("/api/v1/vantage/prompts").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/vantage/insights").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/vantage/evidence").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/vantage/seo").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/vantage/seo/report").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/vantage/seo/crawl").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/vantage/seo/suggestions").status_code, 200)

    def test_seo_reads_real_dataforseo_serp_items_not_a_new_call(self):
        conn = self.app.db_operator()
        try:
            focus = conn.execute(
                "SELECT id FROM brand WHERE workspace_id=1 AND is_focus=1").fetchone()[0]
            conn.execute(
                """INSERT INTO item(workspace_id,surface,source,source_kind,external_id,
                   url,outlet,raw_json,collected_at,content_hash)
                   VALUES(1,'web','dataforseo_brand_serp','licensed','e1',
                   'https://www.bankalfalah.com/','www.bankalfalah.com',
                   '{"rank": 1}','now','e1')""")
            conn.commit()
        finally:
            conn.close()
        out = self.client.get("/api/v1/vantage/seo").get_json()
        focus_brand = next(b for b in out["brands"] if b["is_focus"])
        self.assertEqual(focus_brand["own_domains"][0]["domain"], "www.bankalfalah.com")


if __name__ == "__main__":
    unittest.main()
