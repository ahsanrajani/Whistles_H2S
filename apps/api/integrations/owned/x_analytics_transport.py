"""X (Twitter) owned-analytics facts (§D.3).

Account-grain daily numbers for an owned X account, from the v2 API with the
app-only bearer token: followers from the user object, and impressions /
engagements aggregated over the account's own tweets created that day.
``impression_count`` is only present for some tokens/tiers — when it is absent
the impressions metric (and the engagement-rate proportion) are simply omitted.
"""
import json
import urllib.error
import urllib.request
from datetime import datetime, time, timezone

from .base import OwnedAnalyticsError

API = "https://api.twitter.com/2"
_TIMEOUT = 20
_ENGAGE = ("retweet_count", "reply_count", "like_count", "quote_count")


def _get(url, token):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            payload = json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise OwnedAnalyticsError(f"x api {exc.code}: {detail[:300]}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise OwnedAnalyticsError(f"x api unreachable: {exc}") from exc
    if isinstance(payload, dict) and payload.get("errors") and "data" not in payload:
        raise OwnedAnalyticsError(f"x api: {payload['errors'][0].get('detail') or payload['errors']}")
    return payload


def _media_type(tweet, media_map) -> str:
    keys = ((tweet.get("attachments") or {}).get("media_keys")) or []
    for k in keys:
        t = (media_map or {}).get(k)
        if t:
            return {"animated_gif": "video"}.get(t, t)
    return "media" if keys else "text"


def map_day(user_metrics, tweets, day, media_map=None) -> list[dict]:
    """``user_metrics`` = the user object's ``public_metrics``; ``tweets`` = the
    list of that day's tweet objects; ``media_map`` = ``{media_key: type}`` from
    the response ``includes``. Emits the account-grain totals and one post-grain
    row set per tweet. Pure."""
    facts: list[dict] = []
    followers = (user_metrics or {}).get("followers_count")
    if followers is not None:
        facts.append({"source": "x", "entity_type": "account", "entity_ref": "self",
                      "metric": "followers", "day": day, "value": float(followers)})

    engagements = 0
    impressions = 0
    have_impressions = False
    for tw in tweets or []:
        pm = tw.get("public_metrics") or {}
        eng = sum(int(pm.get(k, 0)) for k in _ENGAGE)
        engagements += eng
        impr = int(pm["impression_count"]) if "impression_count" in pm else None
        if impr is not None:
            have_impressions = True
            impressions += impr

        ref, mt = tw.get("id"), _media_type(tw, media_map)
        if not ref:
            continue
        dims = {"media_type": mt}
        facts.append({"source": "x", "entity_type": "post", "entity_ref": ref,
                      "metric": "engagements", "day": day, "value": float(eng),
                      "dims": dims})
        facts.append({"source": "x", "entity_type": "post", "entity_ref": ref,
                      "metric": "reactions", "day": day,
                      "value": float(pm.get("like_count", 0)), "dims": dims})
        if impr is not None:
            facts.append({"source": "x", "entity_type": "post", "entity_ref": ref,
                          "metric": "impressions", "day": day, "value": float(impr),
                          "dims": dims})
            facts.append({"source": "x", "entity_type": "post", "entity_ref": ref,
                          "metric": "engagement_rate", "day": day,
                          "value": (eng / impr) if impr else None,
                          "numerator": float(eng), "denominator": float(impr),
                          "dims": dims})

    facts.append({"source": "x", "entity_type": "account", "entity_ref": "self",
                  "metric": "engagements", "day": day, "value": float(engagements)})
    if have_impressions:
        facts.append({"source": "x", "entity_type": "account", "entity_ref": "self",
                      "metric": "impressions", "day": day, "value": float(impressions)})
        facts.append({"source": "x", "entity_type": "account", "entity_ref": "self",
                      "metric": "engagement_rate", "day": day,
                      "value": (engagements / impressions) if impressions else None,
                      "numerator": float(engagements), "denominator": float(impressions)})
    return facts


def fetch_day(handle, day, token) -> list[dict]:
    handle = handle.lstrip("@")
    user = _get(f"{API}/users/by/username/{handle}?user.fields=public_metrics", token)
    data = user.get("data") or {}
    uid = data.get("id")
    if not uid:
        raise OwnedAnalyticsError(f"x api: no such user @{handle}")

    start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    end = datetime.fromtimestamp(start.timestamp() + 86400, tz=timezone.utc)
    url = (f"{API}/users/{uid}/tweets?max_results=100"
           f"&start_time={start.strftime('%Y-%m-%dT%H:%M:%SZ')}"
           f"&end_time={end.strftime('%Y-%m-%dT%H:%M:%SZ')}"
           f"&tweet.fields=public_metrics,created_at,attachments"
           f"&expansions=attachments.media_keys&media.fields=type")
    resp = _get(url, token)
    tweets = resp.get("data") or []
    media_map = {m.get("media_key"): m.get("type")
                 for m in (resp.get("includes") or {}).get("media") or []}
    return map_day(data.get("public_metrics"), tweets, day, media_map)
