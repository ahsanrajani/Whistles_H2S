"""Content-calendar intelligence: compliance rules, signal nudges, engagement
insights, closed-loop impact and the thin routes over them. Every LLM call is
mocked; every proportion is checked for its Wilson interval."""
import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from core import (content_calendar as cc, content_compliance as comp, content_impact,
                  content_insights, content_signals)
from integrations.llm import panel

from ._db import ApiTestCase, DbTestCase


def _ago(days, hour=9):
    d = datetime.now(timezone.utc) - timedelta(days=days)
    return d.replace(hour=hour, minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _keys(result):
    return {f["key"] for f in result["findings"]}


class ComplianceRuleTests(unittest.TestCase):
    def test_clean_post_is_clear(self):
        r = comp.check("Our Gulberg branch is open late this Friday.")
        self.assertEqual((r["score"], r["severity"], r["findings"]), (0, "clear", []))

    def test_guaranteed_return_claim_is_high_and_names_its_rules(self):
        r = comp.check("Guaranteed returns of 40% per month. Risk-free, invest today!")
        self.assertTrue({"guaranteed_return", "unrealistic_yield", "missing_disclaimer"} <= _keys(r))
        self.assertEqual(r["severity"], "high")
        self.assertEqual(r["score"], sum(f["weight"] for f in r["findings"]))
        self.assertTrue(all(f["matches"] and f["guidance"] for f in r["findings"]))

    def test_disclaimer_clears_the_missing_disclaimer_rule(self):
        bare = comp.check("Invest in our new mutual fund today.")
        covered = comp.check("Invest in our new mutual fund today. Returns are not "
                             "guaranteed. Subject to market risk. Terms apply.")
        self.assertIn("missing_disclaimer", _keys(bare))
        self.assertNotIn("missing_disclaimer", _keys(covered))

    def test_a_request_for_otp_is_flagged_but_a_warning_about_it_is_not(self):
        asked = comp.check("Reply with your OTP to verify your account.")
        warned = comp.check("We never ask you to share your OTP or PIN with anyone.")
        self.assertIn("sensitive_data_request", _keys(asked))
        self.assertNotIn("sensitive_data_request", _keys(warned))

    def test_outgoing_copy_is_held_to_the_scam_scanner_standard(self):
        r = comp.check("DM us on WhatsApp 0300 1234567 for your refund.")
        self.assertTrue({"scam:whatsapp", "scam:phone"} <= _keys(r))

    def test_awareness_copy_may_name_whatsapp_but_never_publish_a_number(self):
        named = comp.check("Beware: fake accounts will ask you to move to WhatsApp.")
        number = comp.check("Beware of fakes. Our only helpline is +92 300 1234567.")
        self.assertTrue(named["awareness_context"])
        self.assertNotIn("scam:whatsapp", _keys(named))
        self.assertIn("scam:phone", _keys(number))

    def test_every_nudge_template_passes_its_own_compliance_check(self):
        drafts = [d for _t, d in content_signals._SCAM_ANGLES.values()]
        drafts.append("We know some customers are facing problems with app crash, outage. "
                      "Our team is working on it. For help, use our verified app, website "
                      "or helpline only. We will never ask for your OTP or PIN.")
        for d in drafts:
            self.assertEqual(comp.check(d)["severity"], "clear", d)

    def test_policy_lists_rules_and_bands(self):
        pol = comp.policy()
        self.assertEqual([b["key"] for b in pol["bands"]], ["high", "review", "note", "clear"])
        self.assertIn("guaranteed_return", {r["key"] for r in pol["rules"]})
        self.assertIn("scam:short_link", {r["key"] for r in pol["rules"]})


class RewriteTests(unittest.TestCase):
    BAD = "Guaranteed returns on our new fund, invest now!"

    def test_offline_rewrite_is_deterministic_and_safer(self):
        before = comp.check(self.BAD)
        out = comp.rewrite(self.BAD, before["findings"], keys={})
        self.assertTrue(out["mock"])
        self.assertLess(comp.check(out["text"])["score"], before["score"])
        self.assertIn(comp.SAFE_DISCLAIMER, out["text"])

    def test_with_a_key_the_model_text_is_returned_unscored(self):
        findings = comp.check(self.BAD)["findings"]
        with patch.object(panel, "ask", return_value=("google", "gemini", "Invest wisely. Risk applies.\n")):
            out = comp.rewrite(self.BAD, findings, keys={"GOOGLE_API_KEY": "k"})
        self.assertEqual(out, {"text": "Invest wisely. Risk applies.", "mock": False})

    def test_a_failed_model_call_falls_back_to_the_offline_rewrite(self):
        findings = comp.check(self.BAD)["findings"]
        with patch.object(panel, "ask", side_effect=RuntimeError("quota")):
            out = comp.rewrite(self.BAD, findings, keys={"GOOGLE_API_KEY": "k"})
        self.assertTrue(out["mock"])
        self.assertEqual(out["error"], "quota")


class JudgeTests(unittest.TestCase):
    def test_too_early_beats_everything(self):
        self.assertEqual(content_impact.judge(50, 100, 1, 100, 1)[0], "too_early")

    def test_thin_windows_are_not_judged(self):
        self.assertEqual(content_impact.judge(5, 9, 0, 40, 7)[0], "not_enough_data")

    def test_overlapping_intervals_are_no_durable_change(self):
        self.assertEqual(content_impact.judge(6, 20, 4, 20, 7)[0], "no_durable_change")

    def test_separated_intervals_report_the_direction(self):
        self.assertEqual(content_impact.judge(60, 100, 5, 100, 7)[0], "improved")
        self.assertEqual(content_impact.judge(5, 100, 60, 100, 7)[0], "worse")


class EngagementMathTests(unittest.TestCase):
    def test_a_platform_with_no_metrics_is_none_not_zero(self):
        self.assertIsNone(content_insights._engagement(None))
        self.assertIsNone(content_insights._engagement({"views": 900}))

    def test_engagement_sums_only_interaction_counts(self):
        self.assertEqual(content_insights._engagement(
            {"likes": 10, "comments": 4, "shares": None, "views": 9999}), 14)


class _Corpus(DbTestCase):
    """Workspace 1 with a focus brand and helpers to lay down items."""

    def setUp(self):
        super().setUp()
        self.db.execute("INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.execute("INSERT INTO brand(id,workspace_id,name,is_focus) VALUES (1,1,'Focus Bank',1)")
        self._n = 0

    def _item(self, *, source, body, raw, when, surface="facebook", kind="licensed",
              title=None, brand=True, outlet="Focus Bank"):
        self._n += 1
        n = self._n
        self.db.execute(
            """INSERT INTO item(id,workspace_id,surface,source,source_kind,external_id,url,outlet,
                                author,published_at,title,body,raw_json,collected_at,content_hash)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (n, 1, surface, source, kind, f"ext-{n}", f"https://x/{n}", outlet, f"user{n % 7}",
             when, title, body, json.dumps(raw), "now", f"h{n}"))
        if brand:
            self.db.execute("INSERT INTO mention(id,item_id,brand_id,rule) VALUES (?,?,1,'t')", (n, n))
        self.db.commit()
        return f"ext-{n}"

    def _comment(self, body, days, parent=None, source="meta_facebook"):
        raw = {"kind": "comment"}
        if parent:
            raw["parent_id"] = parent
        return self._item(source=source, body=body, raw=raw, when=_ago(days))

    def _post(self, body, days, metrics, hour=9, source="meta_facebook"):
        raw = {"kind": "post"}
        if metrics is not None:
            raw["metrics"] = metrics
        return self._item(source=source, body=body, raw=raw, when=_ago(days, hour))


class SignalTests(_Corpus):
    def _scam_wave(self, flagged, clean=4):
        for i in range(flagged):
            self._comment(f"Contact our agent on WhatsApp for your refund {i}", 2)
        for i in range(clean):
            self._comment(f"Lovely branch staff {i}", 3)

    def test_scam_nudge_carries_its_evidence_and_a_clean_draft(self):
        self._scam_wave(6)
        out = content_signals.nudges(self.db, 1)
        nudge = next(n for n in out["nudges"] if n["kind"] == "scam")
        ev = nudge["evidence"]
        self.assertEqual((ev["flagged"], ev["scanned"]), (6, 10))
        self.assertLess(ev["ci_low"], ev["rate"])
        self.assertGreater(ev["ci_high"], ev["rate"])
        self.assertEqual(comp.check(nudge["draft"])["severity"], "clear")
        self.assertTrue(nudge["why"].startswith("6 of 10 comments"))

    def test_a_couple_of_flags_is_not_a_nudge(self):
        self._scam_wave(2)
        self.assertEqual([n for n in content_signals.nudges(self.db, 1)["nudges"]
                          if n["kind"] == "scam"], [])

    def test_a_recent_consumer_notice_becomes_a_nudge(self):
        self._item(source="regulatory_watch", surface="regulatory", kind="public", brand=False,
                   title="SBP issues consumer protection circular on phishing",
                   body="Banks must warn customers about phishing.",
                   raw={"regulator": "SBP"}, when=_ago(5), outlet="SBP")
        nudge = next(n for n in content_signals.nudges(self.db, 1)["nudges"]
                     if n["kind"] == "regulatory")
        self.assertIn("SBP", nudge["title"])
        self.assertEqual(nudge["severity"], "watch")
        self.assertTrue(set(nudge["evidence"]["topics"]) & {"consumer", "cyber"})

    def test_a_stock_exchange_notice_about_another_company_is_not(self):
        self._item(source="regulatory_watch", surface="regulatory", kind="public", brand=False,
                   title="PSX places a motors company in the non-compliant segment over unpaid penalty",
                   body="", raw={"regulator": "PSX"}, when=_ago(2), outlet="PSX")
        self.assertEqual([n for n in content_signals.nudges(self.db, 1)["nudges"]
                          if n["kind"] == "regulatory"], [])

    def test_an_old_notice_is_not(self):
        self._item(source="regulatory_watch", surface="regulatory", kind="public", brand=False,
                   title="SBP issues consumer protection circular", body="",
                   raw={"regulator": "SBP"}, when=_ago(90), outlet="SBP")
        self.assertEqual([n for n in content_signals.nudges(self.db, 1)["nudges"]
                          if n["kind"] == "regulatory"], [])

    def test_a_focus_brand_incident_becomes_a_high_nudge(self):
        for offset in range(6, 22):
            self._item(source="x_recent", surface="x", body="normal chatter", raw={}, when=_ago(offset, 12))
        for n in range(8):
            body = "the app crash outage is back" if n < 4 else "just a normal comment"
            self._item(source="x_recent", surface="x", body=body, raw={}, when=_ago(2, 12))
        nudge = next(n for n in content_signals.nudges(self.db, 1)["nudges"]
                     if n["kind"] == "incident")
        self.assertEqual(nudge["severity"], "high")
        self.assertIn("outage", nudge["evidence"]["keywords"])

    def test_creating_a_draft_records_its_origin_and_verdict(self):
        self._scam_wave(6)
        key = next(n["key"] for n in content_signals.nudges(self.db, 1)["nudges"]
                   if n["kind"] == "scam")
        out = content_signals.create_draft(self.db, 1, None, key, keys={})
        self.db.commit()
        got = cc.get(self.db.session, 1, out["id"])
        self.assertEqual(got["item"]["state"], "draft")
        self.assertTrue(out["mock"])
        self.assertEqual(out["compliance"]["severity"], "clear")
        origin = [h for h in got["history"] if h["kind"] == "signal_origin"]
        self.assertEqual(origin[0]["detail"], {"signal": key, "signal_kind": "scam"})

    def test_an_expired_signal_cannot_be_drafted(self):
        with self.assertRaises(content_signals.SignalError):
            content_signals.create_draft(self.db, 1, None, "scam:whatsapp", keys={})


class InsightTests(_Corpus):
    def test_too_little_history_says_so_instead_of_guessing(self):
        self._post("New savings plan", 3, {"likes": 10})
        out = content_insights.performance(self.db, 1)
        self.assertIsNone(out["baseline"]["median_engagement"])
        self.assertIn("at least 5 posts", out["baseline"]["note"])
        self.assertIsNone(out["posts"][0]["band"])
        self.assertFalse(out["timing"]["available"])
        self.assertEqual(out["digest"][0]["kind"], "empty")

    def test_a_popular_post_that_scammers_are_working_is_flagged_with_intervals(self):
        for i in range(7):
            self._post(f"Branch update {i}", 20 + i, {"likes": 10, "comments": 0})
        hot = self._post("Profit rate update on savings accounts", 2, {"likes": 90, "comments": 10})
        for i in range(3):
            self._comment(f"WhatsApp me on 03001234567 for a refund {i}", 1, parent=hot)
        for i in range(3):
            self._comment(f"Thanks for the update {i}", 1, parent=hot)
        out = content_insights.performance(self.db, 1)
        post = next(p for p in out["posts"] if p["text"].startswith("Profit rate"))
        self.assertEqual(out["baseline"]["median_engagement"], 10)
        self.assertEqual((post["engagement"], post["band"], post["vs_baseline"]), (96, "above", 9.6))   # comments = the 6 really collected
        self.assertTrue(post["scammers_working_it"])
        flagged = post["comments"]["scam_flagged"]
        self.assertEqual((flagged["k"], flagged["n"]), (3, 6))
        self.assertLess(flagged["ci_low"], flagged["rate"])
        kinds = [d["kind"] for d in out["digest"]]
        self.assertIn("risk", kinds)
        self.assertIn("win", kinds)

    def test_timing_needs_enough_dated_posts_and_reports_the_best_slot(self):
        for i in range(12):
            eve = i % 3 == 0
            self._post(f"Update {i}", i + 1, {"likes": 40 if eve else 8}, hour=14 if eve else 6)
        out = content_insights.performance(self.db, 1)
        timing = out["timing"]
        self.assertTrue(timing["available"])
        self.assertEqual(timing["best_daypart"]["label"], "evening")
        self.assertEqual(len(timing["by_weekday"]), 7)

    def test_a_platform_without_metrics_has_no_engagement_not_zero(self):
        self._post("Video upload", 2, None)
        out = content_insights.performance(self.db, 1)
        self.assertIsNone(out["posts"][0]["engagement"])


class ImpactTests(_Corpus):
    def _published(self, days_ago, origin=True):
        cid = cc.create(self.db.session, 1, None, title="Warn customers", body="Beware of scams",
                        channel="meta")
        if origin:
            cc.record_origin(self.db.session, cid, None, {"signal": "scam:whatsapp", "signal_kind": "scam"})
        for action in ("submit", "approve", "schedule"):
            cc.transition(self.db.session, 1, cid, action, None,
                          at=datetime.now(timezone.utc) if action == "schedule" else None)
        cc.transition(self.db.session, 1, cid, "publish", None,
                      at=datetime.now(timezone.utc) - timedelta(days=days_ago))
        self.db.commit()
        return cid

    def _wave(self, days, flagged, clean):
        for i in range(flagged):
            self._comment(f"Contact our agent on WhatsApp refund {i}", days)
        for i in range(clean):
            self._comment(f"Nice service {i}", days)

    def test_a_scam_post_followed_by_fewer_scam_comments_is_improved(self):
        self._published(days_ago=10)
        self._wave(14, flagged=12, clean=8)        # before: 12 of 20
        self._wave(6, flagged=1, clean=19)         # after: 1 of 20
        out = content_impact.impact(self.db, 1)
        item = out["items"][0]
        self.assertEqual(item["verdict"], "improved")
        self.assertEqual(item["metric"], "scam_flag_rate")
        self.assertEqual((item["before"]["k"], item["before"]["n"]), (12, 20))
        self.assertEqual((item["after"]["k"], item["after"]["n"]), (1, 20))
        self.assertLess(item["before"]["ci_low"], item["before"]["rate"])
        self.assertEqual(out["summary"]["improved"], 1)
        self.assertIn("Association, not proof", out["note"])

    def test_thin_comment_volume_is_not_judged(self):
        self._published(days_ago=10)
        self._wave(14, flagged=2, clean=2)
        self._wave(6, flagged=0, clean=3)
        item = content_impact.impact(self.db, 1)["items"][0]
        self.assertEqual(item["verdict"], "not_enough_data")

    def test_a_post_from_yesterday_is_too_early(self):
        self._published(days_ago=1)
        self.assertEqual(content_impact.impact(self.db, 1)["items"][0]["verdict"], "too_early")

    def test_a_post_without_an_origin_is_measured_on_complaint_words(self):
        self._published(days_ago=10, origin=False)
        self.assertEqual(content_impact.impact(self.db, 1)["items"][0]["metric"], "complaint_rate")


class RiskMapTests(_Corpus):
    def test_only_risky_unpublished_drafts_are_badged(self):
        bad = cc.create(self.db.session, 1, None, title="Fund", body="Guaranteed returns, risk-free!")
        cc.create(self.db.session, 1, None, title="Hours", body="Open late on Friday.")
        self.db.commit()
        today = datetime.now(timezone.utc).date()
        out = comp.risk_map(self.db.session, 1, today - timedelta(days=30), today + timedelta(days=30))
        self.assertEqual(list(out["risk"]), [bad])
        self.assertEqual(out["risk"][bad]["severity"], "high")


class ContentAiApiTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        token = self.client.get("/api/v1/csrf").get_json()["token"]
        self.client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"},
                         headers={"X-CSRF-Token": token})
        with self.client.session_transaction() as s:
            self.csrf = s.get("csrf_token", "")

    def _h(self):
        return {"X-CSRF-Token": self.csrf}

    def test_compliance_route_matches_the_service(self):
        r = self.client.post("/api/v1/content/ai/compliance", headers=self._h(),
                             json={"text": "Guaranteed returns, risk-free!"})
        self.assertEqual(r.status_code, 200)
        out = r.get_json()
        self.assertEqual(out["severity"], comp.check("Guaranteed returns, risk-free!")["severity"])
        self.assertIsNone(out["rewrite"])

    def test_rewrite_is_offered_only_on_request(self):
        r = self.client.post("/api/v1/content/ai/compliance", headers=self._h(),
                             json={"text": "Guaranteed returns, risk-free!", "rewrite": True})
        self.assertIn("text", r.get_json()["rewrite"])

    def test_read_routes_answer_on_an_empty_workspace(self):
        for path in ("signals", "insights", "impact", "risk"):
            r = self.client.get(f"/api/v1/content/ai/{path}")
            self.assertEqual(r.status_code, 200, path)

    def test_drafting_from_an_unknown_signal_is_a_404(self):
        r = self.client.post("/api/v1/content/ai/signals/draft", headers=self._h(),
                             json={"key": "scam:nothing"})
        self.assertEqual(r.status_code, 404)

    def test_the_ai_routes_do_not_shadow_the_item_routes(self):
        cid = self.client.post("/api/v1/content", headers=self._h(),
                               json={"title": "t", "body": "b", "channel": "meta"}).get_json()["id"]
        self.assertEqual(self.client.get(f"/api/v1/content/{cid}").status_code, 200)


if __name__ == "__main__":
    unittest.main()
