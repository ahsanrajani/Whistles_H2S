"""LinkedIn organization owned-analytics facts (§D.3).

Account-grain daily numbers for a company Page via the LinkedIn Marketing API:
one day of ``organizationalEntityShareStatistics`` plus the follower count from
``networkSizes``. ``map_day`` is pure; ``fetch_day`` makes the two GETs.

Dormant until ``LINKEDIN_ACCESS_TOKEN`` + ``LINKEDIN_ORG_URN`` are set (and
``GURU_WRITE_LIVE`` on).
"""
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, time, timezone

from .base import OwnedAnalyticsError

REST = "https://api.linkedin.com/rest"
_TIMEOUT = 20
DEFAULT_VERSION = "202405"


def _ms(d) -> int:
    return int(datetime.combine(d, time.min, tzinfo=timezone.utc).timestamp() * 1000)


def _get(url, token, version):
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "LinkedIn-Version": version,
        "X-Restli-Protocol-Version": "2.0.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise OwnedAnalyticsError(f"linkedin {exc.code}: {detail[:300]}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise OwnedAnalyticsError(f"linkedin unreachable: {exc}") from exc


def map_day(stats, followers, day) -> list[dict]:
    """``stats`` = a ``totalShareStatistics`` dict for the day; ``followers`` =
    an int or None. Pure."""
    facts: list[dict] = []
    stats = stats or {}
    impressions = stats.get("impressionCount")
    reach = stats.get("uniqueImpressionsCount")
    engagements = sum(int(stats.get(k, 0)) for k in
                      ("likeCount", "commentCount", "shareCount", "clickCount"))

    if impressions is not None:
        facts.append({"source": "linkedin", "entity_type": "org", "entity_ref": "self",
                      "metric": "impressions", "day": day, "value": float(impressions)})
    if reach is not None:
        facts.append({"source": "linkedin", "entity_type": "org", "entity_ref": "self",
                      "metric": "reach", "day": day, "value": float(reach)})
    facts.append({"source": "linkedin", "entity_type": "org", "entity_ref": "self",
                  "metric": "engagements", "day": day, "value": float(engagements)})
    if impressions:
        facts.append({"source": "linkedin", "entity_type": "org", "entity_ref": "self",
                      "metric": "engagement_rate", "day": day,
                      "value": engagements / impressions,
                      "numerator": float(engagements), "denominator": float(impressions)})
    if followers is not None:
        facts.append({"source": "linkedin", "entity_type": "org", "entity_ref": "self",
                      "metric": "followers", "day": day, "value": float(followers)})
    return facts


def _day_stats(payload, day):
    """Pick the element whose interval starts on ``day`` from a DAY-granular
    ``organizationalEntityShareStatistics`` response; fall back to the top-level
    ``totalShareStatistics`` when the response isn't interval-split."""
    start_ms = _ms(day)
    for el in (payload or {}).get("elements", []):
        tr = el.get("timeRange") or {}
        if tr.get("start") == start_ms:
            return el.get("totalShareStatistics")
    els = (payload or {}).get("elements") or []
    if len(els) == 1:
        return els[0].get("totalShareStatistics")
    return (payload or {}).get("totalShareStatistics")


def fetch_day(org_urn, day, token, version=DEFAULT_VERSION) -> list[dict]:
    start, end = _ms(day), _ms(day) + 86_400_000
    q = urllib.parse.quote(org_urn, safe="")
    stats_url = (
        f"{REST}/organizationalEntityShareStatistics?q=organizationalEntity"
        f"&organizationalEntity={q}"
        f"&timeIntervals.timeGranularityType=DAY"
        f"&timeIntervals.timeRange.start={start}"
        f"&timeIntervals.timeRange.end={end}")
    stats = _day_stats(_get(stats_url, token, version), day)

    followers = None
    net = _get(f"{REST}/networkSizes/{q}?edgeType=CompanyFollowedByMember",
               token, version)
    if isinstance(net, dict) and net.get("firstDegreeSize") is not None:
        followers = net["firstDegreeSize"]

    return map_day(stats, followers, day)
