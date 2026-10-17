"""The four concrete owned-analytics providers (build plan §6 / P4.1).

Each declares its platform id, the per-tenant credential keys that leave mock
mode, the account-grain (entity_type, metric) pairs it reports daily, and the
media types its posts come in. Request building + live transport are a
deployment step.
"""
from .base import OwnedAnalyticsProvider


class MetaInsights(OwnedAnalyticsProvider):
    PLATFORM = "meta"
    CRED_KEYS = ("META_ACCESS_TOKEN", "META_PAGE_ID")
    ENTITY_TYPE = "page"
    ACCOUNT_METRICS = (
        ("page", "impressions"), ("page", "reach"),
        ("page", "engagements"), ("page", "followers"),
    )
    POST_MEDIA_TYPES = ("image", "video", "link", "status")

    def _live(self, workspace_id, day):
        """Account-grain Page Insights for one day (§D.3). Post-grain stays on
        the empty path until its own packet."""
        from . import meta_insights_transport as t
        return t.fetch_day(self.k["META_PAGE_ID"], day, self.k["META_ACCESS_TOKEN"])


class InstagramInsights(OwnedAnalyticsProvider):
    PLATFORM = "instagram"
    CRED_KEYS = ("META_ACCESS_TOKEN", "META_IG_USER_ID")
    ENTITY_TYPE = "account"
    ACCOUNT_METRICS = (
        ("account", "impressions"), ("account", "reach"),
        ("account", "followers"), ("account", "profile_visits"),
    )
    POST_MEDIA_TYPES = ("image", "video", "reel", "carousel", "story")

    def _live(self, workspace_id, day):
        from . import instagram_insights_transport as t
        return t.fetch_day(self.k["META_IG_USER_ID"], day, self.k["META_ACCESS_TOKEN"])


class XAnalytics(OwnedAnalyticsProvider):
    PLATFORM = "x"
    CRED_KEYS = ("X_BEARER_TOKEN", "X_OWNED_HANDLE")
    ENTITY_TYPE = "account"
    ACCOUNT_METRICS = (
        ("account", "impressions"), ("account", "engagements"),
        ("account", "followers"), ("account", "profile_visits"),
    )
    POST_MEDIA_TYPES = ("text", "photo", "video", "link")

    def _live(self, workspace_id, day):
        from . import x_analytics_transport as t
        return t.fetch_day(self.k["X_OWNED_HANDLE"], day, self.k["X_BEARER_TOKEN"])


class LinkedInAnalytics(OwnedAnalyticsProvider):
    PLATFORM = "linkedin"
    CRED_KEYS = ("LINKEDIN_ACCESS_TOKEN", "LINKEDIN_ORG_URN")
    ENTITY_TYPE = "org"
    ACCOUNT_METRICS = (
        ("org", "impressions"), ("org", "reach"),
        ("org", "engagements"), ("org", "followers"),
    )
    POST_MEDIA_TYPES = ("text", "image", "video", "article", "document")

    def _live(self, workspace_id, day):
        from . import linkedin_analytics_transport as t
        return t.fetch_day(
            self.k["LINKEDIN_ORG_URN"], day, self.k["LINKEDIN_ACCESS_TOKEN"],
            version=self.k.get("LINKEDIN_API_VERSION") or t.DEFAULT_VERSION)


PROVIDERS = {
    p.PLATFORM: p for p in
    (MetaInsights, InstagramInsights, XAnalytics, LinkedInAnalytics)
}


def provider_for(platform: str, keys: dict | None = None, **kw) -> OwnedAnalyticsProvider:
    try:
        return PROVIDERS[platform](keys, **kw)
    except KeyError:
        raise ValueError(f"unknown owned-analytics platform: {platform!r}")
