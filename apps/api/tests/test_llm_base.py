"""integrations/llm/base.py -- the two HTTP primitives the Vantage panel calls."""
import io
import json
import unittest
from unittest.mock import patch

from integrations import llm


class _Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


class GeminiTests(unittest.TestCase):
    def test_no_key_raises_without_a_network_call(self):
        with self.assertRaises(llm.LlmError):
            llm.call_gemini("hi", keys={})

    def test_happy_path_extracts_the_text(self):
        seen = {}

        def fake(req, timeout=None):
            seen["url"] = req.full_url
            seen["key_header"] = req.get_header("X-goog-api-key")
            return _Resp(json.dumps(
                {"candidates": [{"content": {"parts": [{"text": "Chase is fine."}]}}]}
            ).encode())

        with patch("integrations.llm.base.urllib.request.urlopen", fake):
            out = llm.call_gemini("Tell me about Chase", keys={"GOOGLE_API_KEY": "gk"})
        self.assertEqual(out, "Chase is fine.")
        self.assertIn("gemini-3.5-flash:generateContent", seen["url"])
        self.assertEqual(seen["key_header"], "gk")

    def test_http_error_becomes_llm_error(self):
        import urllib.error

        def boom(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 429, "rate limited", {},
                                         io.BytesIO(b'{"error":{"message":"quota"}}'))

        with patch("integrations.llm.base.urllib.request.urlopen", boom):
            with self.assertRaises(llm.LlmError):
                llm.call_gemini("hi", keys={"GOOGLE_API_KEY": "gk"})

    def test_empty_response_is_an_error_not_a_blank_string(self):
        def fake(req, timeout=None):
            return _Resp(json.dumps({"candidates": []}).encode())

        with patch("integrations.llm.base.urllib.request.urlopen", fake):
            with self.assertRaises(llm.LlmError):
                llm.call_gemini("hi", keys={"GOOGLE_API_KEY": "gk"})


class OpenRouterTests(unittest.TestCase):
    def test_no_key_raises_without_a_network_call(self):
        with self.assertRaises(llm.LlmError):
            llm.call_openrouter("hi", keys={}, model="openai/gpt-4o-mini")

    def test_happy_path_extracts_the_message_content(self):
        seen = {}

        def fake(req, timeout=None):
            seen["body"] = json.loads(req.data)
            seen["auth"] = req.get_header("Authorization")
            return _Resp(json.dumps(
                {"choices": [{"message": {"content": "AKD is a rival firm."}}]}
            ).encode())

        with patch("integrations.llm.base.urllib.request.urlopen", fake):
            out = llm.call_openrouter("Compare firms", keys={"OPENROUTER_API_KEY": "ork"},
                                      model="openai/gpt-4o-mini")
        self.assertEqual(out, "AKD is a rival firm.")
        self.assertEqual(seen["body"]["model"], "openai/gpt-4o-mini")
        self.assertEqual(seen["auth"], "Bearer ork")

    def test_http_error_becomes_llm_error(self):
        import urllib.error

        def boom(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 402, "no credit", {},
                                         io.BytesIO(b'{"error":"insufficient credit"}'))

        with patch("integrations.llm.base.urllib.request.urlopen", boom):
            with self.assertRaises(llm.LlmError):
                llm.call_openrouter("hi", keys={"OPENROUTER_API_KEY": "ork"}, model="m")


class PanelRosterTests(unittest.TestCase):
    def test_gemini_tries_direct_first_then_falls_back_to_openrouter(self):
        with patch("integrations.llm.base.call_gemini",
                  side_effect=llm.LlmError("down")) as g, \
             patch("integrations.llm.base.call_openrouter",
                  return_value="via openrouter") as orr:
            provider, model, text = llm.ask("gemini", "hi", keys={"OPENROUTER_API_KEY": "k"})
        g.assert_called_once()
        orr.assert_called_once_with("hi", keys={"OPENROUTER_API_KEY": "k"},
                                    model="google/gemini-3.5-flash")
        self.assertEqual((provider, text), ("openrouter", "via openrouter"))

    def test_gemini_direct_success_never_touches_openrouter(self):
        with patch("integrations.llm.base.call_gemini", return_value="direct answer") as g, \
             patch("integrations.llm.base.call_openrouter") as orr:
            provider, model, text = llm.ask("gemini", "hi", keys={})
        orr.assert_not_called()
        self.assertEqual((provider, model, text), ("google", "gemini-3.5-flash", "direct answer"))

    def test_non_gemini_members_go_straight_to_openrouter(self):
        with patch("integrations.llm.base.call_openrouter", return_value="gpt says hi") as orr:
            provider, model, text = llm.ask("gpt-4o-mini", "hi", keys={})
        orr.assert_called_once_with("hi", keys={}, model="openai/gpt-4o-mini")
        self.assertEqual(provider, "openrouter")

    def test_unknown_model_id_raises(self):
        with self.assertRaises(llm.LlmError):
            llm.ask("does-not-exist", "hi", keys={})


if __name__ == "__main__":
    unittest.main()
