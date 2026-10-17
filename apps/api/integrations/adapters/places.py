"""Google Places API (First Generation) — reviews for the owned business
location. Place Details returns at most 5 reviews per call with no
pagination (a real API limitation, not a bug) so each pull is a refresh of
the most-relevant 5, deduped like every other adapter on `external_id`."""
import json
from datetime import datetime, timezone

from core import collector


class GooglePlacesReviews(collector.Adapter):
    """Reviews are about the place by identity, so `terms` is unused."""
    ID = "google_places_reviews"

    def fetch(self, terms):
        key = self.k["GOOGLE_PLACES_API_KEY"]
        place_id = self.k["GOOGLE_PLACE_ID"]
        url = ("https://maps.googleapis.com/maps/api/place/details/json"
               f"?place_id={place_id}&fields=name,url,rating,reviews&key={key}")
        try:
            payload = json.loads(collector._get(url, timeout=30))
            self.count(self.ID, calls=1)
        except Exception as e:
            self.count(self.ID, ok=False)
            self.log(f"google places · failed ({e})")
            return
        if payload.get("status") != "OK":
            self.count(self.ID, ok=False)
            self.log(f"google places · {payload.get('status')}: "
                      f"{payload.get('error_message', '')}")
            return
        result = payload.get("result") or {}
        place_url = result.get("url") or f"https://maps.google.com/?cid={place_id}"
        reviews = result.get("reviews") or []
        self.log(f"google places · {len(reviews)} reviews")
        for r in reviews:
            epoch = r.get("time")
            published = (datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()
                         if epoch else None)
            review_id = "gplace:" + str(epoch or collector._h(r.get("text")))
            yield {
                "external_id": review_id,
                # No per-review permalink from this API — same fallback
                # pattern as the App/Play Store adapters, kept unique per
                # review so dedupe's exact-URL pass doesn't fold them together.
                "url": f"{place_url}#review-{epoch}",
                "outlet": "Google Places",
                "author": r.get("author_name"),
                "published_at": published,
                "title": None,
                "body": r.get("text"),
                "rating": r.get("rating"),
                "raw": {"relative_time": r.get("relative_time_description")},
            }
