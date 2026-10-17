"""core/seo.py -- real DataForSEO brand-SERP results reshaped into
per-brand search visibility. No new collection, just a different read."""
import unittest

import sqlalchemy as sa

from core import seo

from ._db import DbTestCase

BRANDS = [{"id": 1, "name": "Chase Securities", "is_focus": True},
         {"id": 2, "name": "AKD Securities", "is_focus": False}]


class DomainVisibilityTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (1,'WS','PK','now')")
        self.db.commit()
        self.s = self.db.session

    def _item(self, iid, *, outlet, url, rank, source="dataforseo_brand_serp"):
        self.s.execute(sa.text("""
            INSERT INTO item(id,workspace_id,surface,source,source_kind,external_id,
                             url,outlet,raw_json,collected_at,content_hash)
            VALUES (:id,1,'web',:source,'licensed',:ext,:url,:outlet,:raw,'now',:ext)
        """), {"id": iid, "source": source, "ext": f"e{iid}", "url": url, "outlet": outlet,
               "raw": f'{{"rank": {rank}}}'})

    def test_a_brands_own_domain_is_attributed_to_it(self):
        self._item(1, outlet="www.akdsecurities.com", url="https://www.akdsecurities.com/", rank=1)
        self.db.commit()
        out = seo.domain_visibility(self.s, 1, brands=BRANDS)
        akd = next(b for b in out["brands"] if b["name"] == "AKD Securities")
        self.assertEqual(len(akd["own_domains"]), 1)
        self.assertEqual(akd["own_domains"][0]["domain"], "www.akdsecurities.com")
        self.assertEqual(akd["own_domains"][0]["best_rank"], 1)

    def test_an_abbreviated_domain_is_not_guessed_at(self):
        """"AKD Securities" -> "akdsl.com" is a real abbreviation (initials
        + a suffix), not a substring/prefix of the brand's own name -- a
        looser match here is exactly what produced two real, live false
        positives Hamza caught (2026-09-12): "chasevalue.pk" attributed to
        "Chase Securities" on a bare "chase" prefix, and "worldbank.org" /
        "lloydsbank.com" attributed to "Bank Alfalah" on a bare "bank"
        substring. Safer to leave an abbreviation unattributed (third_party)
        than risk a wrong one -- set BRAND_DOMAINS for the focus brand
        instead of relying on this guess."""
        self._item(1, outlet="www.akdsl.com", url="https://www.akdsl.com/", rank=1)
        self.db.commit()
        out = seo.domain_visibility(self.s, 1, brands=BRANDS)
        akd = next(b for b in out["brands"] if b["name"] == "AKD Securities")
        self.assertEqual(akd["own_domains"], [])
        self.assertEqual(out["third_party"][0]["domain"], "www.akdsl.com")

    def test_a_lookalike_domain_is_not_falsely_attributed(self):
        """Live, real false positives (2026-09-12): a domain that merely
        starts with or contains a brand's first word is not that brand's
        own site."""
        self._item(1, outlet="chasevalue.pk", url="https://chasevalue.pk/", rank=2)
        self._item(2, outlet="www.worldbank.org", url="https://www.worldbank.org/", rank=1,
                   source="dataforseo_serp")
        self.db.commit()
        out = seo.domain_visibility(self.s, 1, brands=BRANDS)
        for b in out["brands"]:
            self.assertEqual(b["own_domains"], [])
        third_party_domains = {row["domain"] for row in out["third_party"]}
        self.assertEqual(third_party_domains, {"chasevalue.pk", "www.worldbank.org"})

    def test_an_unattributable_domain_is_third_party(self):
        self._item(1, outlet="www.facebook.com",
                   url="https://www.facebook.com/ChaseSecurities/", rank=6)
        self.db.commit()
        out = seo.domain_visibility(self.s, 1, brands=BRANDS)
        self.assertEqual(out["third_party"][0]["domain"], "www.facebook.com")
        self.assertEqual(sum(len(b["own_domains"]) for b in out["brands"]), 0)

    def test_best_rank_and_appearance_count_across_repeats(self):
        self._item(1, outlet="www.akdsecurities.com", url="https://www.akdsecurities.com/", rank=3)
        self._item(2, outlet="www.akdsecurities.com", url="https://www.akdsecurities.com/about", rank=1)
        self.db.commit()
        out = seo.domain_visibility(self.s, 1, brands=BRANDS)
        akd = next(b for b in out["brands"] if b["name"] == "AKD Securities")
        self.assertEqual(akd["own_domains"][0]["best_rank"], 1)
        self.assertEqual(akd["own_domains"][0]["appearances"], 2)

    def test_a_row_with_no_rank_is_ignored(self):
        self.s.execute(sa.text("""
            INSERT INTO item(id,workspace_id,surface,source,source_kind,external_id,
                             url,outlet,raw_json,collected_at,content_hash)
            VALUES (1,1,'web','dataforseo_brand_serp','licensed','e1',
                   'https://x','x.com','{}','now','e1')"""))
        self.db.commit()
        out = seo.domain_visibility(self.s, 1, brands=BRANDS)
        self.assertEqual(out["total_domains"], 0)

    def test_workspaces_are_isolated(self):
        self.db.execute(
            "INSERT INTO workspace(id,name,market,created_at) VALUES (2,'WS2','PK','now')")
        self.db.commit()
        self._item(1, outlet="www.akdsl.com", url="https://www.akdsl.com/", rank=1)
        self.db.commit()
        out = seo.domain_visibility(self.s, 2, brands=BRANDS)
        self.assertEqual(out["total_domains"], 0)


if __name__ == "__main__":
    unittest.main()
