"""Vertex AI route: enablement, request shape, error mapping, and that the shared call paths prefer it."""
import io
import json
import os
import unittest
import urllib.error
from unittest.mock import patch

from core import ai_assist
from integrations.llm import base, vertex


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _ok(text="hello"):
    return _Resp(json.dumps({"candidates": [{"content": {"parts": [{"text": text}]}}]}).encode())


class VertexTests(unittest.TestCase):
    def setUp(self):
        vertex._token.update(value=None, expires=0.0)
        self.env = patch.dict(os.environ, {"GURU_LLM": "vertex", "GOOGLE_CLOUD_PROJECT": "proj-1",
                                           "VERTEX_LOCATION": "asia-southeast1"}, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)

    def _fake(self, seen):
        def fake(req, timeout=0):
            seen.append(req)
            if "metadata.google.internal" in req.full_url:
                return _Resp(json.dumps({"access_token": "tok", "expires_in": 3600}).encode())
            return _ok("generated")
        return fake

    def test_disabled_by_default(self):
        with patch.dict(os.environ, {"GURU_LLM": ""}):
            self.assertFalse(vertex.enabled())

    def test_generate_uses_regional_endpoint_bearer_token_and_system_prompt(self):
        seen = []
        with patch("urllib.request.urlopen", self._fake(seen)):
            out = vertex.generate("hi", system="be brief", model_name="m1")
        self.assertEqual(out, "generated")
        call = seen[-1]
        self.assertTrue(call.full_url.startswith(
            "https://asia-southeast1-aiplatform.googleapis.com/v1/projects/proj-1/locations/asia-southeast1/"))
        self.assertTrue(call.full_url.endswith("/publishers/google/models/m1:generateContent"))
        self.assertEqual(call.get_header("Authorization"), "Bearer tok")
        self.assertEqual(json.loads(call.data)["systemInstruction"]["parts"][0]["text"], "be brief")

    def test_global_location_uses_global_host(self):
        with patch.dict(os.environ, {"VERTEX_LOCATION": "global"}):
            self.assertTrue(vertex._url("m").startswith("https://aiplatform.googleapis.com/v1/projects/proj-1/locations/global/"))

    def test_token_is_cached(self):
        seen = []
        with patch("urllib.request.urlopen", self._fake(seen)):
            vertex.generate("a")
            vertex.generate("b")
        self.assertEqual(sum("metadata" in r.full_url for r in seen), 1)

    def test_http_error_is_mapped(self):
        def boom(req, timeout=0):
            if "metadata" in req.full_url:
                return _Resp(json.dumps({"access_token": "t", "expires_in": 3600}).encode())
            raise urllib.error.HTTPError(req.full_url, 403, "no", {}, io.BytesIO(b"denied"))
        with patch("urllib.request.urlopen", boom):
            with self.assertRaises(vertex.VertexError) as cm:
                vertex.generate("x")
        self.assertIn("403", str(cm.exception))

    def test_no_metadata_server_is_a_vertex_error(self):
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("offline")):
            with self.assertRaises(vertex.VertexError):
                vertex.generate("x")

    def test_call_gemini_prefers_vertex_and_needs_no_key(self):
        with patch.object(vertex, "generate", return_value="from vertex") as gen:
            self.assertEqual(base.call_gemini("p", keys={}), "from vertex")
        gen.assert_called_once()

    def test_call_gemini_failure_surfaces_as_llm_error(self):
        with patch.object(vertex, "generate", side_effect=vertex.VertexError("boom")):
            with self.assertRaises(base.LlmError):
                base.call_gemini("p", keys={})

    def test_reply_drafting_uses_vertex(self):
        with patch.object(vertex, "generate", return_value="draft") as gen:
            self.assertEqual(ai_assist._call_gemini_direct("sys", "prompt", keys={}), "draft")
        self.assertEqual(gen.call_args.kwargs["system"], "sys")


if __name__ == "__main__":
    unittest.main()
