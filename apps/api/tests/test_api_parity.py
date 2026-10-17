import os
import unittest
from unittest import mock

import app
from core import (alerts, branch_geo, branch_perf, entity, impersonation, incidents, insights,
                  product_lines, regulatory, scam, switch_intent, triage)

from ._db import ApiTestCase, asgi_client


class ApiParityTests(ApiTestCase):
    """The migration API must expose backend analytics without recalculation."""

    def setUp(self):
        super().setUp()
        csrf = self.client.get("/api/v1/csrf").get_json()["token"]
        response = self.client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "admin123"},
            headers={"X-CSRF-Token": csrf},
        )
        self.assertEqual(response.status_code, 200)
        # The session CSRF token is rotated on login; capture the live one.
        with self.client.session_transaction() as active_session:
            self.csrf = active_session["csrf_token"]

    def test_overview_analytics_match_direct_calls(self):
        payload = self.client.get("/api/v1/overview?period=30d").get_json()
        connection = self.app.db_operator()
        workspace_id = connection.execute(
            "SELECT id FROM workspace ORDER BY id LIMIT 1").fetchone()[0]
        sov = insights.share_of_voice(connection, workspace_id)
        sentiment = insights.sentiment_breakdown(connection, workspace_id)
        reviews = insights.app_reviews(connection, workspace_id)
        deltas = insights.deltas(connection, workspace_id, 30)
        self.assertEqual(payload["sov"], sov)
        self.assertEqual(payload["deltas"], deltas)
        self.assertEqual(payload["mix"], insights.mention_mix(connection, workspace_id, None, 30))
        self.assertEqual(
            payload["kpis"],
            insights.kpis(connection, workspace_id, sov, sentiment, None, 30,
                           insights.PERIOD_LABELS["30d"], reviews, deltas),
        )
        connection.close()

    def test_mentions_rows_and_total_match_evidence(self):
        payload = self.client.get("/api/v1/mentions?sort=new&since=all").get_json()
        connection = self.app.db_operator()
        workspace_id = connection.execute(
            "SELECT id FROM workspace ORDER BY id LIMIT 1").fetchone()[0]
        rows, total = insights.evidence(
            connection, workspace_id, limit=150, sort="new", include_hidden=True)
        self.assertEqual(payload["total"], total)
        self.assertEqual([row["id"] for row in payload["rows"]], [row[0] for row in rows])
        connection.close()

    def test_phase_two_viewer_payloads_match_direct_analytics(self):
        connection = self.app.db_operator()
        workspace_id = connection.execute(
            "SELECT id FROM workspace ORDER BY id LIMIT 1").fetchone()[0]
        sov = insights.share_of_voice(connection, workspace_id)
        focus = next((brand for brand in sov if brand["focus"]), None)

        sentiment = self.client.get("/api/v1/sentiment?period=90d").get_json()
        breakdown = insights.sentiment_breakdown(connection, workspace_id)
        self.assertEqual(sentiment["breakdown"], breakdown)
        self.assertEqual(sentiment["gauge"], insights.gauge(breakdown))
        self.assertEqual(sentiment["trend"], insights.sentiment_trend(connection, workspace_id))

        competitors = self.client.get("/api/v1/competitors?period=90d").get_json()
        gaps, reached, total = insights.outlet_gap(
            connection, workspace_id, focus["name"] if focus else "")
        self.assertEqual(competitors["sov"], sov)
        self.assertEqual(competitors["gaps"], gaps)
        self.assertEqual(competitors["reached"], reached)
        self.assertEqual(competitors["total_outlets"], total)
        self.assertEqual(competitors["trend"],
                         insights.press_volume(connection, workspace_id, days=90))

        reviews = self.client.get("/api/v1/reviews?period=90d").get_json()
        from core.review_store import review_context
        context = review_context(connection.session, workspace_id)
        self.assertEqual(reviews["store_stats"], context["store_stats"])
        self.assertEqual(reviews["focus_brand_id"], context["focus_brand_id"])
        self.assertEqual(reviews["reviews"],
                         insights.app_reviews(connection, workspace_id, recent_limit=50))
        self.assertEqual(reviews["trend"], insights.review_trend(connection, workspace_id))
        self.assertEqual(reviews["timeline"],
                         insights.rating_timeline(connection, workspace_id, days=90))

        themes = self.client.get("/api/v1/themes").get_json()
        expected_themes = (insights.themes(connection, workspace_id, focus["id"], limit=48)
                           if focus else [])
        self.assertEqual(themes["cloud"], expected_themes)
        self.assertEqual(themes["table"], expected_themes)
        connection.close()

    def test_scam_signals_match_direct_scan(self):
        payload = self.client.get("/api/v1/scam?period=all").get_json()
        connection = self.app.db_operator()
        workspace_id = connection.execute(
            "SELECT id FROM workspace ORDER BY id LIMIT 1").fetchone()[0]
        expected = scam.scan(connection, workspace_id, surface=None, days=None)
        connection.close()
        for key, value in expected.items():
            self.assertEqual(payload[key], value)
        self.assertEqual(payload["period"], "all")
        self.assertEqual(
            [rule["key"] for rule in payload["policy"]["signals"]],
            [key for key, _label, _weight, _pattern in scam.SIGNALS],
        )

    def test_complaint_triage_matches_direct_scan(self):
        payload = self.client.get("/api/v1/triage?period=all").get_json()
        connection = self.app.db_operator()
        workspace_id = connection.execute(
            "SELECT id FROM workspace ORDER BY id LIMIT 1").fetchone()[0]
        expected = triage.scan(connection, workspace_id, days=None)
        connection.close()
        for key, value in expected.items():
            self.assertEqual(payload[key], value)
        self.assertEqual(payload["period"], "all")

    def test_switch_intent_matches_direct_scan(self):
        payload = self.client.get("/api/v1/switch-intent?period=all").get_json()
        connection = self.app.db_operator()
        workspace_id = connection.execute(
            "SELECT id FROM workspace ORDER BY id LIMIT 1").fetchone()[0]
        expected = switch_intent.scan(connection, workspace_id, days=None)
        connection.close()
        for key, value in expected.items():
            self.assertEqual(payload[key], value)
        self.assertEqual(payload["period"], "all")

    @mock.patch.dict(os.environ, {"BRAND_DOMAINS": ""}, clear=False)
    @mock.patch("core.impersonation._ct_query", lambda stem: set())
    @mock.patch("core.impersonation._resolve", lambda host: "nxdomain")
    def test_impersonation_watch_is_admin_only_and_uses_stubbed_probes(self):
        viewer = asgi_client()
        csrf = viewer.get("/api/v1/csrf").get_json()["token"]
        viewer.post("/api/v1/auth/login",
                    json={"username": "bank", "password": "viewer123"},
                    headers={"X-CSRF-Token": csrf})
        self.assertEqual(viewer.get("/api/v1/impersonation").status_code, 403)

        connection = self.app.db_operator()
        try:
            connection.execute(
                "UPDATE api_key SET value='bankalfalah.com', status='present' "
                "WHERE workspace_id=0 AND env_var='BRAND_DOMAINS'")
            connection.commit()
        finally:
            connection.close()

        payload = self.client.get("/api/v1/impersonation").get_json()
        expected = impersonation.scan(["bankalfalah.com"])
        self.assertEqual(payload["official"], ["bankalfalah.com"])
        self.assertEqual(payload["policy"], expected["policy"])
        self.assertEqual([row["domain"] for row in payload["candidates"]],
                         [row["domain"] for row in expected["candidates"]])
        self.assertEqual(payload["ct_status"], "ok")

    def test_alerts_match_direct_evaluate_and_dispatch_is_admin_only(self):
        payload = self.client.get("/api/v1/alerts").get_json()
        connection = self.app.db_operator()
        workspace_id = connection.execute(
            "SELECT id FROM workspace ORDER BY id LIMIT 1").fetchone()[0]
        expected = alerts.evaluate(connection, workspace_id, None)
        connection.close()
        self.assertEqual(payload, expected)

        viewer = asgi_client()
        csrf = viewer.get("/api/v1/csrf").get_json()["token"]
        viewer.post("/api/v1/auth/login",
                    json={"username": "bank", "password": "viewer123"},
                    headers={"X-CSRF-Token": csrf})
        self.assertEqual(viewer.get("/api/v1/alerts").status_code, 200)
        with viewer.session_transaction() as viewer_session:
            viewer_csrf = viewer_session["csrf_token"]
        self.assertEqual(
            viewer.post("/api/v1/alerts/dispatch",
                        headers={"X-CSRF-Token": viewer_csrf}).status_code, 403)
        # admin dispatch with no webhook configured sends nowhere, cleanly
        result = self.client.post("/api/v1/alerts/dispatch",
                                  headers={"X-CSRF-Token": self.csrf}).get_json()
        self.assertEqual(result["sent"], [])

    def test_regulatory_feed_matches_direct_summary(self):
        payload = self.client.get("/api/v1/regulatory").get_json()
        connection = self.app.db_operator()
        workspace_id = connection.execute(
            "SELECT id FROM workspace ORDER BY id LIMIT 1").fetchone()[0]
        expected = regulatory.summarize(connection, workspace_id)
        connection.close()
        self.assertEqual(payload, expected)

    def test_product_lines_match_direct_scan(self):
        payload = self.client.get("/api/v1/product-lines?period=all").get_json()
        connection = self.app.db_operator()
        workspace_id = connection.execute(
            "SELECT id FROM workspace ORDER BY id LIMIT 1").fetchone()[0]
        expected = product_lines.scan(connection, workspace_id, days=None)
        connection.close()
        for key, value in expected.items():
            self.assertEqual(payload[key], value)
        self.assertEqual(payload["period"], "all")

    def test_branches_match_direct_scan(self):
        payload = self.client.get("/api/v1/branches?period=all").get_json()
        connection = self.app.db_operator()
        workspace_id = connection.execute(
            "SELECT id FROM workspace ORDER BY id LIMIT 1").fetchone()[0]
        expected = branch_perf.scan(connection, workspace_id, days=None)
        connection.close()
        for key, value in expected.items():
            self.assertEqual(payload[key], value)
        self.assertEqual(payload["period"], "all")

    def test_branch_map_matches_direct_merge(self):
        payload = self.client.get("/api/v1/branches/map").get_json()
        connection = self.app.db_operator()
        workspace_id = connection.execute(
            "SELECT id FROM workspace ORDER BY id LIMIT 1").fetchone()[0]
        expected = branch_geo.with_performance(connection, workspace_id)
        connection.close()
        self.assertEqual(payload["branches"], expected)
        self.assertEqual(payload["summary"]["total"], len(expected))

    def test_competitor_incidents_match_direct_scan(self):
        payload = self.client.get("/api/v1/incidents").get_json()
        connection = self.app.db_operator()
        workspace_id = connection.execute(
            "SELECT id FROM workspace ORDER BY id LIMIT 1").fetchone()[0]
        expected = incidents.scan(connection, workspace_id)
        connection.close()
        self.assertEqual(payload["brands"], expected["brands"])
        self.assertEqual(payload["params"], expected["params"])
        self.assertEqual(payload["lexicon"], expected["lexicon"])

    def test_admin_config_reads_match_backend(self):
        connection = self.app.db_operator()
        workspace_id = connection.execute(
            "SELECT id FROM workspace ORDER BY id LIMIT 1").fetchone()[0]
        scenario = connection.execute(
            "SELECT volume_scenario FROM workspace WHERE id=?", (workspace_id,)).fetchone()[0]
        measured, model = insights.cost(connection, workspace_id, scenario)

        cost = self.client.get("/api/v1/admin/cost").get_json()
        self.assertEqual(cost["scenario"], scenario)
        self.assertEqual(cost["measured"], measured)
        self.assertEqual(cost["model"], model)

        brands = self.client.get("/api/v1/admin/brands").get_json()
        focus = next(brand for brand in brands["brands"] if brand["is_focus"])
        self.assertEqual(focus["name"], "Bank Alfalah")

        keys = self.client.get("/api/v1/admin/keys").get_json()
        self.assertEqual([row["env_var"] for row in keys["workspace"]],
                         [var for var, _label in app.sources.KEYS])
        connection.close()

    def test_brand_preview_uses_the_shared_matcher(self):
        payload = {"name": "Preview", "safe_patterns": ["\\bbank\\b"],
                   "gated_patterns": {}, "context_patterns": [], "exclude_patterns": []}
        result = self.client.post("/api/v1/admin/brands/preview", json=payload,
                                  headers={"X-CSRF-Token": self.csrf}).get_json()
        self.assertEqual(result["errors"], [])

        connection = self.app.db_operator()
        workspace_id = connection.execute(
            "SELECT id FROM workspace ORDER BY id LIMIT 1").fetchone()[0]
        brand = {"id": 0, "name": "Preview", "safe": ["\\bbank\\b"],
                 "gated": {}, "context": [], "exclude": []}
        rows = connection.execute(
            """SELECT title,body FROM item WHERE workspace_id=?
               ORDER BY published_at DESC, id DESC LIMIT 4000""", (workspace_id,)).fetchall()
        expected = sum(1 for title, body in rows
                       if entity.classify(" ".join(filter(None, [title, body])), [brand]))
        self.assertEqual(result["match_count"], expected)
        self.assertEqual(result["sample_size"], len(rows))

        bad = self.client.post("/api/v1/admin/brands/preview",
                               json={"safe_patterns": ["(unterminated"]},
                               headers={"X-CSRF-Token": self.csrf}).get_json()
        self.assertTrue(bad["errors"])
        connection.close()

    def test_review_queue_matches_backend(self):
        connection = self.app.db_operator()
        workspace_id = connection.execute(
            "SELECT id FROM workspace ORDER BY id LIMIT 1").fetchone()[0]
        payload = self.client.get("/api/v1/review").get_json()
        self.assertEqual(payload["calibration"],
                         insights.calibration_status(connection, workspace_id))
        expected = insights.review_batch(connection, workspace_id)
        self.assertEqual([row["id"] for row in payload["batch"]],
                         [row[-1] for row in expected])
        connection.close()

    def test_onboarding_wizard_round_trips(self):
        state = self.client.get("/api/v1/onboarding/state").get_json()
        self.assertEqual(state["steps"][0], "Workspace")

        created = self.client.patch("/api/v1/onboarding/1",
                                    json={"name": "Parity WS", "market": "PK",
                                          "volume_scenario": "mid"},
                                    headers={"X-CSRF-Token": self.csrf}).get_json()
        self.assertEqual(created["step"], 2)
        ws_id = created["ws_id"]

        self.client.patch("/api/v1/onboarding/2",
                          json={"focus": "Parity Bank", "competitors": ["Rival Bank"]},
                          headers={"X-CSRF-Token": self.csrf})
        connection = self.app.db_operator()
        names = [row[0] for row in connection.execute(
            "SELECT name FROM brand WHERE workspace_id=? ORDER BY is_focus DESC", (ws_id,))]
        self.assertEqual(names, ["Parity Bank", "Rival Bank"])

        self.client.patch("/api/v1/onboarding/5", json={"run_now": False},
                          headers={"X-CSRF-Token": self.csrf})
        step = connection.execute(
            "SELECT onboarding_step FROM workspace WHERE id=?", (ws_id,)).fetchone()[0]
        self.assertEqual(step, 0)
        connection.close()

    def test_admin_gating_does_not_leak_onto_viewer_routes(self):
        csrf = self.client.get("/api/v1/csrf").get_json()["token"]
        self.client.post("/api/v1/auth/login",
                         json={"username": "bank", "password": "viewer123"},
                         headers={"X-CSRF-Token": csrf})
        # The viewer app-reviews page must stay open to viewers...
        self.assertEqual(self.client.get("/api/v1/reviews").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/sentiment").status_code, 200)
        # ...while the admin-only calibration queue and admin config are blocked.
        self.assertEqual(self.client.get("/api/v1/review").status_code, 403)
        self.assertEqual(self.client.get("/api/v1/admin/cost").status_code, 403)
        self.assertEqual(self.client.get("/api/v1/onboarding/state").status_code, 403)

    def test_api_mutations_require_csrf_and_admin(self):
        self.assertEqual(self.client.post("/api/v1/auth/logout").status_code, 400)
        with self.client.session_transaction() as active_session:
            token = active_session["csrf_token"]
        self.assertEqual(
            self.client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": token}).status_code,
            200,
        )


if __name__ == "__main__":
    unittest.main()
