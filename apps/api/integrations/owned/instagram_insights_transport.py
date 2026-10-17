"""Instagram Insights -> owned-analytics facts (§D.3).

Account-grain daily metrics for an Instagram Business account, via the same
Graph API host and Page token as Facebook. ``map_account``/``map_media`` are
pure; ``fetch_day`` does the account-insights, media-list and per-media-insights
round-trips.
"""
import json
import urllib.error
import urllib.request

from .base import OwnedAnalyticsError
from .meta_insights_transport import GRAPH, _TIMEOUT, _epoch

# IG insight metric name -> (entity_type, our metric name). ``impressions``
# and ``engagement`` are no longer valid (Graph API v22+ dropped impressions
# for media; ``engagement`` was replaced by ``total_interactions``);
# ``profile_views``/website_clicks/etc. need ``metric_type=total_value`` and
# return a different payload shape, so they're left out here rather than
# mixing two response shapes in one call -- confirmed empirically against
# Peekaboo's IG account 2026-09-16.
_ACCOUNT = {
    "reach": ("account", "reach"),
    "follower_count": ("account", "followers"),
}
_METRIC_PARAM = ",".join(_ACCOUNT)

# IG media insight name -> our metric
_POST = {"reach": "reach", "total_interactions": "engagements", "likes": "likes",
          "comments": "comments", "saved": "saves", "shares": "shares"}
_POST_PARAM = ",".join(_POST)
_MEDIA = {"IMAGE": "image", "VIDEO": "video", "CAROUSEL_ALBUM": "carousel",
          "REELS": "reel", "REEL": "reel"}
_MAX_POSTS = 25


def _one_get(url, token):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            payload = json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise OwnedAnalyticsError(f"instagram insights {exc.code}: {detail[:300]}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise OwnedAnalyticsError(f"instagram insights unreachable: {exc}") from exc
    if isinstance(payload, dict) and payload.get("error"):
        raise OwnedAnalyticsError(f"instagram insights: {payload['error'].get('message')}")
    return payload


def map_media(payload, media_id, media_type, day) -> list[dict]:
    dims = {"media_type": media_type}
    got: dict = {}
    for row in (payload or {}).get("data", []):
        m = _POST.get(row.get("name"))
        val = (row.get("values") or [{}])[-1].get("value")
        if m and val is not None:
            got[m] = float(val)
    return [{"source": "instagram", "entity_type": "post", "entity_ref": media_id,
             "metric": m, "day": day, "value": v, "dims": dims}
            for m, v in got.items()]


def map_account(payload, day) -> list[dict]:
    facts: list[dict] = []
    for row in (payload or {}).get("data", []):
        spec = _ACCOUNT.get(row.get("name"))
        if not spec:
            continue
        values = row.get("values") or [{}]
        val = values[-1].get("value")
        if val is None:
            continue
        et, m = spec
        facts.append({"source": "instagram", "entity_type": et,
                      "entity_ref": "self", "metric": m, "day": day,
                      "value": float(val)})
    return facts


def fetch_day(ig_user_id, day, token) -> list[dict]:
    since, until = _epoch(day), _epoch(day) + 86400
    facts = map_account(_one_get(
        f"{GRAPH}/{ig_user_id}/insights?metric={_METRIC_PARAM}"
        f"&period=day&since={since}&until={until}", token), day)

    media = _one_get(
        f"{GRAPH}/{ig_user_id}/media?fields=id,media_type,timestamp"
        f"&since={since}&until={until}&limit={_MAX_POSTS}", token).get("data") or []
    for m in media[:_MAX_POSTS]:
        mid = m.get("id")
        if not mid:
            continue
        mt = _MEDIA.get((m.get("media_type") or "").upper(), "image")
        try:
            mi = _one_get(f"{GRAPH}/{mid}/insights?metric={_POST_PARAM}", token)
        except OwnedAnalyticsError:
            continue
        facts.extend(map_media(mi, mid, mt, day))
    return facts
