"""DataForSEO SERP adapters — Reddit discovery and plain brand SERPs through the
Standard task-post / task-get queue."""
import base64
import json
import time
from datetime import datetime, timezone

from core import collector


class DataForSEOStandard(collector.Adapter):
    """DataForSEO Standard task-post/task-get flow shared by SERP adapters."""
    QUERY_PREFIX = ""

    def keywords(self, terms):
        return [self.QUERY_PREFIX + term for term in terms[:3]]

    def fetch(self, terms):
        auth = base64.b64encode(
            f"{self.k['DATAFORSEO_LOGIN']}:{self.k['DATAFORSEO_PASSWORD']}".encode()).decode()
        hdr = {"Authorization": f"Basic {auth}", "Content-Type": "application/json"}
        tasks = [{"language_code": "en", "location_code": 2586,
                  "keyword": keyword, "depth": 10}
                 for keyword in self.keywords(terms)]
        try:
            posted = json.loads(collector._get(
                "https://api.dataforseo.com/v3/serp/google/organic/task_post",
                data=json.dumps(tasks).encode(), headers=hdr, timeout=90))
            self.count(self.ID, calls=len(tasks))
        except Exception as e:
            self.count(self.ID, ok=False)
            self.log(f"dataforseo · failed ({e})")
            return
        task_ids = [task.get("id") for task in posted.get("tasks", []) if task.get("id")]
        for task_id in task_ids:
            result = None
            for _ in range(12):
                time.sleep(5)
                try:
                    fetched = json.loads(collector._get(
                        "https://api.dataforseo.com/v3/serp/google/organic/task_get/advanced/"
                        + task_id, headers=hdr, timeout=45))
                except Exception as e:
                    self.count(self.ID, ok=False)
                    self.log(f"dataforseo · task {task_id} failed ({e})")
                    break
                payload = fetched.get("tasks") or []
                result = payload[0].get("result") if payload else None
                if result:
                    break
            if not result:
                self.log(f"dataforseo · task {task_id} not ready after 60s")
                continue
            for res in result:
                items = res.get("items") or []
                keyword = res.get("keyword", "")
                self.log(f"dataforseo · {keyword[:40]} · {len(items)}")
                for it in items:
                    if it.get("type") != "organic":
                        continue
                    yield {"external_id": collector._h(it.get("url")),
                           "url": it.get("url"), "outlet": it.get("domain"),
                           "author": it.get("domain"),
                           "published_at": None, "title": it.get("title"),
                           "body": (it.get("title") or "") + " " + (it.get("description") or ""),
                           "raw": {"rank": it.get("rank_absolute"), "keyword": keyword}}


class DataForSEOSerp(DataForSEOStandard):
    """Reddit discovery through the Standard queue."""
    ID = "dataforseo_serp"
    QUERY_PREFIX = "site:reddit.com "


class DataForSEOBrandSerp(DataForSEOStandard):
    """Plain brand SERPs through the Standard queue."""
    ID = "dataforseo_brand_serp"


class DataForSEOWebBackfill(DataForSEOBrandSerp):
    """Historical backfill (cadence 0 — never auto-scheduled, only run via
    ``only_sources=["web_backfill"]``): the same plain brand-SERP query,
    year-qualified. There is no verified date-range parameter on this queue,
    but Google's own organic ranking for "<brand> <year>" skews hard toward
    that year even without one — the same task_post/task_get mechanism already
    proven live, just fed different keywords. Worth a small real test run to
    confirm it actually surfaces older material before relying on it."""
    ID = "web_backfill"
    YEARS_BACK = 3

    def keywords(self, terms):
        this_year = datetime.now(timezone.utc).year
        years = range(this_year - self.YEARS_BACK, this_year)
        return [f"{self.QUERY_PREFIX}{term} {year}"
                for term in terms[:3] for year in years]
