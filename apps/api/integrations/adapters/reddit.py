"""Reddit adapters — the unlicensed Arctic Shift archive and the OAuth free tier."""
import base64
import json
import time
import urllib.parse
from datetime import datetime, timezone

from core import collector


class ArcticShift(collector.Adapter):
    """Unlicensed community archive. Works from datacenter IPs where the Reddit
    free tier does not, but enforces a punishing per-IP budget."""
    ID = "arctic_shift"
    BASE = "https://arctic-shift.photon-reddit.com/api"
    SUBS = ["pakistan", "PakistaniTech", "developersPakistan", "chutyapa"]

    def fetch(self, terms):
        misses = 0
        for sub in self.SUBS:
            for term in terms[:3]:
                if misses >= 2:
                    self.log("arctic shift · budget exhausted, stopping early")
                    return
                url = (f"{self.BASE}/comments/search?subreddit={sub}"
                       f"&body={urllib.parse.quote(term)}&limit=100")
                try:
                    payload = json.loads(collector._get(url, timeout=60))
                    self.count(self.ID)
                except Exception as e:
                    self.count(self.ID, ok=False)
                    misses += 1
                    self.log(f"arctic shift · r/{sub} throttled ({e})")
                    time.sleep(5)
                    continue
                misses = 0
                rows = payload.get("data") or []
                self.log(f"reddit archive · r/{sub} · {term} · {len(rows)}")
                for c in rows:
                    ts = c.get("created_utc")
                    yield {"external_id": c.get("id"),
                           "url": "https://reddit.com" + (c.get("permalink") or ""),
                           "outlet": f"r/{sub}", "author": c.get("author"),
                           "published_at": datetime.fromtimestamp(
                               ts, timezone.utc).isoformat() if ts else None,
                           "title": None, "body": c.get("body"),
                           "raw": {"subreddit": sub, "score": c.get("score")}}
                time.sleep(1.5)


class RedditFree(collector.Adapter):
    ID = "reddit_free"
    SUBS = ["pakistan", "PakistaniTech", "developersPakistan", "chutyapa"]

    def fetch(self, terms):
        try:
            basic = base64.b64encode(
                f"{self.k['REDDIT_CLIENT_ID']}:{self.k['REDDIT_CLIENT_SECRET']}"
                .encode()).decode()
            tok = json.loads(collector._get("https://www.reddit.com/api/v1/access_token",
                                            data=b"grant_type=client_credentials",
                                            headers={"Authorization": f"Basic {basic}"}))["access_token"]
            self.count(self.ID)
        except Exception as e:
            self.count(self.ID, ok=False)
            self.log(f"reddit · auth failed ({e}) — expected from a datacenter IP")
            return
        hdr = {"Authorization": f"bearer {tok}"}
        for sub in self.SUBS:
            for term in terms[:4]:
                url = (f"https://oauth.reddit.com/r/{sub}/search?q="
                       f"{urllib.parse.quote(term)}&restrict_sr=1&sort=new&limit=100")
                try:
                    d = json.loads(collector._get(url, timeout=45, headers=hdr))
                    self.count(self.ID)
                except Exception as e:
                    self.count(self.ID, ok=False)
                    self.log(f"reddit · r/{sub} {term} failed ({e})")
                    continue
                kids = d.get("data", {}).get("children", [])
                self.log(f"reddit · r/{sub} · {term} · {len(kids)}")
                for ch in kids:
                    x = ch.get("data", {})
                    yield {"external_id": x.get("id"),
                           "url": "https://reddit.com" + (x.get("permalink") or ""),
                           "outlet": f"r/{sub}", "author": x.get("author"),
                           "published_at": datetime.fromtimestamp(
                               x["created_utc"], timezone.utc).isoformat()
                               if x.get("created_utc") else None,
                           "title": x.get("title"),
                           "body": x.get("selftext") or x.get("title"),
                           "raw": {"subreddit": sub, "score": x.get("score")}}
                time.sleep(0.7)
