import json
import unittest

from ._db import DbTestCase
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core import report

ROOT = Path(__file__).resolve().parents[1]


def _day(offset):
    return (datetime.now(timezone.utc) - timedelta(days=offset)).strftime("%Y-%m-%dT09:00:00Z")


class ReportTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.execute(
            "INSERT INTO brand(id,workspace_id,name,is_focus) VALUES (1,1,'Bank Alfalah',1)")
        self._id = 0


    def _row(self, *, surface, source, text, rating, offset, branch_key=None,
             sentiment="neg", category="complaint"):
        self._id += 1
        raw = {"branch_key": branch_key} if branch_key else {"kind": "comment"}
        self.db.execute(
            """INSERT INTO item(id,workspace_id,surface,source,source_kind,external_id,url,
                                outlet,published_at,body,rating,raw_json,collected_at,content_hash)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (self._id, 1, surface, source, "licensed", f"e{self._id}", f"https://x/{self._id}",
             "Google Maps", _day(offset), text, rating, json.dumps(raw), "now", f"h{self._id}"))
        self.db.execute(
            "INSERT INTO mention(id,item_id,brand_id,rule) VALUES (?,?,1,'seed')",
            (self._id, self._id))
        self.db.execute(
            """INSERT INTO sentiment(mention_id,label,model_id,scored_lang,scored_at)
               VALUES (?,?,?,?,?)""", (self._id, sentiment, "seed", "en", "now"))
        if category:
            self.db.execute(
                """INSERT INTO mention_class(mention_id,category,model_id,classified_at)
                   VALUES (?,?,?,?)""", (self._id, category, "seed", "now"))
        self.db.commit()

    def _load(self):
        # a Critical complaint (regulator + loss + blocked)  -> triage_critical fires
        self._row(surface="facebook", source="brightdata_facebook_comments",
                  text="Account blocked, unauthorized transaction, money not reversed. "
                       "Escalating to the Banking Mohtasib and my lawyer.",
                  rating=None, offset=2)
        # a low-rated review cluster on one branch -> branch rules fire
        for i in range(6):
            self._row(surface="branch_review", source="google_maps_reviews",
                      text="Biometric verification machine was down again, staff were rude "
                           "and unhelpful. Long queue, only one counter.",
                      rating=1, offset=3 + i, branch_key="bahria-ph7-rwp")

    def test_priorities_are_ranked_actionable_items(self):
        self._load()
        prios = report.priorities(self.db, 1)
        self.assertTrue(prios)
        for item in prios:
            self.assertEqual(set(item) >= {"key", "severity", "title", "detail", "href", "when"}, True)
            self.assertTrue(item["href"].startswith("/"))
        # critical items sort ahead of warnings
        severities = [p["severity"] for p in prios]
        self.assertEqual(severities, sorted(severities, key={"critical": 0, "warning": 1, "info": 2}.get))
        self.assertTrue(any(p["key"].startswith("branch") for p in prios))

    def test_highlights_shape(self):
        self._load()
        h = report.highlights(self.db, 1)
        self.assertEqual(h["focus_brand"], "Bank Alfalah")
        self.assertEqual(
            set(h["numbers"]),
            {"mentions", "negative_share_pct", "switch_at_risk", "triage_critical",
             "triage_high", "scam_flag_rate_pct", "branches_flagged"})
        self.assertGreaterEqual(h["numbers"]["triage_critical"], 1)
        self.assertGreaterEqual(h["numbers"]["branches_flagged"], 1)
        self.assertTrue(h["worst_branches"])
        self.assertIn("generated_at", h)

    @unittest.skipUnless(report.PDF_OK, "reportlab not installed")
    def test_build_pdf_returns_a_pdf(self):
        self._load()
        pdf = report.build_pdf(report.highlights(self.db, 1))
        self.assertIsInstance(pdf, bytes)
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertGreater(len(pdf), 1000)


if __name__ == "__main__":
    unittest.main()
