"""web_backfill — year-qualified brand SERPs for historical coverage."""
import unittest
from datetime import datetime, timezone

from core import collector, sources  # noqa: F401 -- collector must import before
                                     # integrations.adapters is touched directly,
                                     # or their mutual "from core import collector" /
                                     # "from integrations.adapters import ..." cycle
                                     # resolves in the direction that ImportErrors.
from integrations.adapters import DataForSEOWebBackfill


class KeywordExpansionTests(unittest.TestCase):
    def _adapter(self):
        return DataForSEOWebBackfill({}, lambda *_: None, lambda *_a, **_k: None)

    def test_expands_each_term_across_years_back(self):
        a = self._adapter()
        kws = a.keywords(["Chase Securities", "AKD Securities"])
        this_year = datetime.now(timezone.utc).year
        want_years = list(range(this_year - a.YEARS_BACK, this_year))
        self.assertEqual(len(kws), 2 * len(want_years))
        for year in want_years:
            self.assertIn(f"Chase Securities {year}", kws)
            self.assertIn(f"AKD Securities {year}", kws)

    def test_caps_at_three_terms_like_the_parent(self):
        a = self._adapter()
        kws = a.keywords(["A", "B", "C", "D"])
        used = {kw.rsplit(" ", 1)[0] for kw in kws}
        self.assertEqual(used, {"A", "B", "C"})

    def test_never_auto_scheduled(self):
        self.assertEqual(sources.SOURCES["web_backfill"]["cadence"], 0)
        self.assertEqual(sources.SOURCES["web_backfill"]["surface"], "web")
        self.assertIn("DATAFORSEO_LOGIN", sources.SOURCES["web_backfill"]["needs"])


if __name__ == "__main__":
    unittest.main()
