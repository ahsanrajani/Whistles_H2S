"""P1.9a — structured JSON logs with a request id and tenant id on every line."""
import json
import logging
import unittest

from obs import context
from obs.logs import JsonFormatter


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record):
        self.records.append(record)


class JsonFormatterTests(unittest.TestCase):
    def setUp(self):
        self.fmt = JsonFormatter()
        self.addCleanup(context.clear)

    def _fmt(self, record):
        return json.loads(self.fmt.format(record))

    def test_core_fields_are_present_and_json(self):
        rec = logging.makeLogRecord({"name": "guru.test", "levelno": logging.INFO,
                                     "levelname": "INFO", "msg": "hello %s",
                                     "args": ("world",)})
        out = self._fmt(rec)
        self.assertEqual(out["logger"], "guru.test")
        self.assertEqual(out["level"], "INFO")
        self.assertEqual(out["msg"], "hello world")
        self.assertIn("T", out["ts"])                      # ISO-8601

    def test_correlation_ids_come_from_context(self):
        context.bind(request_id="abc123", tenant_id=7)
        out = self._fmt(logging.makeLogRecord({"msg": "x"}))
        self.assertEqual(out["request_id"], "abc123")
        self.assertEqual(out["tenant_id"], 7)

    def test_ids_are_null_when_unset(self):
        out = self._fmt(logging.makeLogRecord({"msg": "x"}))
        self.assertIsNone(out["request_id"])
        self.assertIsNone(out["tenant_id"])

    def test_extra_fields_are_merged(self):
        rec = logging.makeLogRecord({"msg": "http_request", "status": 200,
                                     "path": "/api/v1/overview"})
        out = self._fmt(rec)
        self.assertEqual(out["status"], 200)
        self.assertEqual(out["path"], "/api/v1/overview")

    def test_exception_is_formatted(self):
        try:
            raise ValueError("boom")
        except ValueError:
            import sys
            rec = logging.makeLogRecord({"msg": "failed"})
            rec.exc_info = sys.exc_info()
        out = self._fmt(rec)
        self.assertIn("ValueError: boom", out["exc"])


class RequestCorrelationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from ._client import AsgiTestClient
        cls.client = AsgiTestClient()

    def setUp(self):
        self.cap = _Capture()
        self.cap.setLevel(logging.INFO)
        access = logging.getLogger("guru.access")
        self._saved_level = access.level
        access.setLevel(logging.INFO)
        access.addHandler(self.cap)
        self.addCleanup(access.removeHandler, self.cap)
        self.addCleanup(access.setLevel, self._saved_level)

    def _access_record(self):
        return next(r for r in self.cap.records if r.getMessage() == "http_request")

    def test_response_carries_a_request_id_header(self):
        resp = self.client.get("/api/v1/csrf")
        self.assertTrue(resp.headers.get("X-Request-Id"))

    def test_inbound_request_id_is_honoured(self):
        resp = self.client.get("/api/v1/csrf", headers={"X-Request-Id": "trace-42"})
        self.assertEqual(resp.headers["X-Request-Id"], "trace-42")

    def test_one_access_line_per_request_with_method_path_status(self):
        self.client.get("/api/v1/csrf", headers={"X-Request-Id": "trace-99"})
        rec = self._access_record()
        self.assertEqual(rec.method, "GET")
        self.assertEqual(rec.path, "/api/v1/csrf")
        self.assertEqual(rec.status, 200)
        self.assertEqual(rec.request_id, "trace-99")
        self.assertIsInstance(rec.dur_ms, float)

    def test_probe_paths_are_not_access_logged(self):
        self.client.get("/healthz")
        self.assertEqual(
            [r for r in self.cap.records if r.getMessage() == "http_request"], [])


if __name__ == "__main__":
    unittest.main()
