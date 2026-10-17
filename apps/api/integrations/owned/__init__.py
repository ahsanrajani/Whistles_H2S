"""Owned-analytics ingestion (build plan §6 / P4.1).

Providers pull daily metrics from the surfaces a tenant owns (Meta / Instagram
/ X / LinkedIn) into the ``metric_fact`` warehouse. Mirrors the shape of
``integrations/write/``: a base class, concrete platform classes, a
``provider_for`` factory, all working in mock mode until live transport is
wired at deploy.
"""
from .base import OwnedAnalyticsError, OwnedAnalyticsProvider
from .providers import (InstagramInsights, LinkedInAnalytics, MetaInsights,
                        PROVIDERS, XAnalytics, provider_for)

__all__ = ["OwnedAnalyticsProvider", "OwnedAnalyticsError", "MetaInsights",
           "InstagramInsights", "XAnalytics", "LinkedInAnalytics", "PROVIDERS",
           "provider_for"]
