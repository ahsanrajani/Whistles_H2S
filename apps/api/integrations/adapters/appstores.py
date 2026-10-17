"""App-store review adapters — the free iTunes RSS feed and Google Play reviews
via the DataForSEO App Data API."""
import base64
import json
import time

from core import collector

from . import app_meta


class AppStoreReviews(collector.Adapter):
    """Recent App Store reviews for the focus brand's app via the free iTunes
    RSS feed. Reviews are about the app by identity, so `terms` is unused."""
    ID = "appstore_reviews"

    def fetch(self, terms):
        """APPSTORE_APP_ID may hold several ids (comma/space separated) -- each
        review carries its app's id/name/icon in ``raw``."""
        cc = (self.k.get("APPSTORE_COUNTRY") or "pk").lower()
        for app_id in app_meta.parse_ids(self.k["APPSTORE_APP_ID"]):
            yield from self._fetch_app(app_id, cc, app_meta.appstore(app_id, cc))

    def _fetch_app(self, app_id, cc, meta):
        app_url = f"https://apps.apple.com/{cc}/app/id{app_id}"
        # Apple's RSS review feed is edge-cached per page and per-page results
        # are not contiguous -- confirmed live (2026-09-12) that page 2 can
        # come back empty while pages 3 and 6 still have reviews. Do not
        # treat one empty page as end-of-feed; only stop on a request error
        # or after page 10 (page 11 returns HTTP 400 -- Apple's own ceiling).
        for page in range(1, 11):
            url = (f"https://itunes.apple.com/{cc}/rss/customerreviews/"
                   f"page={page}/sortBy=mostRecent/id={app_id}/json")
            try:
                payload = json.loads(collector._get(url, timeout=45))
                self.count(self.ID)
            except Exception as e:
                self.count(self.ID, ok=False)
                self.log(f"app store · page {page} failed ({e})")
                break
            entries = ((payload.get("feed") or {}).get("entry")) or []
            if isinstance(entries, dict):
                entries = [entries]
            reviews = [e for e in entries if e.get("im:rating")]
            self.log(f"app store · page {page} · {len(reviews)} reviews")
            for e in reviews:
                try:
                    rating = int((e.get("im:rating") or {}).get("label") or 0)
                except (TypeError, ValueError):
                    rating = None
                review_id = (e.get("id") or {}).get("label") or ""
                yield {
                    "external_id": "as:" + review_id,
                    # Apple has no per-review permalink, so every review would
                    # otherwise share this exact URL — a `#` fragment (inert
                    # for both the browser and the App Store page) keeps each
                    # row distinct so collector.dedupe()'s exact_url pass
                    # doesn't fold 99 of every 100 reviews into "duplicates".
                    "url": f"{app_url}?see-all=reviews#review-{review_id}",
                    "outlet": "App Store",
                    "author": ((e.get("author") or {}).get("name") or {}).get("label"),
                    "published_at": (e.get("updated") or {}).get("label"),
                    "title": (e.get("title") or {}).get("label"),
                    "body": (e.get("content") or {}).get("label"),
                    "rating": rating,
                    "raw": {"version": (e.get("im:version") or {}).get("label"),
                            **app_meta.app_raw(app_id, meta)},
                }
            time.sleep(0.4)


class PlayStoreReviews(collector.Adapter):
    """Google Play reviews for the focus brand's app through the DataForSEO App
    Data API (there is no first-party Play reviews API)."""
    ID = "playstore_reviews"

    def fetch(self, terms):
        """PLAYSTORE_APP_ID may hold several package names (comma/space
        separated) -- each review carries its app's id/name/icon in ``raw``."""
        cc = (self.k.get("APPSTORE_COUNTRY") or "pk").lower()
        for app_id in app_meta.parse_ids(self.k["PLAYSTORE_APP_ID"]):
            yield from self._fetch_app(app_id, app_meta.playstore(app_id, cc))

    def _fetch_app(self, app_id, meta):
        auth = base64.b64encode(
            f"{self.k['DATAFORSEO_LOGIN']}:{self.k['DATAFORSEO_PASSWORD']}".encode()).decode()
        hdr = {"Authorization": f"Basic {auth}", "Content-Type": "application/json"}
        # Play Store has no per-review permalink (same limitation as the App
        # Store adapter) — DataForSEO does not return one either, so fall back
        # to the app's real listing page rather than link nowhere.
        app_url = f"https://play.google.com/store/apps/details?id={app_id}"
        task = [{"app_id": app_id, "location_code": 2586,
                 "language_code": "en", "depth": 200, "sort_by": "newest"}]
        try:
            posted = json.loads(collector._get(
                "https://api.dataforseo.com/v3/app_data/google/app_reviews/task_post",
                data=json.dumps(task).encode(), headers=hdr, timeout=90))
            self.count(self.ID, calls=1)
        except Exception as e:
            self.count(self.ID, ok=False)
            self.log(f"play reviews · task_post failed ({e})")
            return
        task_ids = [t.get("id") for t in posted.get("tasks", []) if t.get("id")]
        for task_id in task_ids:
            result = None
            for _ in range(18):
                time.sleep(6)
                try:
                    fetched = json.loads(collector._get(
                        "https://api.dataforseo.com/v3/app_data/google/app_reviews/"
                        "task_get/advanced/" + task_id, headers=hdr, timeout=45))
                except Exception as e:
                    self.count(self.ID, ok=False)
                    self.log(f"play reviews · task {task_id} failed ({e})")
                    break
                payload = fetched.get("tasks") or []
                result = payload[0].get("result") if payload else None
                if result:
                    break
            if not result:
                self.log(f"play reviews · task {task_id} not ready")
                continue
            for res in result:
                items = res.get("items") or []
                self.count(self.ID, units=len(items))
                self.log(f"play reviews · {len(items)} reviews")
                for it in items:
                    try:
                        rating = int((it.get("rating") or {}).get("value") or 0) or None
                    except (TypeError, ValueError):
                        rating = None
                    review_id = str(it.get("id") or collector._h(it.get("review_text")))
                    yield {
                        "external_id": "gp:" + review_id,
                        # Same fallback-collision risk as AppStoreReviews above
                        # — keep it unique per review with an inert fragment.
                        "url": it.get("review_url") or f"{app_url}#review-{review_id}",
                        "outlet": "Google Play",
                        "author": (it.get("user_profile") or {}).get("profile_name"),
                        "published_at": it.get("timestamp"),
                        "title": None,
                        "body": it.get("review_text"),
                        "rating": rating,
                        "raw": {"version": it.get("version"),
                                **app_meta.app_raw(app_id, meta)},
                    }
