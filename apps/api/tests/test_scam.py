import json
import unittest

from ._db import DbTestCase
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core import scam

ROOT = Path(__file__).resolve().parents[1]


def _day(offset):
    return (datetime.now(timezone.utc) - timedelta(days=offset)).strftime("%Y-%m-%dT09:00:00Z")


class ScoreTextTests(unittest.TestCase):
    def test_weights_add_per_distinct_signal(self):
        score, hits = scam.score_text(
            "Send your details on WhatsApp 0300 1234567, quick support team"
        )
        self.assertIn("whatsapp", hits)
        self.assertIn("phone", hits)
        self.assertIn("impersonation", hits)
        self.assertEqual(score, 4 + 3 + 2)

    def test_clean_comment_scores_zero(self):
        self.assertEqual(scam.score_text("Great service at the Gulberg branch today"), (0, []))

    def test_shortened_link_and_telegram(self):
        score, hits = scam.score_text("claim your reward at bit.ly/x9 or t.me/agent")
        self.assertEqual(set(hits), {"short_link", "telegram", "payout_lure"})
        self.assertEqual(score, 3 + 3 + 2)

    def test_severity_bands_are_inclusive_lower_bounds(self):
        self.assertEqual(scam.severity_of(0), "clear")
        self.assertEqual(scam.severity_of(1), "low")
        self.assertEqual(scam.severity_of(4), "elevated")
        self.assertEqual(scam.severity_of(7), "high")


class ScanTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'Bank Alfalah','PK','now')")
        self.db.execute(
            "INSERT INTO brand(id,workspace_id,name,is_focus) VALUES (1,1,'Bank Alfalah',1)")
        self._next_id = 1


    _DEFAULT = object()

    def _item(self, *, source, body, kind="comment", actor_hash=None, author=None,
              published=_DEFAULT, surface="facebook", kind_source="licensed", mention=True):
        iid = self._next_id
        self._next_id += 1
        raw = {"kind": kind}
        if actor_hash:
            raw["actor_hash"] = actor_hash
        when = _day(1) if published is self._DEFAULT else published
        self.db.execute(
            """INSERT INTO item(id,workspace_id,surface,source,source_kind,external_id,
                                url,outlet,author,published_at,body,raw_json,collected_at,
                                content_hash)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (iid, 1, surface, source, kind_source, f"ext-{iid}", f"https://x/{iid}",
             "Bank Alfalah", author, when, body, json.dumps(raw),
             "now", f"h{iid}"))
        if mention:
            self.db.execute(
                "INSERT INTO mention(item_id,brand_id,rule) VALUES (?,1,'brightdata_owned_channel')",
                (iid,))
        self.db.commit()
        return iid

    def test_flags_scores_and_ignores_non_comments(self):
        self._item(source="brightdata_facebook_comments",
                   body="WhatsApp me on 03001234567 for your refund department claim",
                   actor_hash="hash-a")
        self._item(source="brightdata_instagram_comments",
                   body="lovely branch staff", actor_hash="hash-b", surface="instagram")
        # a post on a Meta source must not be scanned
        self._item(source="meta_facebook", body="Contact our agent on t.me/x now",
                   kind="post")
        # a non-comment source is out of scope entirely
        self._item(source="googlenews_rss", body="WhatsApp 03001234567", kind="comment",
                   kind_source="public", surface="news")

        report = scam.scan(self.db, 1)

        self.assertEqual(report["summary"]["scanned"], 2)
        self.assertEqual(report["summary"]["flagged"], 1)
        flag = report["flagged"][0]
        self.assertEqual(flag["score"], 4 + 3 + 2)
        self.assertEqual(flag["severity"], "high")
        self.assertEqual(set(flag["signals"]), {"whatsapp", "phone", "payout_lure"})
        self.assertTrue(flag["author_ref"].startswith("a:"))
        self.assertEqual(report["coverage"]["sources"],
                         ["brightdata_facebook_comments", "brightdata_instagram_comments"])
        self.assertEqual(report["policy"]["max_score"], sum(w for _k, _l, w, _p in scam.SIGNALS))

    def test_repeat_offender_grouping_by_actor_hash(self):
        for _ in range(2):
            self._item(source="brightdata_facebook_comments",
                       body="DM me, contact our admin on wa.me/123", actor_hash="repeat")
        self._item(source="brightdata_facebook_comments",
                   body="message me privately, telegram t.me/z", actor_hash="once")

        report = scam.scan(self.db, 1)

        self.assertEqual(report["summary"]["repeat_offenders"], 1)
        top = report["offenders"][0]
        self.assertEqual(top["actor_ref"], "a:repeat")
        self.assertEqual(top["flagged"], 2)
        self.assertTrue(top["repeat"])
        self.assertTrue(all(flag["repeat"] == (flag["author_ref"] == "a:repeat")
                            for flag in report["flagged"]))

    def test_period_filter_excludes_older_and_undated_comments(self):
        self._item(source="brightdata_facebook_comments",
                   body="whatsapp 03001234567", actor_hash="fresh", published=_day(3))
        self._item(source="brightdata_facebook_comments",
                   body="whatsapp 03001234567", actor_hash="stale", published=_day(60))
        self._item(source="brightdata_facebook_comments",
                   body="whatsapp 03001234567", actor_hash="undated", published=None)

        report = scam.scan(self.db, 1, days=7)
        self.assertEqual(report["summary"]["scanned"], 1)
        self.assertEqual(report["summary"]["flagged"], 1)


if __name__ == "__main__":
    unittest.main()
