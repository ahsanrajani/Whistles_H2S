"""P4.8 — report export engine (CSV / Excel / PDF with charts)."""
import unittest

from core import export_engine as ex

from ._db import ApiTestCase

_PAYLOAD = {
    "total": 10,
    "window": {"start": "2026-06-01", "end": "2026-06-30"},
    "distribution": {"1": 2, "3": 1, "5": 7},
    "by_channel": {"x": {"rate": 0.8, "n": 5}, "facebook": {"rate": 0.5, "n": 4}},
    "agents": [{"user_id": 1, "ready_seconds": 100.0},
               {"user_id": 2, "ready_seconds": 50.0}],
}


class DocumentShapeTests(unittest.TestCase):
    def setUp(self):
        self.doc = ex.document_from(_PAYLOAD, "Test report")

    def test_scalars_and_nested_scalars_become_meta(self):
        self.assertEqual(self.doc["meta"]["total"], 10)
        self.assertEqual(self.doc["meta"]["window.start"], "2026-06-01")

    def test_row_list_becomes_a_table(self):
        agents = next(t for t in self.doc["tables"] if t["name"] == "agents")
        self.assertEqual(agents["columns"], ["user_id", "ready_seconds"])
        self.assertEqual(agents["rows"], [[1, 100.0], [2, 50.0]])

    def test_chartable_maps_get_a_chart_hint(self):
        dist = next(t for t in self.doc["tables"] if t["name"] == "distribution")
        self.assertEqual(dist["chart"]["type"], "bar")
        self.assertEqual(dist["chart"]["val"], 1)

    def test_nested_dict_map_becomes_a_keyed_table(self):
        bc = next(t for t in self.doc["tables"] if t["name"] == "by_channel")
        self.assertEqual(bc["columns"][0], "key")
        self.assertIn("rate", bc["columns"])


class RenderTests(unittest.TestCase):
    def test_csv(self):
        blob = ex.render(_PAYLOAD, "csv", title="t")[2]
        text = blob.decode()
        self.assertIn("# distribution", text)
        self.assertIn("total,10", text)

    def test_xlsx_is_a_zip(self):
        media, ext, blob = ex.render(_PAYLOAD, "xlsx", title="t")
        self.assertEqual(ext, "xlsx")
        self.assertTrue(blob.startswith(b"PK"))

    def test_pdf(self):
        blob = ex.render(_PAYLOAD, "pdf", title="t")[2]
        self.assertTrue(blob.startswith(b"%PDF"))

    def test_unknown_format(self):
        with self.assertRaises(ValueError):
            ex.render(_PAYLOAD, "docx", title="t")


class ExportApiTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        token = self.client.get("/api/v1/csrf").get_json()["token"]
        self.client.post("/api/v1/auth/login",
                         json={"username": "admin", "password": "admin123"},
                         headers={"X-CSRF-Token": token})

    def test_export_endpoint_formats(self):
        base = "/api/v1/reports/export?kind=csat&start=2026-01-01&end=2027-01-01"
        csv_r = self.client.get(base + "&format=csv")
        self.assertEqual(csv_r.status_code, 200)
        self.assertIn("text/csv", csv_r.headers["content-type"])
        self.assertIn(b"issued", csv_r.get_data())

        self.assertTrue(self.client.get(base + "&format=xlsx").get_data().startswith(b"PK"))
        self.assertTrue(self.client.get(base + "&format=pdf").get_data().startswith(b"%PDF"))

    def test_bad_requests(self):
        self.assertEqual(self.client.get(
            "/api/v1/reports/export?kind=metrics&format=csv").status_code, 400)
        self.assertEqual(self.client.get(
            "/api/v1/reports/export?kind=bogus&format=csv").status_code, 400)

    def test_export_is_audited(self):
        self.client.get("/api/v1/reports/export?kind=sla&format=pdf"
                        "&start=2026-01-01&end=2027-01-01")
        conn = self.app.db_operator()
        try:
            row = conn.execute(
                "SELECT action, target FROM audit_event "
                "WHERE action='data.export' ORDER BY id DESC LIMIT 1").fetchone()
        finally:
            conn.close()
        self.assertEqual(row[0], "data.export")
        self.assertEqual(row[1], "report.sla.pdf")


if __name__ == "__main__":
    unittest.main()
