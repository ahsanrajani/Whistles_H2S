"""Bright Data adapters — bounded collection from the focus brand's own
Facebook / Instagram channels (posts + comments) and the dormant Google Maps
reviews stub. Never fed entity/competitor search terms; every adapter enforces
the shared monthly record/dollar budget before it spends.
"""
from core import bright_data, collector


class BrightDataFacebookPosts(collector.Adapter):
    """Bounded collection from the focus brand's owned Facebook page only."""
    ID = "brightdata_facebook_posts"

    def fetch(self, terms):
        # Never use entity search terms here: that would multiply paid requests
        # across competitors. One explicit owned-page username is the only input.
        per_run = min(25, collector._positive_number(
            self.k.get("BRIGHT_DATA_FACEBOOK_PER_RUN_LIMIT", "5"),
            "Bright Data per-run limit", integer=True))
        budget = collector._bright_data_month_budget(self.k)
        limit = min(per_run, budget.records)

        self.log(
            "bright data facebook · focus page only · "
            f"limit {limit} · month {budget.used}/{budget.record_cap} records"
        )
        client = bright_data.BrightDataClient(self.k["BRIGHT_DATA_API_KEY"])
        try:
            result = client.discover_facebook_page_posts(
                self.k["BRIGHT_DATA_FACEBOOK_PAGE_USERNAME"], limit
            )
        except Exception:
            self.count(self.ID, calls=1, units=0, ok=False, unit_cost=budget.unit_cost)
            raise
        rows = result.records
        self.count(self.ID, calls=1, units=len(rows), unit_cost=budget.unit_cost)
        if len(rows) > limit:
            raise collector.QuotaExceeded(
                f"Bright Data returned {len(rows)} records above requested limit {limit}"
            )
        self.log(f"bright data facebook · {len(rows)} posts · snapshot {result.snapshot_id}")
        for row in rows:
            post_id = row.get("post_id") or row.get("shortcode")
            body = row.get("content")
            if not post_id or not body:
                continue
            yield {
                "external_id": f"bd-fb-post:{post_id}",
                "url": row.get("url"),
                "outlet": row.get("page_name") or "Facebook",
                "author": row.get("page_name") or row.get("user_username_raw"),
                "published_at": row.get("date_posted"),
                "title": None,
                "body": body,
                "raw": {
                    "kind": "post",
                    "snapshot_id": result.snapshot_id,
                    "provider_record": row,
                },
            }


class _BrightDataComments(collector.Adapter):
    """Bounded comment collection for the focus brand's own posts on one network.

    Inputs are post URLs already collected by the matching posts adapter (read
    from the DB into keys by ``run_collection``), never search terms. Because
    these provider datasets have no per-request record cap, this trims the number
    of posts to what the remaining monthly budget covers at the per-post cap, and
    re-applies the per-post cap to the returned rows.

    Subclasses set the network-specific ids/keys/labels below.
    """
    NETWORK = None            # "facebook" / "instagram", for log lines
    URLS_KEY = None           # keys entry holding the collected post URLs
    POSTS_PER_RUN_KEY = None
    PER_POST_KEY = None
    CLIENT_METHOD = None      # BrightDataClient method name
    EXTERNAL_ID_PREFIX = None
    OUTLET = None

    def fetch(self, terms):
        post_urls = list(self.k.get(self.URLS_KEY) or [])
        posts_per_run = collector._positive_number(
            self.k.get(self.POSTS_PER_RUN_KEY, "3"),
            f"Bright Data {self.NETWORK} comment posts-per-run", integer=True)
        per_post = min(200, collector._positive_number(
            self.k.get(self.PER_POST_KEY, "50"),
            f"Bright Data {self.NETWORK} comments-per-post", integer=True))
        budget = collector._bright_data_month_budget(self.k)
        if not post_urls:
            self.log(
                f"bright data {self.NETWORK} comments · no collected posts yet · skipped"
            )
            return

        max_posts = max(1, budget.records // per_post)
        selected = post_urls[:min(posts_per_run, max_posts)]
        self.log(
            f"bright data {self.NETWORK} comments · focus posts only · "
            f"{len(selected)} post(s) · <= {per_post}/post · "
            f"month {budget.used}/{budget.record_cap} records"
        )
        client = bright_data.BrightDataClient(self.k["BRIGHT_DATA_API_KEY"])
        try:
            result = getattr(client, self.CLIENT_METHOD)(selected, per_post)
        except Exception:
            self.count(self.ID, calls=1, units=0, ok=False, unit_cost=budget.unit_cost)
            raise
        rows = result.records
        self.count(self.ID, calls=1, units=len(rows), unit_cost=budget.unit_cost)
        if len(rows) > budget.records:
            raise collector.QuotaExceeded(
                f"Bright Data returned {len(rows)} comment records above the "
                f"affordable budget {budget.records}"
            )
        self.log(
            f"bright data {self.NETWORK} comments · {len(rows)} comments · "
            f"snapshot {result.snapshot_id}"
        )
        seen_per_post = {}
        for row in rows:
            comment_id = row.get("comment_id") or row.get("id")
            body = row.get("comment_text") or row.get("content")
            post_url = row.get("post_url") or row.get("post_id")
            if not comment_id or not body:
                continue
            count = seen_per_post.get(post_url, 0)
            if count >= per_post:
                continue                     # client-side backstop on the per-post cap
            seen_per_post[post_url] = count + 1
            actor = row.get("user_url") or row.get("user_id")
            yield {
                "external_id": f"{self.EXTERNAL_ID_PREFIX}:{comment_id}",
                "url": row.get("comment_url") or row.get("post_url"),
                "outlet": self.OUTLET,
                "author": row.get("user_name") or actor,
                "published_at": row.get("date_created") or row.get("date_posted"),
                "title": None,
                "body": body,
                "raw": {
                    "kind": "comment",
                    "snapshot_id": result.snapshot_id,
                    "post_url": row.get("post_url"),
                    "parent_comment_id": row.get("parent_comment_id"),
                    "actor_hash": collector._h(str(actor)) if actor else None,
                    "provider_record": row,
                },
            }


class BrightDataFacebookComments(_BrightDataComments):
    ID = "brightdata_facebook_comments"
    NETWORK = "facebook"
    URLS_KEY = "_BRIGHT_DATA_FACEBOOK_POST_URLS"
    POSTS_PER_RUN_KEY = "BRIGHT_DATA_FACEBOOK_COMMENT_POSTS_PER_RUN"
    PER_POST_KEY = "BRIGHT_DATA_FACEBOOK_COMMENTS_PER_POST"
    CLIENT_METHOD = "collect_facebook_post_comments"
    EXTERNAL_ID_PREFIX = "bd-fb-comment"
    OUTLET = "Facebook"


class BrightDataInstagramComments(_BrightDataComments):
    ID = "brightdata_instagram_comments"
    NETWORK = "instagram"
    URLS_KEY = "_BRIGHT_DATA_INSTAGRAM_POST_URLS"
    POSTS_PER_RUN_KEY = "BRIGHT_DATA_INSTAGRAM_COMMENT_POSTS_PER_RUN"
    PER_POST_KEY = "BRIGHT_DATA_INSTAGRAM_COMMENTS_PER_POST"
    CLIENT_METHOD = "collect_instagram_post_comments"
    EXTERNAL_ID_PREFIX = "bd-ig-comment"
    OUTLET = "Instagram"


class _BrightDataOwnedChannel(collector.Adapter):
    """Config-gated owned-channel post collector for a Bright Data dataset that
    is not part of the verified core set (P2.6).

    Dormant until ``DATASET_KEY`` (the dataset id) and ``TARGET_KEY`` (the owned
    username / company / profile) are both set. When live it discovers a bounded
    number of recent posts, honours the shared monthly Bright Data record + USD
    caps, and maps each row through the generic field aliases below. Never fed
    entity search terms.
    """
    DATASET_KEY = None
    TARGET_KEY = None
    PER_RUN_KEY = None            # optional; defaults to 5
    SURFACE_OUTLET = None
    EXTERNAL_PREFIX = None

    def available(self):
        return bool(self.k.get("BRIGHT_DATA_API_KEY"))

    def fetch(self, terms):
        dataset_id = (self.k.get(self.DATASET_KEY) or "").strip()
        target = (self.k.get(self.TARGET_KEY) or "").strip()
        if not dataset_id:
            self.log(f"{self.ID} · no dataset id configured — skipped")
            return
        if not target:
            self.log(f"{self.ID} · no owned-channel target configured — skipped")
            return

        per_run = min(25, collector._positive_number(
            self.k.get(self.PER_RUN_KEY or "", "5"),
            f"{self.ID} per-run limit", integer=True))
        budget = collector._bright_data_month_budget(self.k)
        limit = min(per_run, budget.records)
        self.log(f"{self.ID} · owned channel only · limit {limit} · "
                 f"month {budget.used}/{budget.record_cap} records")
        client = bright_data.BrightDataClient(self.k["BRIGHT_DATA_API_KEY"])
        try:
            result = client.discover_owned_posts(dataset_id, target, limit)
        except Exception:
            self.count(self.ID, calls=1, units=0, ok=False, unit_cost=budget.unit_cost)
            raise
        rows = result.records
        self.count(self.ID, calls=1, units=len(rows), unit_cost=budget.unit_cost)
        if len(rows) > limit:
            raise collector.QuotaExceeded(
                f"{self.ID} returned {len(rows)} records above requested {limit}")
        self.log(f"{self.ID} · {len(rows)} posts · snapshot {result.snapshot_id}")
        for row in rows:
            post_id = (row.get("post_id") or row.get("id") or row.get("shortcode")
                       or row.get("review_id") or row.get("url"))
            body = (row.get("content") or row.get("caption") or row.get("text")
                    or row.get("description") or row.get("review_text"))
            if not post_id or not body:
                continue
            yield {
                "external_id": f"{self.EXTERNAL_PREFIX}:{post_id}",
                "url": row.get("url"),
                "outlet": self.SURFACE_OUTLET,
                "author": (row.get("user_posted") or row.get("profile_name")
                           or row.get("author") or row.get("reviewer_name")
                           or self.SURFACE_OUTLET),
                "published_at": (row.get("date_posted") or row.get("timestamp")
                                 or row.get("date") or row.get("review_date")),
                "title": row.get("title"),
                "rating": row.get("rating") or row.get("stars"),
                "body": body,
                "raw": {"kind": "post", "snapshot_id": result.snapshot_id,
                        "provider_record": row},
            }


class BrightDataGoogleMapsReviews(_BrightDataOwnedChannel):
    """Google Maps reviews for the focus brand's own branch locations. Dormant
    until ``BRIGHT_DATA_GMAPS_REVIEWS_DATASET`` + ``BRIGHT_DATA_GMAPS_PLACE`` are
    set (the PoC runs on seeded review data). Items land on the ``branch_review``
    surface — no competitor places."""
    ID = "brightdata_gmaps_reviews"
    DATASET_KEY = "BRIGHT_DATA_GMAPS_REVIEWS_DATASET"
    TARGET_KEY = "BRIGHT_DATA_GMAPS_PLACE"
    SURFACE_OUTLET = "Google Maps"
    EXTERNAL_PREFIX = "bd-gmaps-review"


class BrightDataLinkedIn(_BrightDataOwnedChannel):
    """Config-only (P2.6). Owned LinkedIn company page posts."""
    ID = "brightdata_linkedin_posts"
    DATASET_KEY = "BRIGHT_DATA_LINKEDIN_DATASET"
    TARGET_KEY = "BRIGHT_DATA_LINKEDIN_COMPANY"
    SURFACE_OUTLET = "LinkedIn"
    EXTERNAL_PREFIX = "bd-li-post"


class BrightDataTikTok(_BrightDataOwnedChannel):
    """Config-only (P2.6). Owned TikTok account posts."""
    ID = "brightdata_tiktok_posts"
    DATASET_KEY = "BRIGHT_DATA_TIKTOK_DATASET"
    TARGET_KEY = "BRIGHT_DATA_TIKTOK_USERNAME"
    SURFACE_OUTLET = "TikTok"
    EXTERNAL_PREFIX = "bd-tt-post"


class BrightDataQuora(_BrightDataOwnedChannel):
    """Config-only (P2.6). Owned Quora space / profile posts."""
    ID = "brightdata_quora_posts"
    DATASET_KEY = "BRIGHT_DATA_QUORA_DATASET"
    TARGET_KEY = "BRIGHT_DATA_QUORA_PROFILE"
    SURFACE_OUTLET = "Quora"
    EXTERNAL_PREFIX = "bd-qr-post"


class BrightDataInstagramPosts(collector.Adapter):
    """Bounded collection from the focus brand's owned Instagram profile only."""
    ID = "brightdata_instagram_posts"

    def fetch(self, terms):
        # One explicit owned-profile username, never entity search terms.
        per_run = min(25, collector._positive_number(
            self.k.get("BRIGHT_DATA_INSTAGRAM_PER_RUN_LIMIT", "5"),
            "Bright Data Instagram per-run limit", integer=True))
        budget = collector._bright_data_month_budget(self.k)
        limit = min(per_run, budget.records)

        self.log(
            "bright data instagram · focus profile only · "
            f"limit {limit} · month {budget.used}/{budget.record_cap} records"
        )
        client = bright_data.BrightDataClient(self.k["BRIGHT_DATA_API_KEY"])
        try:
            result = client.discover_instagram_profile_posts(
                self.k["BRIGHT_DATA_INSTAGRAM_USERNAME"], limit
            )
        except Exception:
            self.count(self.ID, calls=1, units=0, ok=False, unit_cost=budget.unit_cost)
            raise
        rows = result.records
        self.count(self.ID, calls=1, units=len(rows), unit_cost=budget.unit_cost)
        if len(rows) > limit:
            raise collector.QuotaExceeded(
                f"Bright Data returned {len(rows)} records above requested limit {limit}"
            )
        self.log(
            f"bright data instagram · {len(rows)} posts · snapshot {result.snapshot_id}"
        )
        for row in rows:
            post_id = row.get("post_id") or row.get("shortcode")
            body = row.get("caption") or row.get("content")
            if not post_id or not body:
                continue
            yield {
                "external_id": f"bd-ig-post:{post_id}",
                "url": row.get("url"),
                "outlet": row.get("profile_name") or row.get("user_posted") or "Instagram",
                "author": row.get("user_posted") or row.get("profile_name"),
                "published_at": row.get("date_posted"),
                "title": None,
                "body": body,
                "raw": {
                    "kind": "post",
                    "snapshot_id": result.snapshot_id,
                    "provider_record": row,
                },
            }
