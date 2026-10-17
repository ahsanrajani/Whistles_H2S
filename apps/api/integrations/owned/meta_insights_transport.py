"""Meta Page Insights -> owned-analytics facts (§D.3).

Account-grain daily metrics for a Facebook Page. ``map_account`` is pure and
unit-tested; ``fetch_day`` is the one urllib round-trip. Post-grain scorecards
stay on the mock/empty path for now.
"""
import json
import urllib.error
import urllib.request
from datetime import datetime, time, timezone

from .base import OwnedAnalyticsError

GRAPH = "https://graph.facebook.com/v21.0"
_TIMEOUT = 20

# Graph metric name -> (entity_type, our metric name). page_impressions*,
# page_fans and page_engaged_users are deprecated on current Graph API
# versions ("(#100) The value must be a valid insights metric") -- confirmed
# empirically against Peekaboo's Page 2026-09-16; page_follows replaces
# page_fans, there is no surviving reach/impressions metric for Pages.
_ACCOUNT = {
    "page_post_engagements": ("page", "engagements"),
    "page_follows": ("page", "followers"),
    "page_views_total": ("page", "page_views"),
    "page_actions_post_reactions_total": ("page", "reactions"),
}
_METRIC_PARAM = ",".join(_ACCOUNT)


def _epoch(d) -> int:
    return int(datetime.combine(d, time.min, tzinfo=timezone.utc).timestamp())


def map_account(payload, day) -> list[dict]:
    """A Graph insights ``data`` list -> owned-analytics fact dicts, plus the
    engagement-rate proportion carrying its raw counts (for P4.2's Wilson)."""
    got: dict = {}
    for row in (payload or {}).get("data", []):
        spec = _ACCOUNT.get(row.get("name"))
        if not spec:
            continue
        values = row.get("values") or [{}]
        val = values[-1].get("value")
        if isinstance(val, dict):                       # e.g. reactions-by-type breakdown
            val = sum(int(v) for v in val.values()) if val else None
        if val is None:
            continue
        got[spec] = float(val)

    return [
        {"source": "meta", "entity_type": et, "entity_ref": "self",
         "metric": m, "day": day, "value": v}
        for (et, m), v in got.items()
    ]


# post_impressions*/post_engaged_users are likewise deprecated; post_clicks
# and post_video_views survive (video_views is harmless -- 0 -- on a non-video
# post, confirmed empirically).
_POST = {
    "post_clicks": ("post", "clicks"),
    "post_video_views": ("post", "video_views"),
}
_POST_PARAM = ",".join((*_POST, "post_reactions_by_type_total"))
_MEDIA = {"photo": "image", "share": "link", "status": "status", "video": "video",
          "album": "carousel", "link": "link", "event": "event"}
_MAX_POSTS = 25


def _get(url, token):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            payload = json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise OwnedAnalyticsError(f"meta insights {exc.code}: {detail[:300]}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise OwnedAnalyticsError(f"meta insights unreachable: {exc}") from exc
    if isinstance(payload, dict) and payload.get("error"):
        raise OwnedAnalyticsError(f"meta insights: {payload['error'].get('message')}")
    return payload


def map_post(payload, post_id, media_type, day) -> list[dict]:
    got: dict = {}
    reactions = None
    for row in (payload or {}).get("data", []):
        name = row.get("name")
        val = (row.get("values") or [{}])[-1].get("value")
        if name == "post_reactions_by_type_total" and isinstance(val, dict):
            reactions = float(sum(int(v) for v in val.values()))
        elif name in _POST and val is not None:
            got[_POST[name]] = float(val)

    dims = {"media_type": media_type}
    facts = [{"source": "meta", "entity_type": et, "entity_ref": post_id,
              "metric": m, "day": day, "value": v, "dims": dims}
             for (et, m), v in got.items()]
    if reactions is not None:
        facts.append({"source": "meta", "entity_type": "post", "entity_ref": post_id,
                      "metric": "reactions", "day": day, "value": reactions, "dims": dims})
    return facts


def _post_media(post) -> str:
    for att in ((post.get("attachments") or {}).get("data") or []):
        mt = att.get("media_type")
        if mt:
            return _MEDIA.get(mt.lower(), mt.lower())
    return "status"


def _resolve_page_token(page_id, token):
    """Meta's "new Pages experience" rejects a user/system-user token on
    Page insights calls ("must be called with a Page Access Token") --
    exchange it for the Page-scoped token via /me/accounts, matched on
    page_id. Own copy, same pattern as adapters.meta.MetaBase._page_token
    and write.meta_transport.resolve_page_token -- read and write sides
    intentionally don't share this helper."""
    data = _get(f"{GRAPH}/me/accounts", token)
    for acct in data.get("data") or []:
        if str(acct.get("id")) == str(page_id) and acct.get("access_token"):
            return acct["access_token"]
    raise OwnedAnalyticsError(f"meta insights: no page-scoped token for page_id={page_id}")


def fetch_day(page_id, day, token) -> list[dict]:
    page_token = _resolve_page_token(page_id, token)
    since, until = _epoch(day), _epoch(day) + 86400
    facts = map_account(_get(
        f"{GRAPH}/{page_id}/insights?metric={_METRIC_PARAM}"
        f"&period=day&since={since}&until={until}", page_token), day)

    posts = _get(
        f"{GRAPH}/{page_id}/posts?fields=id,attachments{{media_type}}"
        f"&since={since}&until={until}&limit={_MAX_POSTS}", page_token).get("data") or []
    for post in posts[:_MAX_POSTS]:
        pid = post.get("id")
        if not pid:
            continue
        try:
            pi = _get(f"{GRAPH}/{pid}/insights?metric={_POST_PARAM}", page_token)
        except OwnedAnalyticsError:
            continue                                # one bad post must not sink the day
        facts.extend(map_post(pi, pid, _post_media(post), day))
    return facts
