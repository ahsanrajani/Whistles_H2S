"""Analytics query layer — the aggregation SQL behind the insight surfaces.

One module per ``core/insights`` surface (plus the standalone scanners in
P1.2d). Each function takes a ``Session`` and returns raw rows; the Python
shaping stays in ``core``.
"""
from . import (calibration, competitors, cost, dashboards, evidence, kpis,
               overview, reviews, scanners, sentiment, themes, trends)

__all__ = ["competitors", "sentiment", "reviews", "trends", "calibration",
           "cost", "dashboards", "evidence", "kpis", "overview", "themes",
           "scanners"]
