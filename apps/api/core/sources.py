"""Source registry: one place that knows what each source costs, what it needs,
and whether it may ever reach a client.

Unit costs are the verified list prices, not estimates. `cost_note` explains
any figure that would otherwise look wrong.
"""

SOURCES = {
    "googlenews_rss": {
        "label": "Google News RSS", "surface": "news", "kind": "public",
        "independent": True, "needs": [], "unit": "query",
        "unit_cost": 0.0, "cost_note": "No credentials, no cost, no rate card.",
        "client_safe": True,
    },
    "regulatory_watch": {
        "label": "Regulatory watch (SBP / Mohtasib / PSX)", "surface": "regulatory",
        "kind": "public", "independent": True, "needs": [], "unit": "feed",
        "unit_cost": 0.0,
        "cost_note": "Public regulator RSS/Atom feeds. Context, not brand mentions — "
                     "items land on the 'regulatory' surface with no implicit mention.",
        "client_safe": True,
    },
    "arctic_shift": {
        "label": "Arctic Shift", "surface": "reddit", "kind": "unlicensed",
        "independent": True, "needs": [], "unit": "query",
        "unit_cost": 0.0,
        "cost_note": "Free community archive. Per-IP budget trips after ~30 calls.",
        "client_safe": False,
        "warn": "Unlicensed archive. Evaluation only — must not reach client output.",
    },
    "reddit_free": {
        "label": "Reddit API (free tier)", "surface": "reddit", "kind": "noncommercial",
        "independent": True, "needs": ["REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET"],
        "unit": "query", "unit_cost": 0.0,
        "cost_note": "100 QPM, non-commercial. 403s from datacenter IPs.",
        "client_safe": False,
        "warn": "Non-commercial tier. Commercial access is a 2-4 week queue.",
    },
    "dataforseo_serp": {
        "label": "DataForSEO SERP", "surface": "reddit", "kind": "licensed",
        "independent": True, "needs": ["DATAFORSEO_LOGIN", "DATAFORSEO_PASSWORD"],
        "unit": "SERP (10 results)", "unit_cost": 0.0006,
        "cost_note": "Standard queue. Live is $0.002 — 3.3x for a 5-minute gain "
                     "a nightly collector does not need.",
        "client_safe": True,
    },
    "dataforseo_brand_serp": {
        "label": "DataForSEO brand SERP", "surface": "web", "kind": "licensed",
        "independent": True, "needs": ["DATAFORSEO_LOGIN", "DATAFORSEO_PASSWORD"],
        "unit": "SERP (10 results)", "unit_cost": 0.0006,
        "cost_note": "Plain brand SERPs through the Standard task queue.",
        "client_safe": True,
    },
    "web_backfill": {
        "label": "Historical web backfill (DataForSEO)", "surface": "web",
        "kind": "licensed", "independent": True,
        "needs": ["DATAFORSEO_LOGIN", "DATAFORSEO_PASSWORD"],
        "unit": "SERP (10 results)", "unit_cost": 0.0006,
        "cost_note": "Year-qualified brand SERPs (\"<brand> <year>\") through the "
                     "same Standard queue as dataforseo_brand_serp, reaching back "
                     "WEB_BACKFILL_YEARS_BACK years. Never auto-scheduled (cadence "
                     "0) — an explicit one-off admin action, ~3x the query volume "
                     "of a normal pass for the years it covers.",
        "client_safe": True,
    },
    "brightdata_serp_x": {
        "label": "X via Bright Data SERP", "surface": "x", "kind": "licensed",
        "independent": True,
        "needs": ["BRIGHT_DATA_API_KEY", "BRIGHT_DATA_SERP_ZONE"],
        "unit": "SERP (10 results)", "unit_cost": 0.0015,
        "cost_note": "Google `site:x.com`/`twitter.com` discovery through Bright "
                     "Data's SERP API — reuses the account key, no dataset id. "
                     "Coverage is what Google indexes, not the firehose.",
        "client_safe": True, "sampled": True,
    },
    "brightdata_serp_reddit": {
        "label": "Reddit via Bright Data SERP", "surface": "reddit", "kind": "licensed",
        "independent": True,
        "needs": ["BRIGHT_DATA_API_KEY", "BRIGHT_DATA_SERP_ZONE"],
        "unit": "SERP (10 results)", "unit_cost": 0.0015,
        "cost_note": "Google `site:reddit.com` discovery through Bright Data's "
                     "SERP API — a second, independent Reddit path alongside "
                     "dataforseo_serp. Reuses the account key, no dataset id.",
        "client_safe": True,
    },
    "dataforseo_content": {
        "label": "DataForSEO Content Analysis", "surface": "news",
        "kind": "licensed", "independent": True,
        "needs": ["DATAFORSEO_LOGIN", "DATAFORSEO_PASSWORD"],
        "unit": "search", "unit_cost": 0.02,
        "cost_note": "Second independent news source. Without it, news coverage "
                     "is not estimable.",
        "client_safe": True,
    },
    "x_recent": {
        "label": "X recent search", "surface": "x", "kind": "licensed",
        "independent": False, "needs": ["X_BEARER_TOKEN"], "unit": "read",
        "unit_cost": 0.005,
        "cost_note": "~46% of the bill and purely variable with no volume "
                     "discount. 7-day window; history starts at first poll.",
        "client_safe": True, "sampled": True,
    },
    "x_owned_posts": {
        "label": "X owned timeline", "surface": "x", "kind": "licensed",
        "independent": True, "needs": ["X_BEARER_TOKEN", "X_OWNED_HANDLE"],
        "unit": "read", "unit_cost": 0.005,
        "cost_note": "Same read-tier pricing as x_recent; 2 calls per run.",
        "client_safe": True, "brand_implicit": True,
        "implicit_rule": "brightdata_owned_channel",
    },
    "youtube_v3": {
        "label": "YouTube Data API", "surface": "youtube", "kind": "public",
        "independent": False, "needs": ["YOUTUBE_API_KEY"], "unit": "search",
        "unit_cost": 0.0,
        "cost_note": "10,000 units/day free; search costs 100, so ~100/day.",
        "client_safe": True,
    },
    "youtube_owned_videos": {
        "label": "YouTube channel uploads (owned)", "surface": "youtube",
        "kind": "public", "independent": True,
        "needs": ["YOUTUBE_API_KEY", "YOUTUBE_CHANNEL_ID"],
        "unit": "call", "unit_cost": 0.0,
        "cost_note": "10,000 units/day free; ~3 calls per run.",
        "client_safe": True, "brand_implicit": True,
        "implicit_rule": "brightdata_owned_channel",
    },
    "bluesky": {
        "label": "Bluesky", "surface": "bluesky", "kind": "public",
        "independent": False, "needs": ["BLUESKY_HANDLE", "BLUESKY_APP_PASSWORD"],
        "unit": "query", "unit_cost": 0.0,
        "cost_note": "Free. PK banking volume is near zero — include for "
                     "completeness, never as an X substitute.",
        "client_safe": True,
    },
    "meta_facebook": {
        "label": "Facebook (Meta Graph)", "surface": "facebook", "kind": "public",
        "independent": False, "needs": ["META_ACCESS_TOKEN", "META_PAGE_ID"],
        "unit": "graph call", "unit_cost": 0.0,
        "cost_note": "Meta Graph API. Page posts and their comments.",
        "client_safe": True, "brand_implicit": True, "implicit_rule": "meta_mention",
    },
    "brightdata_facebook_posts": {
        "label": "Facebook posts (Bright Data)", "surface": "facebook",
        "kind": "licensed", "independent": False,
        "needs": ["BRIGHT_DATA_API_KEY", "BRIGHT_DATA_FACEBOOK_PAGE_USERNAME"],
        "unit": "record", "unit_cost": 0.0007,
        "cost_note": "Focus-brand page only. The default is Bright Data's published "
                     "starting rate; set the account-specific rate in Admin.",
        "warn": "Never use this source for competitor collection.",
        "client_safe": True, "brand_implicit": True,
        "implicit_rule": "brightdata_owned_channel",
    },
    "brightdata_facebook_comments": {
        "label": "Facebook comments (Bright Data)", "surface": "facebook",
        "kind": "licensed", "independent": False,
        "needs": ["BRIGHT_DATA_API_KEY", "BRIGHT_DATA_FACEBOOK_PAGE_USERNAME"],
        "unit": "record", "unit_cost": 0.0007,
        "cost_note": "Comments on the focus brand's own posts only. The provider "
                     "dataset has no per-request cap, so spend is bounded by the "
                     "shared monthly record/USD caps, a posts-per-run limit, and "
                     "a per-post comment limit.",
        "warn": "Never use this source for competitor collection.",
        "client_safe": True, "brand_implicit": True,
        "implicit_rule": "brightdata_owned_channel",
    },
    "brightdata_instagram_posts": {
        "label": "Instagram posts (Bright Data)", "surface": "instagram",
        "kind": "licensed", "independent": False,
        "needs": ["BRIGHT_DATA_API_KEY", "BRIGHT_DATA_INSTAGRAM_USERNAME"],
        "unit": "record", "unit_cost": 0.0007,
        "cost_note": "Focus-brand profile only. Shares the monthly Bright Data "
                     "record and USD caps with the Facebook collectors.",
        "warn": "Never use this source for competitor collection.",
        "client_safe": True, "brand_implicit": True,
        "implicit_rule": "brightdata_owned_channel",
    },
    "brightdata_instagram_comments": {
        "label": "Instagram comments (Bright Data)", "surface": "instagram",
        "kind": "licensed", "independent": False,
        "needs": ["BRIGHT_DATA_API_KEY", "BRIGHT_DATA_INSTAGRAM_USERNAME"],
        "unit": "record", "unit_cost": 0.0007,
        "cost_note": "Comments on the focus brand's own posts only. Uncapped "
                     "dataset — bounded by the shared monthly caps, a posts-per-run "
                     "limit, and a per-post comment limit.",
        "warn": "Never use this source for competitor collection.",
        "client_safe": True, "brand_implicit": True,
        "implicit_rule": "brightdata_owned_channel",
    },
    "brightdata_gmaps_reviews": {
        "label": "Google Maps branch reviews (Bright Data)", "surface": "branch_review",
        "kind": "licensed", "independent": True,
        "needs": ["BRIGHT_DATA_API_KEY", "BRIGHT_DATA_GMAPS_REVIEWS_DATASET"],
        "unit": "record", "unit_cost": 0.0015,
        "cost_note": "Reviews for the focus brand's own branch locations. Two-stage "
                     "(discover place URL per branch, then pull reviews); shares the "
                     "monthly Bright Data record and USD caps. Dormant until the "
                     "dataset ids are set — the PoC runs on seeded review data.",
        "warn": "Focus-brand branch locations only — never competitor places.",
        "client_safe": True, "brand_implicit": True,
        "implicit_rule": "brightdata_owned_channel",
    },
    "brightdata_linkedin_posts": {
        "label": "LinkedIn company posts (Bright Data)", "surface": "linkedin",
        "kind": "licensed", "independent": True,
        "needs": ["BRIGHT_DATA_API_KEY", "BRIGHT_DATA_LINKEDIN_DATASET",
                  "BRIGHT_DATA_LINKEDIN_COMPANY"],
        "unit": "record", "unit_cost": 0.0015,
        "cost_note": "Config-only (P2.6). Owned company page only; shares the "
                     "monthly Bright Data caps. Dormant until the dataset id is set.",
        "client_safe": True, "brand_implicit": True,
        "implicit_rule": "brightdata_owned_channel",
    },
    "brightdata_tiktok_posts": {
        "label": "TikTok posts (Bright Data)", "surface": "tiktok",
        "kind": "licensed", "independent": True,
        "needs": ["BRIGHT_DATA_API_KEY", "BRIGHT_DATA_TIKTOK_DATASET",
                  "BRIGHT_DATA_TIKTOK_USERNAME"],
        "unit": "record", "unit_cost": 0.0015,
        "cost_note": "Config-only (P2.6). Owned account only. Dormant until the "
                     "dataset id is set.",
        "client_safe": True, "brand_implicit": True,
        "implicit_rule": "brightdata_owned_channel",
    },
    "brightdata_quora_posts": {
        "label": "Quora posts (Bright Data)", "surface": "quora",
        "kind": "licensed", "independent": True,
        "needs": ["BRIGHT_DATA_API_KEY", "BRIGHT_DATA_QUORA_DATASET",
                  "BRIGHT_DATA_QUORA_PROFILE"],
        "unit": "record", "unit_cost": 0.0015,
        "cost_note": "Config-only (P2.6). Owned profile / space only. Dormant "
                     "until the dataset id is set.",
        "client_safe": True, "brand_implicit": True,
        "implicit_rule": "brightdata_owned_channel",
    },
    "google_maps_reviews": {
        "label": "Google Maps branch reviews (seed)", "surface": "branch_review",
        "kind": "licensed", "independent": True, "needs": [], "unit": "review",
        "unit_cost": 0.0,
        "cost_note": "PoC placeholder — branch reviews paraphrased from real public "
                     "complaints and loaded by scripts/seed_branch_demo.py. Replaced "
                     "by brightdata_gmaps_reviews once live.",
        "client_safe": True, "brand_implicit": True,
        "implicit_rule": "brightdata_owned_channel",
    },
    "google_places_reviews": {
        "label": "Google Places reviews (owned location)", "surface": "branch_review",
        "kind": "official", "independent": True,
        "needs": ["GOOGLE_PLACES_API_KEY", "GOOGLE_PLACE_ID"],
        "unit": "call", "unit_cost": 0.0,
        "cost_note": "Google Places API (First Gen) Place Details. Free tier covers "
                     "normal review-monitoring volume. Returns at most 5 most-relevant "
                     "reviews per call, no pagination — a real API ceiling.",
        "client_safe": True, "brand_implicit": True,
        "implicit_rule": "brightdata_owned_channel",
    },
    "meta_instagram": {
        "label": "Instagram (Meta Graph)", "surface": "instagram", "kind": "public",
        "independent": False, "needs": ["META_ACCESS_TOKEN", "META_IG_USER_ID"],
        "unit": "graph call", "unit_cost": 0.0,
        "cost_note": "Meta Graph API. Account media captions and their comments.",
        "client_safe": True, "brand_implicit": True, "implicit_rule": "meta_mention",
    },
    "appstore_reviews": {
        "label": "App Store reviews", "surface": "app_reviews", "kind": "public",
        "independent": True, "needs": ["APPSTORE_APP_ID"], "unit": "page (50 reviews)",
        "unit_cost": 0.0,
        "cost_note": "Free public iTunes RSS feed. Up to 500 recent reviews.",
        "client_safe": True, "brand_implicit": True, "implicit_rule": "app_review",
    },
    "playstore_reviews": {
        "label": "Google Play reviews", "surface": "app_reviews", "kind": "licensed",
        "independent": True,
        "needs": ["DATAFORSEO_LOGIN", "DATAFORSEO_PASSWORD", "PLAYSTORE_APP_ID"],
        "unit": "150 reviews", "unit_cost": 0.0009,
        "cost_note": "DataForSEO App Data API. Billed per 150 reviews returned.",
        "client_safe": True, "brand_implicit": True, "implicit_rule": "app_review",
    },
    "huggingface_sentiment": {
        "label": "Sentiment (Hugging Face)", "surface": "—", "kind": "licensed",
        "independent": False, "needs": ["HF_TOKEN"], "unit": "inference",
        "unit_cost": 0.0,
        "cost_note": "Hosted text classification. Actual provider compute cost is "
                     "recorded by Hugging Face and varies by runtime.",
        "client_safe": True,
    },
    "huggingface_classify": {
        "label": "Mention type (Hugging Face)", "surface": "—", "kind": "licensed",
        "independent": False, "needs": ["HF_TOKEN"], "unit": "inference",
        "unit_cost": 0.0,
        "cost_note": "Hosted zero-shot classification, one call per mention. "
                     "Provider compute cost is recorded by Hugging Face.",
        "client_safe": True,
    },
}

CLIENT_SAFE_KINDS = ("public", "licensed")

# --- Adapter contract v2 (build plan §4 / P2.2) -------------------------------
# Every source declares cadence (seconds), incremental cursor kind, an optional
# token-bucket rate limit, and its source_class. Applied below as
# defaults + per-source overrides so the diff stays small and coverage total.
_CONTRACT_DEFAULTS = {
    "cadence": 86400,          # daily
    "cursor": "none",
    "rate_limit": None,        # or {"per_second": float, "burst": int}
    "source_class": "third_party",
}
_CONTRACT_OVERRIDES = {
    # third-party aggregators / scrapers, run hourly, timestamp-cursored feeds
    "googlenews_rss":        {"cadence": 3600, "cursor": "timestamp"},
    "regulatory_watch":      {"cadence": 21600, "cursor": "timestamp",
                              "source_class": "official"},
    "arctic_shift":          {"cadence": 43200, "cursor": "timestamp"},
    "reddit_free":           {"cadence": 21600, "cursor": "timestamp",
                              "rate_limit": {"per_second": 1.0, "burst": 5}},
    "dataforseo_serp":       {"cadence": 86400, "cursor": "page"},
    "dataforseo_brand_serp": {"cadence": 86400, "cursor": "page"},
    "web_backfill":          {"cadence": 0, "cursor": "page"},   # explicit-only
    "brightdata_serp_x":     {"cadence": 21600, "cursor": "page",
                              "rate_limit": {"per_second": 1.0, "burst": 3}},
    "brightdata_serp_reddit": {"cadence": 21600, "cursor": "page",
                               "rate_limit": {"per_second": 1.0, "burst": 3}},
    "dataforseo_content":    {"cadence": 86400, "cursor": "timestamp"},
    "youtube_owned_videos":  {"cadence": 21600, "cursor": "id",
                              "source_class": "official"},
    "x_owned_posts":         {"cadence": 21600, "cursor": "id",
                              "source_class": "official"},
    "x_recent":              {"cadence": 3600, "cursor": "timestamp",
                              "rate_limit": {"per_second": 1.0, "burst": 3}},
    "bluesky":               {"cadence": 3600, "cursor": "timestamp"},
    # platform-official APIs
    "meta_facebook":         {"cadence": 3600, "cursor": "timestamp",
                              "source_class": "official",
                              "rate_limit": {"per_second": 5.0, "burst": 10}},
    "meta_instagram":        {"cadence": 3600, "cursor": "timestamp",
                              "source_class": "official",
                              "rate_limit": {"per_second": 5.0, "burst": 10}},
    "google_maps_reviews":   {"cadence": 21600, "cursor": "timestamp",
                              "source_class": "official"},
    "google_places_reviews": {"cadence": 21600, "cursor": "timestamp",
                              "source_class": "official"},
    "appstore_reviews":      {"cadence": 21600, "cursor": "id",
                              "source_class": "official"},
    "playstore_reviews":     {"cadence": 21600, "cursor": "id",
                              "source_class": "official"},
    # Bright Data family — hourly for posts, cost-capped
    "brightdata_facebook_posts":     {"cadence": 3600, "cursor": "id"},
    "brightdata_facebook_comments":  {"cadence": 3600, "cursor": "id"},
    "brightdata_instagram_posts":    {"cadence": 3600, "cursor": "id"},
    "brightdata_instagram_comments": {"cadence": 3600, "cursor": "id"},
    "brightdata_gmaps_reviews":      {"cadence": 86400, "cursor": "id"},
    "brightdata_linkedin_posts":     {"cadence": 21600, "cursor": "id"},
    "brightdata_tiktok_posts":       {"cadence": 21600, "cursor": "id"},
    "brightdata_quora_posts":        {"cadence": 21600, "cursor": "id"},
    # inference services — not collectors, run on demand
    "huggingface_sentiment": {"cadence": 0, "source_class": "official"},
    "huggingface_classify":  {"cadence": 0, "source_class": "official"},
}
for _sid, _meta in SOURCES.items():
    for _k, _default in _CONTRACT_DEFAULTS.items():
        _meta.setdefault(_k, _default)
    _meta.update(_CONTRACT_OVERRIDES.get(_sid, {}))

KEYS = [
    ("BRIGHT_DATA_API_KEY", "Bright Data API key (focus-brand collection only)"),
    ("BRIGHT_DATA_SERP_ZONE", "Bright Data SERP API zone name (for X/Reddit discovery)"),
    ("BRIGHT_DATA_FACEBOOK_PAGE_USERNAME", "Owned Facebook page username"),
    ("BRIGHT_DATA_FACEBOOK_PER_RUN_LIMIT", "Bright Data Facebook posts per run (default 5)"),
    ("BRIGHT_DATA_FACEBOOK_MONTHLY_RECORD_CAP", "Bright Data monthly record cap, all FB/IG sources (default 100)"),
    ("BRIGHT_DATA_COST_PER_RECORD_USD", "Bright Data account cost per record USD (default 0.0007)"),
    ("BRIGHT_DATA_MONTHLY_CAP_USD", "Bright Data monthly dollar cap, all FB/IG sources (default 0.10)"),
    ("BRIGHT_DATA_FACEBOOK_COMMENT_POSTS_PER_RUN", "Bright Data comment posts per run (default 3)"),
    ("BRIGHT_DATA_FACEBOOK_COMMENTS_PER_POST", "Bright Data comments-per-post cap (default 50)"),
    ("BRIGHT_DATA_INSTAGRAM_USERNAME", "Owned Instagram profile username"),
    ("BRIGHT_DATA_INSTAGRAM_PER_RUN_LIMIT", "Bright Data Instagram posts per run (default 5)"),
    ("BRIGHT_DATA_INSTAGRAM_COMMENT_POSTS_PER_RUN", "Bright Data IG comment posts per run (default 3)"),
    ("BRIGHT_DATA_INSTAGRAM_COMMENTS_PER_POST", "Bright Data IG comments-per-post cap (default 50)"),
    ("DATAFORSEO_LOGIN", "DataForSEO login (email)"),
    ("DATAFORSEO_PASSWORD", "DataForSEO API password — not the account password"),
    ("X_BEARER_TOKEN", "X bearer token"),
    ("X_MONTHLY_READ_CAP", "X hard read cap (default 4000)"),
    ("X_OWNED_HANDLE", "Owned X @handle for owned-analytics (no @)"),
    ("X_WRITE_TOKEN", "X OAuth2 user token for replies/DMs (tweet.write, dm.write, block.write)"),
    ("X_OWNED_USER_ID", "Owned X numeric user id (optional; for block/unblock)"),
    ("REDDIT_CLIENT_ID", "Reddit script app client id"),
    ("REDDIT_CLIENT_SECRET", "Reddit script app secret"),
    ("YOUTUBE_API_KEY", "YouTube Data API v3 key"),
    ("YOUTUBE_CHANNEL_ID", "Owned YouTube channel id (starts with UC…)"),
    ("YOUTUBE_OAUTH_TOKEN", "YouTube OAuth2 token for comment replies (youtube.force-ssl)"),
    ("GOOGLE_BUSINESS_TOKEN", "Google Business Profile OAuth2 token for review replies"),
    ("BLUESKY_HANDLE", "Bluesky handle"),
    ("BLUESKY_APP_PASSWORD", "Bluesky app password — not the account password"),
    ("APPSTORE_APP_ID", "App Store numeric app id (from the store URL); several apps: separate with spaces or commas"),
    ("APPSTORE_COUNTRY", "App Store country code (default pk)"),
    ("PLAYSTORE_APP_ID", "Google Play package name, e.g. com.examplebank.mobile; several apps: separate with spaces or commas"),
    ("META_ACCESS_TOKEN", "Meta long-lived page access token"),
    ("META_PAGE_ID", "Facebook Page id"),
    ("META_IG_USER_ID", "Instagram Business account id"),
    ("META_APP_ID", "Meta app id (optional; appsecret_proof)"),
    ("META_APP_SECRET", "Meta app secret (optional; appsecret_proof)"),
    ("INSTAGRAM_LOGIN_ACCESS_TOKEN",
     "Instagram User Access Token from the standalone 'Instagram API with Instagram "
     "Login' app — preferred route for Instagram DM read + reply (graph.instagram.com; "
     "no Page-token exchange). Falls back to META_ACCESS_TOKEN's route if unset."),
    ("INSTAGRAM_LOGIN_APP_ID", "Instagram-Login app id (optional; token refresh)"),
    ("INSTAGRAM_LOGIN_APP_SECRET", "Instagram-Login app secret (optional; token refresh)"),
    ("GURU_WRITE_LIVE", "Real external API calls for this workspace — writes + owned-analytics pulls (1 = on; default off)"),
    ("LINKEDIN_ACCESS_TOKEN", "LinkedIn Marketing API OAuth token (owned analytics + write)"),
    ("LINKEDIN_ORG_URN", "LinkedIn company URN, e.g. urn:li:organization:12345"),
    ("LINKEDIN_API_VERSION", "LinkedIn-Version header, YYYYMM (optional; default 202405)"),
    ("REGULATORY_FEEDS", "Extra regulator feeds, one 'Label|https://…' per line (optional)"),
    ("BRAND_DOMAINS", "Official brand domains for impersonation watch, comma/space separated"),
    ("BRIGHT_DATA_GMAPS_DISCOVERY_DATASET", "Bright Data Google Maps business-discovery dataset id (gd_…)"),
    ("BRIGHT_DATA_GMAPS_REVIEWS_DATASET", "Bright Data Google Maps reviews dataset id (gd_…)"),
    ("BRIGHT_DATA_GMAPS_PLACE", "Owned branch place name / query for Bright Data Maps reviews"),
    ("BRIGHT_DATA_LINKEDIN_DATASET", "Bright Data LinkedIn company-posts dataset id (gd_…) — config-only"),
    ("BRIGHT_DATA_LINKEDIN_COMPANY", "Owned LinkedIn company page slug"),
    ("BRIGHT_DATA_TIKTOK_DATASET", "Bright Data TikTok posts dataset id (gd_…) — config-only"),
    ("BRIGHT_DATA_TIKTOK_USERNAME", "Owned TikTok username"),
    ("BRIGHT_DATA_QUORA_DATASET", "Bright Data Quora posts dataset id (gd_…) — config-only"),
    ("BRIGHT_DATA_QUORA_PROFILE", "Owned Quora profile / space"),
    ("ALERT_CONFIG", "Alert thresholds as JSON (optional; overrides defaults)"),
    ("ALERT_SLACK_WEBHOOK", "Slack incoming-webhook URL for alert dispatch (optional)"),
    ("ALERT_WEBHOOK_URL", "Generic JSON webhook for alert dispatch — email / WhatsApp relay (optional)"),
    ("HF_TOKEN", "Hugging Face inference token"),
    ("GOOGLE_API_KEY", "Google AI (Gemini) API key — care-reply drafting + Vantage panel"),
    ("GEMINI_MODEL", "Gemini model id (optional; default gemini-3.5-flash)"),
    ("OPENROUTER_API_KEY", "OpenRouter API key — Vantage AI-visibility panel (GPT/Perplexity/Claude/Llama + Gemini fallback)"),
    ("GOOGLE_PLACES_API_KEY", "Google Places API key (business review collection)"),
    ("GOOGLE_PLACE_ID", "Google Place id for the owned business location"),
    ("GOOGLE_OAUTH2_CLIENT_ID", "Google Cloud OAuth2 client id (mints Business Profile / YouTube reply tokens)"),
    ("GOOGLE_OAUTH2_CLIENT_SECRET", "Google Cloud OAuth2 client secret"),
    ("GOOGLE_OAUTH2_REFRESH_TOKEN", "Google OAuth2 refresh token (long-lived; used to mint short-lived access tokens)"),
    ("SENTIMENT_MODEL_ID", "Pinned sentiment model id"),
    ("CLASSIFY_MODEL_ID", "Pinned mention-type (zero-shot) model id"),
]

# No API and no licensing path at any price. Rendered as unmonitored, not zero.
UNMONITORABLE = {
    "facebook_public": "Public posts by non-Pages, and all Groups. No API, no licensing path.",
    "tiktok": "No listening API. No commercial licensing path.",
    "linkedin": "No listening API. No commercial licensing path.",
    "whatsapp": "End-to-end encrypted. Structurally unmonitorable.",
}

# Modelled monthly running cost per brand, by scenario. Measured spend from
# call_log is shown alongside so the model can be checked against reality.
SCENARIO_MODEL = {
    "low":  {"total": 6.95,  "detail": {"DataForSEO content": 2.40, "X": 2.50,
                                        "SERP": 0.30, "reviews": 0.10,
                                        "sentiment": 0.25, "infra": 1.40}},
    "mid":  {"total": 17.44, "detail": {"DataForSEO content": 7.20, "X": 7.50,
                                        "SERP": 0.65, "reviews": 0.14,
                                        "sentiment": 0.76, "infra": 1.20}},
    "high": {"total": 47.00, "detail": {"DataForSEO content": 19.00, "X": 21.50,
                                        "SERP": 1.80, "reviews": 0.40,
                                        "sentiment": 2.10, "infra": 2.20}},
}
