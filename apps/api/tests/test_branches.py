import unittest

from core import branches


class ResolveTests(unittest.TestCase):
    def test_alias_phrase_matches(self):
        hit = branches.resolve("terrible service at the Allama Iqbal Town Lahore branch today")
        self.assertIsNotNone(hit)
        key, method, conf = hit
        self.assertEqual(key, "ait-lahore")
        self.assertEqual(method, "alias")
        self.assertGreater(conf, 0.4)

    def test_name_token_plus_city(self):
        hit = branches.resolve("the Bahria branch in Rawalpindi kept my father waiting")
        self.assertEqual(hit[0], "bahria-ph7-rwp")

    def test_branch_code_is_the_strongest_signal(self):
        hit = branches.resolve("Haroonabad branch code 0125, funds frozen for weeks")
        self.assertEqual(hit[0], "haroonabad")
        self.assertEqual(hit[1], "code")
        self.assertEqual(hit[2], 1.0)

    def test_no_branch_named_returns_none(self):
        self.assertIsNone(branches.resolve("Bank Alfalah app is down again, cannot log in"))
        self.assertIsNone(branches.resolve(""))

    def test_two_aliases_tie_across_cities_resolves_to_none(self):
        # "napier road" (Karachi) and "paris road" (Sialkot) each score one alias.
        self.assertIsNone(branches.resolve(
            "the Napier Road branch and the Paris Road branch were both a mess"))

    def test_catalog_shape(self):
        cat = branches.catalog()
        self.assertEqual(len(cat), len(branches.BRANCHES))
        self.assertEqual(set(cat[0]), {"key", "name", "code", "city"})


if __name__ == "__main__":
    unittest.main()
