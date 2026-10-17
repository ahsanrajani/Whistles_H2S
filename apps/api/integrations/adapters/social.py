"""Microblog adapters — Bluesky search and the X (Twitter) recent-search tier."""
import json
import time
import urllib.parse

from core import collector


class Bluesky(collector.Adapter):
    ID = "bluesky"

    def fetch(self, terms):
        try:
            body = json.dumps({"identifier": self.k["BLUESKY_HANDLE"],
                               "password": self.k["BLUESKY_APP_PASSWORD"]}).encode()
            s = json.loads(collector._get("https://bsky.social/xrpc/com.atproto.server.createSession",
                                          data=body, headers={"Content-Type": "application/json"}))
            jwt = s["accessJwt"]
            self.count(self.ID)
        except Exception as e:
            self.count(self.ID, ok=False)
            self.log(f"bluesky · session failed ({e})")
            return
        hdr = {"Authorization": f"Bearer {jwt}"}
        for term in terms[:4]:
            url = ("https://bsky.social/xrpc/app.bsky.feed.searchPosts?q="
                   + urllib.parse.quote(term) + "&limit=100")
            try:
                d = json.loads(collector._get(url, timeout=45, headers=hdr))
                self.count(self.ID)
            except Exception as e:
                self.count(self.ID, ok=False)
                self.log(f"bluesky · {term} failed ({e})")
                continue
            posts = d.get("posts", [])
            self.log(f"bluesky · {term} · {len(posts)}")
            for p in posts:
                rec = p.get("record", {})
                handle = (p.get("author") or {}).get("handle")
                rkey = (p.get("uri") or "").rsplit("/", 1)[-1]
                public_url = (f"https://bsky.app/profile/{handle}/post/{rkey}"
                              if handle and rkey else None)
                yield {"external_id": p.get("cid"), "url": public_url,
                       "outlet": "bluesky",
                       "author": handle,
                       "published_at": rec.get("createdAt"),
                       "title": None, "body": rec.get("text"),
                       "raw": {"term": term}}
            time.sleep(0.4)


class XRecent(collector.Adapter):
    """Sampled by design. The read cap is a hard halt, not an alert."""
    ID = "x_recent"

    def fetch(self, terms):
        cap = int(self.k.get("X_MONTHLY_READ_CAP") or 4000)
        used = int(self.k.get("_X_MONTHLY_USED") or 0)
        hdr = {"Authorization": f"Bearer {self.k['X_BEARER_TOKEN']}"}
        for term in terms[:3]:
            if used + 100 > cap:
                raise collector.QuotaExceeded(
                    f"X monthly read cap would be exceeded: {used} used, {cap} cap")
            url = ("https://api.x.com/2/tweets/search/recent?query="
                   + urllib.parse.quote(f'"{term}" -is:retweet')
                   + "&max_results=100&tweet.fields=created_at,lang,author_id")
            try:
                d = json.loads(collector._get(url, timeout=45, headers=hdr))
            except Exception as e:
                self.count(self.ID, ok=False)
                self.log(f"x · {term} failed ({e})")
                continue
            rows = d.get("data", [])
            used += len(rows)
            self.count(self.ID, units=len(rows))
            self.log(f"x · {term} · {len(rows)} (sampled)")
            for t in rows:
                yield {"external_id": t.get("id"),
                       "url": f"https://x.com/i/status/{t.get('id')}",
                       "outlet": "x.com", "author": t.get("author_id"),
                       "published_at": t.get("created_at"),
                       "title": None, "body": t.get("text"), "sampled": 1,
                       "raw": {"term": term, "lang": t.get("lang")}}
            time.sleep(0.5)


class XOwnedPosts(collector.Adapter):
    """The owned handle's own recent tweets, with real public engagement
    counts. `terms` is unused -- this is the account's own timeline."""
    ID = "x_owned_posts"

    def fetch(self, terms):
        handle = self.k["X_OWNED_HANDLE"].lstrip("@")
        hdr = {"Authorization": f"Bearer {self.k['X_BEARER_TOKEN']}"}
        try:
            who = json.loads(collector._get(
                f"https://api.x.com/2/users/by/username/{handle}", timeout=30, headers=hdr))
            self.count(self.ID, units=1)
        except Exception as e:
            self.count(self.ID, ok=False)
            self.log(f"x owned · handle lookup failed ({e})")
            return
        user_id = (who.get("data") or {}).get("id")
        if not user_id:
            self.log(f"x owned · {handle} not found")
            return
        url = (f"https://api.x.com/2/users/{user_id}/tweets"
               "?max_results=25&exclude=retweets,replies"
               "&tweet.fields=created_at,public_metrics")
        try:
            d = json.loads(collector._get(url, timeout=30, headers=hdr))
            self.count(self.ID, units=1)
        except Exception as e:
            self.count(self.ID, ok=False)
            self.log(f"x owned · timeline failed ({e})")
            return
        rows = d.get("data") or []
        self.log(f"x owned · {len(rows)} posts")
        for t in rows:
            pm = t.get("public_metrics") or {}
            yield {"external_id": t.get("id"),
                   "url": f"https://x.com/{handle}/status/{t.get('id')}",
                   "outlet": "x.com", "author": handle,
                   "published_at": t.get("created_at"), "title": None,
                   "body": t.get("text"),
                   "raw": {"kind": "post", "metrics": {
                       "likes": pm.get("like_count"), "reposts": pm.get("retweet_count"),
                       "replies": pm.get("reply_count"), "quotes": pm.get("quote_count")}}}
