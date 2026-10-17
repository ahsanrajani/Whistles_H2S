"""Bright Data SERP adapters — X and Reddit keyword discovery.

Parallel to ``DataForSEOSerp``: one ``site:`` Google query per brand term
through Bright Data's SERP API (``api.brightdata.com/request`` with
``brd_json=1``), organic results filtered to the platform's hosts become items
on the ``x`` / ``reddit`` surface. Uses the existing ``BRIGHT_DATA_API_KEY``
plus a SERP zone name — no dataset id.
"""
import json
import re
import urllib.parse

from core import collector

_ENDPOINT = "https://api.brightdata.com/request"


def _organic(raw) -> list:
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return []
    if isinstance(data, str):                       # brd_json can double-encode
        try:
            data = json.loads(data)
        except (ValueError, TypeError):
            return []
    if isinstance(data, dict):
        return data.get("organic") or data.get("organic_results") or []
    return []


def _domain(url: str):
    try:
        return re.sub(r"^www\.", "", urllib.parse.urlparse(url).netloc.lower()) or None
    except ValueError:
        return None


class BrightDataSerp(collector.Adapter):
    QUERY_PREFIX = ""
    HOSTS: tuple[str, ...] = ()
    MAX_TERMS = 3
    DEPTH = 10

    def _search_urls(self, terms):
        for term in [t for t in terms if t][:self.MAX_TERMS]:
            q = f"{self.QUERY_PREFIX}{term}".strip()
            params = urllib.parse.urlencode({"q": q, "num": self.DEPTH})
            yield term, f"https://www.google.com/search?{params}&brd_json=1"

    def _on_surface(self, link: str) -> bool:
        return bool(link) and any(h in link for h in self.HOSTS)

    def fetch(self, terms):
        token = (self.k.get("BRIGHT_DATA_API_KEY") or "").strip()
        zone = (self.k.get("BRIGHT_DATA_SERP_ZONE") or "").strip()
        if not token or not zone:
            return
        hdr = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        for term, url in self._search_urls(terms):
            self.throttle()
            body = json.dumps({"zone": zone, "url": url, "format": "raw"}).encode()
            try:
                raw = collector._get(_ENDPOINT, data=body, headers=hdr, timeout=90)
                self.count(self.ID, calls=1)
            except Exception as e:                          # noqa: BLE001
                self.count(self.ID, ok=False)
                self.log(f"brightdata serp · {term[:40]} failed ({e})")
                continue
            results = _organic(raw)
            kept = 0
            for item in results:
                link = item.get("link") or item.get("url")
                if not self._on_surface(link):
                    continue
                title = (item.get("title") or "").strip()
                snippet = (item.get("description") or item.get("snippet") or "").strip()
                kept += 1
                yield {
                    "external_id": collector._h(link),
                    "url": link,
                    "outlet": _domain(link),
                    "author": _domain(link),
                    "published_at": None,
                    "title": title,
                    "body": (f"{title} {snippet}").strip(),
                    "raw": {"rank": item.get("rank") or item.get("rank_absolute"),
                            "via": "brightdata_serp", "query": term},
                }
            self.log(f"brightdata serp · {term[:40]} · {kept}/{len(results)} on-surface")


class BrightDataSerpX(BrightDataSerp):
    ID = "brightdata_serp_x"
    QUERY_PREFIX = "site:x.com OR site:twitter.com "
    HOSTS = ("x.com/", "twitter.com/")


class BrightDataSerpReddit(BrightDataSerp):
    ID = "brightdata_serp_reddit"
    QUERY_PREFIX = "site:reddit.com "
    HOSTS = ("reddit.com/",)
