"""The five concrete write clients (build plan §5 / P3.1).

Each declares its platform id, the per-tenant credential keys that switch it out
of mock mode, and the verb subset it actually supports. Meta has a live Graph
API transport (§D.2, in ``meta_transport``); the rest still fall through to the
dry-run / mock behaviour in ``base`` until their transports are wired.
"""
from .. import google_oauth
from .base import WriteClient
from . import (google_reviews_transport, linkedin_write_transport, meta_transport,
               x_transport, youtube_write_transport)


def _google_token(keys, static_key):
    """A static override always wins; otherwise mint one from the refresh
    token (Google access tokens expire in ~1hr, so a stored copy would go
    stale — mint fresh on every call instead)."""
    return keys.get(static_key) or google_oauth.mint_access_token(keys)


class MetaWriteClient(WriteClient):
    PLATFORM = "meta"
    CRED_KEYS = ("META_ACCESS_TOKEN", "META_PAGE_ID")
    SUPPORTED = ("reply_public", "reply_dm", "publish", "schedule",
                 "delete_reply", "block", "unblock")

    def _endpoint(self, action, target_ref):
        try:
            method, url, _ = meta_transport.build_request(
                action, target_ref, {}, page_id=self.k.get("META_PAGE_ID"),
                ig_user_id=self.k.get("META_IG_USER_ID"))
            return f"{method} {url}"
        except Exception:                                     # noqa: BLE001
            return None

    def _live(self, action, target_ref, request):
        request = request or {}
        ig_login_token = self.k.get("INSTAGRAM_LOGIN_ACCESS_TOKEN")
        is_ig_dm = action == "reply_dm" and request.get("channel") == "instagram_dm"
        if is_ig_dm and ig_login_token:
            # Preferred route for Instagram DMs -- see meta_transport's
            # build_instagram_login_dm docstring. No Page-token exchange:
            # the Instagram-Login token is already scoped to the IG account.
            method, url, payload = meta_transport.build_instagram_login_dm(
                target_ref, request, ig_user_id=self.k.get("META_IG_USER_ID"))
            return meta_transport.call(method, url, payload, ig_login_token)
        method, url, payload = meta_transport.build_request(
            action, target_ref, request, page_id=self.k["META_PAGE_ID"],
            ig_user_id=self.k.get("META_IG_USER_ID"))
        # Every one of these verbs writes as the Page, not the person --
        # Graph rejects (Messenger/IG Send API) or silently misbehaves
        # (comment replies) on a plain user token. Root-caused 2026-09-11.
        token = meta_transport.resolve_page_token(self.k)
        return meta_transport.call(method, url, payload, token)


class XWriteClient(WriteClient):
    PLATFORM = "x"
    CRED_KEYS = ("X_WRITE_TOKEN",)
    SUPPORTED = ("reply_public", "reply_dm", "publish", "delete_reply",
                 "block", "unblock")

    def _endpoint(self, action, target_ref):
        try:
            method, url, _ = x_transport.build_request(
                action, target_ref, {}, source_user_id="me")
            return f"{method} {url}"
        except Exception:                                     # noqa: BLE001
            return None

    def _live(self, action, target_ref, request):
        token = self.k["X_WRITE_TOKEN"]
        src = None
        if action in ("block", "unblock"):
            src = self.k.get("X_OWNED_USER_ID") or x_transport.resolve_me(token)
        method, url, payload = x_transport.build_request(
            action, target_ref, request, source_user_id=src)
        return x_transport.call(method, url, payload, token)


class LinkedInWriteClient(WriteClient):
    PLATFORM = "linkedin"
    CRED_KEYS = ("LINKEDIN_ACCESS_TOKEN", "LINKEDIN_ORG_URN")
    SUPPORTED = ("reply_public", "publish", "delete_reply")

    def _endpoint(self, action, target_ref):
        try:
            method, url, _ = linkedin_write_transport.build_request(
                action, target_ref or "urn:li:share:0", {},
                org_urn=self.k.get("LINKEDIN_ORG_URN"))
            return f"{method} {url}"
        except Exception:                                     # noqa: BLE001
            return None

    def _live(self, action, target_ref, request):
        method, url, payload = linkedin_write_transport.build_request(
            action, target_ref, request, org_urn=self.k["LINKEDIN_ORG_URN"])
        return linkedin_write_transport.call(
            method, url, payload, self.k["LINKEDIN_ACCESS_TOKEN"],
            version=self.k.get("LINKEDIN_API_VERSION")
            or linkedin_write_transport.DEFAULT_VERSION)


class GoogleReviewsWriteClient(WriteClient):
    PLATFORM = "google_reviews"
    CRED_KEYS = ("GOOGLE_BUSINESS_TOKEN",)
    # a review only gets a reply; Google can reject it after submission
    SUPPORTED = ("reply_public", "delete_reply")

    def _cred_ok(self):
        return bool(self.k.get("GOOGLE_BUSINESS_TOKEN")) or google_oauth.has_refresh_creds(self.k)

    def _endpoint(self, action, target_ref):
        try:
            method, url, _ = google_reviews_transport.build_request(
                action, target_ref or "accounts/a/locations/l/reviews/r", {})
            return f"{method} {url}"
        except Exception:                                     # noqa: BLE001
            return None

    def _live(self, action, target_ref, request):
        method, url, payload = google_reviews_transport.build_request(
            action, target_ref, request)
        return google_reviews_transport.call(
            method, url, payload, _google_token(self.k, "GOOGLE_BUSINESS_TOKEN"),
            review_name=str(target_ref).strip("/"))


class YouTubeWriteClient(WriteClient):
    PLATFORM = "youtube"
    CRED_KEYS = ("YOUTUBE_OAUTH_TOKEN",)
    SUPPORTED = ("reply_public", "publish", "delete_reply")

    def _cred_ok(self):
        return bool(self.k.get("YOUTUBE_OAUTH_TOKEN")) or google_oauth.has_refresh_creds(self.k)

    def _endpoint(self, action, target_ref):
        try:
            method, url, _ = youtube_write_transport.build_request(
                action, target_ref or "vid", {})
            return f"{method} {url}"
        except Exception:                                     # noqa: BLE001
            return None

    def _live(self, action, target_ref, request):
        method, url, payload = youtube_write_transport.build_request(
            action, target_ref, request)
        return youtube_write_transport.call(
            method, url, payload, _google_token(self.k, "YOUTUBE_OAUTH_TOKEN"))


CLIENTS = {
    "meta": MetaWriteClient,
    "x": XWriteClient,
    "linkedin": LinkedInWriteClient,
    "google_reviews": GoogleReviewsWriteClient,
    "youtube": YouTubeWriteClient,
}

# Read-side surfaces (core/sources.py, ChannelBadge's CHANNEL_META) label
# Facebook and Instagram as distinct sources because they're collected
# separately; on the write side both go through the same Meta Graph API and
# Page/token credentials, so both resolve to the one client here. Found via
# F7.5's reply-send interaction test 500ing on any facebook-channel case.
_ALIASES = {"facebook": "meta", "instagram": "meta"}


def client_for(platform: str, keys: dict, **kw) -> WriteClient:
    platform = _ALIASES.get(platform, platform)
    try:
        return CLIENTS[platform](keys, **kw)
    except KeyError:
        raise ValueError(f"unknown write platform: {platform!r}")
