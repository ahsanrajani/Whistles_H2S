"""P3.7 — AI reply assistance.

Exit criterion: a suggestion comes back fast (mock mode is instant) and nothing
is sent — the agent must accept it explicitly via the normal reply endpoint.
"""
import unittest
from unittest.mock import patch

from core import ai_assist

from ._db import ApiTestCase, DbTestCase


class SuggestUnitTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.commit()
        self.s = self.db.session
        from core import cases
        self.cid = cases.ingest_message(self.s, 1, platform="x", handle="@c",
                                        body="My card was declined at an ATM")["case_id"]
        self.db.execute(
            "INSERT INTO kb_article(workspace_id,title,body,tags) "
            "VALUES (1,'ATM decline','If a card is declined at an ATM, check the "
            "daily limit and any fraud lock.','atm card decline')")
        self.db.commit()

    def test_mock_reply_suggestion_cites_the_kb(self):
        out = ai_assist.suggest(self.s, 1, self.cid, kind="reply", keys={})
        self.assertTrue(out["mock"])
        self.assertIn("ATM decline", " ".join(str(x) for x in [out["suggestion"]]) or "")
        self.assertTrue(out["sources"])          # kb article id(s)

    def test_polish_kinds(self):
        for kind in ("grammar", "tone", "brand_voice"):
            out = ai_assist.suggest(self.s, 1, self.cid, kind=kind,
                                    draft="pls chek ur limit", keys={})
            self.assertTrue(out["suggestion"])
            self.assertEqual(out["sources"], [])

    def test_unknown_kind_raises(self):
        with self.assertRaises(ValueError):
            ai_assist.suggest(self.s, 1, self.cid, kind="haiku", keys={})

    # --- context-aware greeting (Hamza, live screenshot C-117: "says thank
    # you for messaging xxx again and again, should do so for the first
    # message") ------------------------------------------------------------
    def test_mock_reply_greets_on_a_genuine_first_contact(self):
        # this fixture's workspace has no focus brand configured, so mock
        # mode's brand-less greeting branch is the one that fires -- still
        # exercises the same first_contact=True path.
        out = ai_assist.suggest(self.s, 1, self.cid, kind="reply", keys={})
        self.assertIn("Thanks for reaching out", out["suggestion"])

    def test_mock_reply_does_not_re_greet_once_the_business_has_replied(self):
        from core import cases
        cases.post_reply(self.s, self.cid, 1, body="We're looking into it.",
                         channel="x", actor=1)
        self.db.commit()
        cases.ingest_message(self.s, 1, platform="x", handle="@c",
                             body="Any update yet?")
        self.db.commit()
        out = ai_assist.suggest(self.s, 1, self.cid, kind="reply", keys={}, force=True)
        self.assertNotIn("Thank you for contacting", out["suggestion"])
        self.assertNotIn("Thanks for reaching out", out["suggestion"])

    def test_real_mode_system_prompt_forbids_re_greeting_after_a_reply(self):
        from core import cases
        cases.post_reply(self.s, self.cid, 1, body="We're looking into it.",
                         channel="x", actor=1)
        self.db.commit()
        cases.ingest_message(self.s, 1, platform="x", handle="@c",
                             body="Any update yet?")
        self.db.commit()
        seen = {}

        def fake(system, prompt, *, keys):
            seen["system"] = system
            return "A direct, specific reply."

        ai_assist.suggest(self.s, 1, self.cid, kind="reply",
                          keys={"GOOGLE_API_KEY": "k"}, call_model=fake, force=True)
        self.assertIn("do NOT greet", seen["system"])

    def test_real_mode_uses_the_injected_model(self):
        seen = {}

        def fake(system, prompt, *, keys):
            seen["system"] = system
            seen["prompt"] = prompt
            return "  A grounded on-brand reply.  "

        out = ai_assist.suggest(self.s, 1, self.cid, kind="reply",
                                keys={"GOOGLE_API_KEY": "k"}, call_model=fake)
        self.assertFalse(out["mock"])
        self.assertFalse(out["cached"])
        self.assertEqual(out["suggestion"], "A grounded on-brand reply.")
        self.assertIn("ATM", seen["prompt"])

    def test_a_second_draftless_reply_call_is_served_from_cache(self):
        calls = []

        def fake(system, prompt, *, keys):
            calls.append(1)
            return f"reply #{len(calls)}"

        first = ai_assist.suggest(self.s, 1, self.cid, kind="reply",
                                  keys={"GOOGLE_API_KEY": "k"}, call_model=fake)
        self.db.commit()
        second = ai_assist.suggest(self.s, 1, self.cid, kind="reply",
                                   keys={"GOOGLE_API_KEY": "k"}, call_model=fake)
        self.assertFalse(first["cached"])
        self.assertTrue(second["cached"])
        self.assertEqual(second["suggestion"], first["suggestion"])
        self.assertEqual(len(calls), 1)          # the model was only ever asked once

    def test_a_new_message_invalidates_the_cache(self):
        from core import cases
        calls = []

        def fake(system, prompt, *, keys):
            calls.append(1)
            return f"reply #{len(calls)}"

        ai_assist.suggest(self.s, 1, self.cid, kind="reply",
                          keys={"GOOGLE_API_KEY": "k"}, call_model=fake)
        self.db.commit()
        cases.post_reply(self.s, self.cid, 1, body="we're on it", channel="x", actor=1)
        self.db.commit()
        out = ai_assist.suggest(self.s, 1, self.cid, kind="reply",
                                keys={"GOOGLE_API_KEY": "k"}, call_model=fake)
        self.assertFalse(out["cached"])
        self.assertEqual(len(calls), 2)

    def test_a_call_with_a_draft_never_uses_the_cache(self):
        calls = []

        def fake(system, prompt, *, keys):
            calls.append(1)
            return f"reply #{len(calls)}"

        ai_assist.suggest(self.s, 1, self.cid, kind="reply", draft="a draft",
                          keys={"GOOGLE_API_KEY": "k"}, call_model=fake)
        self.db.commit()
        out = ai_assist.suggest(self.s, 1, self.cid, kind="reply", draft="a draft",
                                keys={"GOOGLE_API_KEY": "k"}, call_model=fake)
        self.assertFalse(out["cached"])
        self.assertEqual(len(calls), 2)

    def test_a_gemini_failure_falls_back_to_its_openrouter_copy(self):
        # found live: a real case hit a genuine Gemini 503 with no fallback
        # at all -- this path now matches integrations/llm/panel.py's roster.
        with patch.object(ai_assist, "_call_gemini_direct",
                          side_effect=RuntimeError("HTTP Error 503: Service Unavailable")), \
             patch("integrations.llm.base.call_openrouter",
                  return_value="A reply from the OpenRouter fallback.") as openrouter:
            out = ai_assist.suggest(self.s, 1, self.cid, kind="reply",
                                    keys={"GOOGLE_API_KEY": "k", "OPENROUTER_API_KEY": "ork"})
        self.assertFalse(out["mock"])
        self.assertEqual(out["suggestion"], "A reply from the OpenRouter fallback.")
        self.assertEqual(openrouter.call_args.kwargs["model"], "google/gemini-3.5-flash")

    def test_both_routes_failing_raises_a_clean_actionable_error(self):
        with patch.object(ai_assist, "_call_gemini_direct",
                          side_effect=RuntimeError("timed out")), \
             patch("integrations.llm.base.call_openrouter",
                  side_effect=RuntimeError("HTTP Error 429: Too Many Requests")):
            with self.assertRaises(ValueError) as caught:
                ai_assist.suggest(self.s, 1, self.cid, kind="reply",
                                  keys={"GOOGLE_API_KEY": "k", "OPENROUTER_API_KEY": "ork"})
        self.assertIn("429", str(caught.exception))

    def test_force_bypasses_an_otherwise_valid_cache_hit(self):
        calls = []

        def fake(system, prompt, *, keys):
            calls.append(1)
            return f"reply #{len(calls)}"

        ai_assist.suggest(self.s, 1, self.cid, kind="reply",
                          keys={"GOOGLE_API_KEY": "k"}, call_model=fake)
        self.db.commit()
        out = ai_assist.suggest(self.s, 1, self.cid, kind="reply", force=True,
                                keys={"GOOGLE_API_KEY": "k"}, call_model=fake)
        self.assertFalse(out["cached"])
        self.assertEqual(len(calls), 2)


class SuggestApiTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        # the route calls _app.keys(ws), which picks up a real GOOGLE_API_KEY
        # from the environment if one is set — stub the model call so the test
        # is deterministic and never leaves the process.
        self._model = patch.object(
            ai_assist, "_default_call_model",
            lambda system, prompt, *, keys: "A grounded, on-brand reply.")
        self._model.start()
        self.addCleanup(self._model.stop)

    def _login(self):
        token = self.client.get("/api/v1/csrf").get_json()["token"]
        self.client.post("/api/v1/auth/login",
                         json={"username": "admin", "password": "admin123"},
                         headers={"X-CSRF-Token": token})
        with self.client.session_transaction() as s:
            self.csrf = s.get("csrf_token", "")

    def _post(self, path, body):
        return self.client.post(path, json=body, headers={"X-CSRF-Token": self.csrf})

    def test_suggest_returns_text_and_sends_nothing(self):
        self._login()
        cid = self._post("/api/v1/care/cases/ingest",
                         {"platform": "x", "handle": "@c", "body": "help please"}
                         ).get_json()["case_id"]
        resp = self._post(f"/api/v1/care/cases/{cid}/suggest", {"kind": "reply"})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()["suggestion"])

        # nothing was sent: no outbound message on the case, no outbound_action
        detail = self.client.get(f"/api/v1/care/cases/{cid}").get_json()
        self.assertFalse([m for m in detail["messages"] if m["direction"] == "outbound"])
        conn = self.app.db_operator()
        try:
            n = conn.execute("SELECT count(*) FROM outbound_action").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(n, 0)

    def test_suggest_reply_is_cached_across_requests(self):
        self._login()
        cid = self._post("/api/v1/care/cases/ingest",
                         {"platform": "x", "handle": "@c", "body": "help please"}
                         ).get_json()["case_id"]
        first = self._post(f"/api/v1/care/cases/{cid}/suggest", {"kind": "reply"})
        second = self._post(f"/api/v1/care/cases/{cid}/suggest", {"kind": "reply"})
        self.assertFalse(first.get_json()["cached"])
        self.assertTrue(second.get_json()["cached"])
        self.assertEqual(first.get_json()["suggestion"], second.get_json()["suggestion"])

    def test_suggest_bad_kind_is_400(self):
        self._login()
        cid = self._post("/api/v1/care/cases/ingest",
                         {"platform": "x", "handle": "@c", "body": "x"}).get_json()["case_id"]
        self.assertEqual(
            self._post(f"/api/v1/care/cases/{cid}/suggest", {"kind": "nope"}).status_code, 400)

    def test_suggest_reply_names_the_real_focus_brand(self):
        # Hamza: 'Make sure the ai suggested replies include the brand name
        # eg "thank you for contacting chase securities"' -- workspace 1's
        # seeded focus brand is Bank Alfalah (db.bootstrap.seed()). Nests on
        # top of the class-level _default_call_model patch (correctly
        # restores to it, not to the unpatched original, on exit).
        seen = {}

        def fake(system, prompt, *, keys):
            seen["system"] = system
            return "ok"

        self._login()
        cid = self._post("/api/v1/care/cases/ingest",
                         {"platform": "x", "handle": "@c", "body": "help please"}
                         ).get_json()["case_id"]
        with patch.object(ai_assist, "_default_call_model", fake):
            self._post(f"/api/v1/care/cases/{cid}/suggest", {"kind": "reply"})
        self.assertIn("Bank Alfalah", seen["system"])


class TrimIncompleteTailTests(unittest.TestCase):
    def test_a_complete_sentence_is_untouched(self):
        self.assertEqual(ai_assist._trim_incomplete_tail("Thanks for reaching out."),
                         "Thanks for reaching out.")

    def test_a_response_cut_off_mid_sentence_is_trimmed_to_the_last_full_one(self):
        text = "Thanks for reaching out. Could you please let us"
        self.assertEqual(ai_assist._trim_incomplete_tail(text), "Thanks for reaching out.")

    def test_no_sentence_boundary_at_all_is_left_alone_rather_than_blanked(self):
        self.assertEqual(ai_assist._trim_incomplete_tail("no punctuation here"),
                         "no punctuation here")

    def test_trailing_quote_or_paren_after_punctuation_counts_as_complete(self):
        self.assertEqual(ai_assist._trim_incomplete_tail('She said "hello."'),
                         'She said "hello."')


if __name__ == "__main__":
    unittest.main()
