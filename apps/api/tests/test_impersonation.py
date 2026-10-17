import unittest

from core import impersonation as imp


class PermutationTests(unittest.TestCase):
    def test_base_domain_never_returned_and_output_is_deterministic(self):
        first = imp.permutations("bankalfalah.com")
        second = imp.permutations("BankAlfalah.com")
        self.assertEqual(first, second)
        self.assertNotIn("bankalfalah.com", dict(first))
        self.assertTrue(all(c.endswith((".com", ".net", ".org", ".co", ".info",
                                        ".online", ".site", ".app", ".pk", ".bank",
                                        ".com.pk")) for c, _t in first))

    def test_covers_the_expected_techniques(self):
        cand = dict(imp.permutations("bankalfalah.com"))
        techniques = set(cand.values())
        for expected in ("omission", "repetition", "transposition", "replacement",
                         "tld_swap", "subdomain_bait", "combo", "hyphenation"):
            self.assertIn(expected, techniques)
        self.assertIn("login-bankalfalah.com", cand)
        self.assertEqual(cand["login-bankalfalah.com"], "subdomain_bait")
        self.assertIn("bankalfalah.net", cand)

    def test_multi_part_tld_is_kept_whole(self):
        self.assertEqual(imp._split("bankalfalah.com.pk"), ("bankalfalah", "com.pk"))


class ScanTests(unittest.TestCase):
    def test_no_domains_returns_empty_shape(self):
        report = imp.scan([])
        self.assertEqual(report["candidates"], [])
        self.assertEqual(report["ct_status"], "skipped")
        self.assertIn("techniques", report["policy"])

    def test_resolving_and_ct_bonuses_apply(self):
        resolving = {"bankalfalah.net"}
        certs = {"bankalfalah": {"login-bankalfalah.com", "evil-bankalfalah.xyz"}}

        report = imp.scan(
            ["bankalfalah.com"],
            resolve=lambda host: "resolves" if host in resolving else "nxdomain",
            ct_query=lambda stem: certs.get(stem),
        )

        rows = {row["domain"]: row for row in report["candidates"]}
        # tld_swap (2) + resolves (3) -> 5 -> elevated
        self.assertEqual(rows["bankalfalah.net"]["score"], 2 + 3)
        self.assertEqual(rows["bankalfalah.net"]["band"], "elevated")
        # subdomain_bait (3) + ct bonus (4), and ct_observed flagged
        self.assertTrue(rows["login-bankalfalah.com"]["ct_observed"])
        self.assertEqual(rows["login-bankalfalah.com"]["score"], 3 + 4)
        # a cert name that is not one of our permutations is folded in
        self.assertIn("evil-bankalfalah.xyz", rows)
        self.assertEqual(rows["evil-bankalfalah.xyz"]["technique"], "ct_observed")
        self.assertEqual(report["summary"]["resolving"], 1)
        self.assertGreaterEqual(report["summary"]["ct_observed"], 2)
        self.assertEqual(report["ct_status"], "ok")

    def test_ct_failure_is_marked_unavailable(self):
        report = imp.scan(["bankalfalah.com"],
                          resolve=lambda _h: "nxdomain",
                          ct_query=lambda _s: None)
        self.assertEqual(report["ct_status"], "unavailable")

    def test_budget_stops_dns_checks_and_marks_unknown(self):
        ticks = iter([0.0] + [0.0] * 3 + [99.0] * 200)
        report = imp.scan(
            ["bankalfalah.com"],
            resolve=lambda _h: "resolves",
            ct_query=lambda _s: set(),
            budget_s=1.0,
            clock=lambda: next(ticks),
        )
        dns_values = {row["dns"] for row in report["candidates"]}
        self.assertIn("unknown", dns_values)
        self.assertLess(report["summary"]["dns_checked"], report["summary"]["candidates"])


if __name__ == "__main__":
    unittest.main()
