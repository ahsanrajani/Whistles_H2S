from ._db import DbTestCase

from core import branch_complaints

CSV_HEADER = "Branch Name,Complainant,Complaint Date,Complaint Text (paraphrased),Source URL\n"


class ParseCsvTests(DbTestCase):
    def test_rejects_wrong_headers(self):
        rows, err = branch_complaints.parse_csv(b"Branch,Complainant\nx,y\n")
        self.assertEqual(rows, [])
        self.assertIn("Branch Name", err)

    def test_parses_rows_and_strips_whitespace(self):
        raw = (CSV_HEADER +
               ' Main Sargodha , Ali Raza ,2026-01-05, ATM ate my card , https://x/1 \n')
        rows, err = branch_complaints.parse_csv(raw.encode())
        self.assertIsNone(err)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Branch Name"], "Main Sargodha")
        self.assertEqual(rows[0]["Complaint Text (paraphrased)"], "ATM ate my card")
        self.assertEqual(rows[0]["_index"], 1)


class ImportRowsTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.execute(
            "INSERT INTO brand(id,workspace_id,name,is_focus) VALUES (1,1,'Bank Alfalah',1)")
        self.db.commit()

    def _rows(self, csv_text):
        rows, err = branch_complaints.parse_csv((CSV_HEADER + csv_text).encode())
        self.assertIsNone(err)
        return rows

    def test_inserts_item_and_explicit_mention_for_a_matched_branch(self):
        rows = self._rows(
            "Main Sargodha,Ali Raza,2026-01-05,ATM ate my card and no refund,https://x/1\n")
        result = branch_complaints.import_rows(
            self.db.session, workspace_id=1, brand_id=1, rows=rows)
        self.assertEqual(result, {"inserted": 1, "skipped": 0, "errors": []})

        item = self.db.execute(
            "SELECT surface, source, source_kind, rating FROM item WHERE workspace_id=1").fetchone()
        self.assertEqual(item[0], branch_complaints.SURFACE)
        self.assertEqual(item[1], branch_complaints.SOURCE)
        self.assertEqual(item[2], "licensed")
        self.assertIsNone(item[3])

        mention = self.db.execute(
            "SELECT brand_id, rule FROM mention WHERE workspace_id=1").fetchone()
        self.assertEqual(mention[0], 1)
        self.assertEqual(mention[1], branch_complaints.RULE)

        # no sentiment/category -- left for the async scoring job
        self.assertIsNone(self.db.execute(
            "SELECT 1 FROM sentiment WHERE mention_id = (SELECT id FROM mention LIMIT 1)").fetchone())

    def test_unmatched_branch_name_is_a_row_error(self):
        rows = self._rows("Nowhere Branch,Ali,2026-01-05,bad service,https://x/2\n")
        result = branch_complaints.import_rows(
            self.db.session, workspace_id=1, brand_id=1, rows=rows)
        self.assertEqual(result["inserted"], 0)
        self.assertEqual(result["skipped"], 1)
        self.assertIn("no branch match", result["errors"][0]["reason"])

    def test_empty_complaint_text_is_a_row_error(self):
        rows = self._rows("Main Sargodha,Ali,2026-01-05,,https://x/3\n")
        result = branch_complaints.import_rows(
            self.db.session, workspace_id=1, brand_id=1, rows=rows)
        self.assertEqual(result["inserted"], 0)
        self.assertEqual(result["skipped"], 1)
        self.assertIn("empty complaint text", result["errors"][0]["reason"])

    def test_duplicate_source_url_in_one_upload_gets_a_distinct_stored_url(self):
        rows = self._rows(
            "Main Sargodha,Ali,2026-01-05,ATM ate my card,https://x/same\n"
            "Main Sargodha,Bilal,2026-01-06,branch was rude,https://x/same\n")
        result = branch_complaints.import_rows(
            self.db.session, workspace_id=1, brand_id=1, rows=rows)
        self.assertEqual(result["inserted"], 2)
        urls = {r[0] for r in self.db.execute(
            "SELECT url FROM item WHERE workspace_id=1 ORDER BY id").fetchall()}
        self.assertEqual(len(urls), 2)
        self.assertIn("https://x/same", urls)

    def test_reuploading_the_same_row_is_a_no_op(self):
        rows = self._rows("Main Sargodha,Ali,2026-01-05,ATM ate my card,https://x/1\n")
        first = branch_complaints.import_rows(
            self.db.session, workspace_id=1, brand_id=1, rows=rows)
        self.db.commit()
        second = branch_complaints.import_rows(
            self.db.session, workspace_id=1, brand_id=1, rows=rows)
        self.assertEqual(first["inserted"], 1)
        self.assertEqual(second["inserted"], 0)
        self.assertEqual(second["skipped"], 1)
        count = self.db.execute("SELECT COUNT(*) FROM item WHERE workspace_id=1").fetchone()[0]
        self.assertEqual(count, 1)
