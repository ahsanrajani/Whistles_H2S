"""Multi-app support for the store-review adapters: id-list parsing and the
free, best-effort name + icon lookup that lets the UI show which app a review
belongs to. A failed lookup returns ``{}`` -- the review is still collected,
it just has no icon (never a guessed one)."""
import html
import json
import re

from core import collector

_SPLIT = re.compile(r"[,\s;]+")
_META = re.compile(r'<meta[^>]+property="og:(title|image)"[^>]+content="([^"]*)"', re.I)


def parse_ids(value):
    """'a b, c' -> ['a', 'b', 'c'] (order kept, duplicates dropped). One id
    still works exactly as before."""
    seen = []
    for part in _SPLIT.split(value or ""):
        if part and part not in seen:
            seen.append(part)
    return seen


def appstore(app_id, country="pk"):
    """{'name', 'icon'} from Apple's free iTunes lookup, or {}."""
    try:
        res = json.loads(collector._get(
            f"https://itunes.apple.com/lookup?id={app_id}&country={country}", timeout=20))
        hit = (res.get("results") or [{}])[0]
        icon = hit.get("artworkUrl100") or hit.get("artworkUrl60")
        return {"name": hit.get("trackName"), "icon": icon} if icon or hit.get("trackName") else {}
    except Exception:                                            # noqa: BLE001
        return {}


def playstore(app_id, country="pk"):
    """{'name', 'icon'} scraped from the public listing's og: tags, or {}."""
    try:
        page = collector._get(
            f"https://play.google.com/store/apps/details?id={app_id}&hl=en&gl={country}",
            timeout=20, headers={"Accept-Language": "en-US,en;q=0.9"}).decode("utf-8", "replace")
        tags = {k.lower(): html.unescape(v) for k, v in _META.findall(page)}
        name = re.sub(r"\s+-\s+Apps on Google Play$", "", tags.get("title", "")) or None
        icon = re.sub(r"=s\d+.*$", "=s64", tags["image"]) if tags.get("image") else None
        return {"name": name, "icon": icon} if icon or name else {}
    except Exception:                                            # noqa: BLE001
        return {}


def app_raw(app_id, meta):
    """The identifying fields stored on each review's ``raw``."""
    return {"app_id": app_id, "app_name": meta.get("name"), "app_icon": meta.get("icon")}
