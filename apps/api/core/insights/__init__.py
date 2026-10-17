"""Insights.

The rule for everything here: an insight is only worth showing if it survives
its own uncertainty. Anything that would flip on a handful of items gets
returned with the caveat attached, not stripped of it.

This package was split out of a single `core/insights.py` (P0.2). The surfaces
now live one-per-module; this file re-exports every public name (and the few
helpers other modules import by name) so `from core import insights` and
`insights.<name>` keep working unchanged.
"""
from .calibration import (CALIBRATION_TARGET, calibration_status, exclusions,
                          review_batch, rule_precision)
from .common import (PERIOD_LABELS, PERIODS, SAFE_SQL, _age_days, _day_bucket,
                     _iso_weeks, _pct_delta, _poly, _split_window)
from .competitors import (indistinguishable_pairs, outlet_gap, share_of_voice,
                          top_outlets)
from .cost import cost
from .evidence import evidence, feed
from .kpis import deltas, kpis
from .overview import (action_cards, headline, language_mix, mention_mix,
                       surface_ledger, top_authors)
from .reviews import app_reviews, rating_timeline, review_trend
from .sentiment import gauge, sentiment_breakdown, sentiment_trend
from .themes import STOPWORDS, themes
from .trends import peak_hours, press_volume, timeline

__all__ = [
    "SAFE_SQL", "PERIODS", "PERIOD_LABELS", "CALIBRATION_TARGET", "STOPWORDS",
    "share_of_voice", "indistinguishable_pairs", "outlet_gap", "top_outlets",
    "sentiment_breakdown", "gauge", "sentiment_trend",
    "app_reviews", "review_trend", "rating_timeline",
    "timeline", "press_volume", "peak_hours",
    "rule_precision", "calibration_status", "review_batch", "exclusions",
    "themes", "feed", "evidence", "deltas", "kpis", "cost",
    "surface_ledger", "language_mix", "top_authors", "mention_mix", "headline",
    "action_cards",
    # helpers imported by name elsewhere in core/
    "_day_bucket", "_age_days", "_split_window", "_pct_delta",
    "_iso_weeks", "_poly",
]
