"""News-wire adapters — Google News RSS search and the regulatory-notice feed.

Shared primitives (`Adapter`, `_get`, `_h`, `_news_query_feed`, `_gnews_outlet`)
come from `core.collector`; referencing them through the module keeps the
`@patch("core.collector.*")` seams the tests rely on intact.
"""
import time
import urllib.parse
import xml.etree.ElementTree as ET

from core import collector


class GoogleNews(collector.Adapter):
    ID = "googlenews_rss"

    def fetch(self, terms):
        for term in terms:
            url = ("https://news.google.com/rss/search?q="
                   + urllib.parse.quote(f'"{term}"') + "&hl=en-PK&gl=PK&ceid=PK:en")
            try:
                root = ET.fromstring(collector._get(url))
                self.count(self.ID)
            except Exception as e:
                self.count(self.ID, ok=False)
                self.log(f"googlenews: {term} failed — {e}")
                continue
            n = 0
            for it in root.findall(".//item"):
                title = (it.findtext("title") or "").strip()
                link = (it.findtext("link") or "").strip()
                outlet = None
                for s in it:
                    if s.tag.endswith("source"):
                        outlet = (s.text or "").strip()
                # Google News appends " - Outlet" to titles; that suffix is the
                # only reliable publisher signal when <source> is absent.
                if not outlet and " - " in title:
                    outlet = title.rsplit(" - ", 1)[1].strip()
                    title = title.rsplit(" - ", 1)[0].strip()
                if outlet:
                    outlet = outlet.strip(" |-–—·").strip()
                n += 1
                yield {"external_id": collector._h(title, link), "url": link,
                       "outlet": outlet, "author": outlet,
                       "published_at": (it.findtext("pubDate") or "").strip(),
                       "title": title, "body": title,
                       "raw": {"term": term}}
            self.log(f"news · {term} · {n} items")
            time.sleep(0.5)


class RegulatoryWatch(collector.Adapter):
    """Dated regulatory notices — SBP, Banking Mohtasib, PSX — as a context feed.

    These are not brand mentions: items land on the ``regulatory`` surface with
    no implicit mention, so they never touch share-of-voice or sentiment. Feeds
    are RSS or Atom; a broken or unreachable feed is skipped, not fatal. The
    default feed URLs are the published regulator endpoints and can be extended
    or overridden with the ``REGULATORY_FEEDS`` key (``Label|url`` per line).
    """
    ID = "regulatory_watch"
    # The regulators' own RSS endpoints are unreliable to fetch server-side —
    # SBP sits behind a bot-management WAF that 403s any non-browser client,
    # and Banking Mohtasib / PSX don't publish a working feed at all (PSX's
    # `/announcements` "rss" path is the Angular app shell, not XML). They
    # stay in the list as a best case (harmless if they fail — a feed error
    # is skipped, not fatal), backed by a Google News RSS search per
    # regulator — the same always-reachable mechanism GoogleNews already
    # uses — so the surface has real, current notices either way.
    FEEDS = [
        ("SBP", "https://www.sbp.org.pk/rss/PressRelease.xml"),
        ("SBP", "https://www.sbp.org.pk/rss/Circulars.xml"),
        ("SBP", collector._news_query_feed('"State Bank of Pakistan" '
                                           '(circular OR notification OR penalty OR directive) when:180d')),
        ("PSX", collector._news_query_feed('"Pakistan Stock Exchange" (listing OR delisting OR SECP OR '
                                           'penalty OR disclosure OR "circuit breaker") when:180d')),
        ("Banking Mohtasib", "https://www.bankingmohtasib.gov.pk/feed/"),
        ("Banking Mohtasib", collector._news_query_feed('"Banking Mohtasib" '
                                                        '(complaint OR relief OR customers OR banks) when:180d')),
    ]

    def fetch(self, terms):
        feeds = list(self.FEEDS)
        for line in str(self.k.get("REGULATORY_FEEDS") or "").splitlines():
            label, _, url = line.partition("|")
            if label.strip() and url.strip():
                feeds.append((label.strip(), url.strip()))
        for label, url in feeds:
            try:
                root = ET.fromstring(collector._get(url, timeout=30))
                self.count(self.ID)
            except Exception as e:
                self.count(self.ID, ok=False)
                self.log(f"regulatory · {label} feed failed — {e}")
                continue
            n = 0
            is_news_search = "news.google.com" in url
            for entry in self._entries(root):
                title = entry["title"]
                if not title:
                    continue
                n += 1
                raw, outlet = {"regulator": label}, label
                if is_news_search:
                    title, publisher = collector._gnews_outlet(title)
                    if publisher:
                        raw["publisher"] = outlet = publisher
                yield {
                    "external_id": collector._h(label, title, entry["link"]),
                    "url": entry["link"] or None, "outlet": outlet, "author": outlet,
                    "published_at": entry["published"] or None,
                    "title": title, "body": entry["summary"] or title,
                    "raw": raw,
                }
            self.log(f"regulatory · {label} · {n} notices")
            time.sleep(0.3)

    @staticmethod
    def _entries(root):
        rss_items = root.findall(".//item")
        if rss_items:
            for it in rss_items:
                yield {
                    "title": (it.findtext("title") or "").strip(),
                    "link": (it.findtext("link") or "").strip(),
                    "summary": (it.findtext("description") or "").strip(),
                    "published": (it.findtext("pubDate") or "").strip(),
                }
            return
        ns = "{http://www.w3.org/2005/Atom}"
        for e in root.findall(f".//{ns}entry"):
            link_el = e.find(f"{ns}link")
            yield {
                "title": (e.findtext(f"{ns}title") or "").strip(),
                "link": (link_el.get("href") if link_el is not None else "") or "",
                "summary": (e.findtext(f"{ns}summary")
                            or e.findtext(f"{ns}content") or "").strip(),
                "published": (e.findtext(f"{ns}updated")
                              or e.findtext(f"{ns}published") or "").strip(),
            }
