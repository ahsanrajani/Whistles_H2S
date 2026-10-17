"""Collection engine. Adapters yield raw records; matching happens centrally.

Every adapter logs its calls so cost is measured from the call_log rather than
asserted from a spreadsheet.

P0.4 moved the concrete adapters to ``integrations/adapters/`` (one module per
family) and the post-collection steps to ``collection/{dedupe,match,status}.py``.
This module keeps the shared primitives (``Adapter``, ``_get``, ``_h``, the
Bright Data budget helpers, ``QuotaExceeded``), the ``REGISTRY`` list and the
``run_collection`` orchestrator, and re-exports ``dedupe`` / ``match`` /
``write_status`` so ``collector.<name>`` and the tests' ``@patch`` seams are
unchanged. ``time`` / ``bright_data`` / ``sentiment`` stay imported here for the
same reason.
"""
import hashlib
import json
import re
import time  # noqa: F401 — re-exported: tests patch core.collector.time.sleep
import urllib.parse
import urllib.request
from collections import namedtuple
from datetime import datetime, timezone

from . import bright_data, classify, entity, sentiment, sources  # noqa: F401

UA = "whistles-ears/0.2"


def now():
    return datetime.now(timezone.utc).isoformat()


def _get(url, timeout=45, headers=None, data=None):
    req = urllib.request.Request(url, data=data,
                                 headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _h(*p):
    return hashlib.sha256("\x1f".join(x or "" for x in p).encode()).hexdigest()[:32]


def _news_query_feed(query):
    """A Google News RSS search URL — the same mechanism GoogleNews already
    uses, reused as a reachable, always-real stand-in for regulator sites
    whose own feeds are geo/bot-gated (see RegulatoryWatch)."""
    return ("https://news.google.com/rss/search?q=" + urllib.parse.quote(query)
            + "&hl=en-PK&gl=PK&ceid=PK:en")


def _gnews_outlet(title):
    """Split a Google News RSS "Headline - Outlet" title into (title, outlet)."""
    if " - " in title:
        head, outlet = title.rsplit(" - ", 1)
        return head.strip(), outlet.strip(" |-–—·").strip()
    return title, None


class Adapter:
    ID = None

    def __init__(self, keys, log, count):
        self.k = keys
        self.log = log
        self.count = count      # count(source, calls=1, units=0, ok=True)
        self._bucket = None

    @property
    def meta(self):
        return sources.SOURCES[self.ID]

    # --- contract v2 (P2.2) ------------------------------------------------
    @property
    def source_class(self):
        return self.meta.get("source_class", "third_party")

    @property
    def cadence_seconds(self):
        return int(self.meta.get("cadence", 86400))

    @property
    def cursor_kind(self):
        return self.meta.get("cursor", "none")

    def throttle(self, n=1.0):
        """Adapters that make many HTTP calls in one fetch() call this before
        each request to honour the declared token-bucket rate limit."""
        from integrations.adapters.contract import bucket_for
        if self._bucket is None:
            self._bucket = bucket_for(self.meta.get("rate_limit")) or False
        if self._bucket:
            self._bucket.take(n, sleep=time.sleep)

    def available(self):
        return all(self.k.get(n) for n in self.meta["needs"])

    def fetch(self, terms):
        return iter(())


class QuotaExceeded(RuntimeError):
    """A billing guardrail that must fail the collection visibly."""


def _positive_number(value, label, *, integer=False):
    try:
        parsed = int(value) if integer else float(value)
    except (TypeError, ValueError) as exc:
        raise QuotaExceeded(f"{label} must be a positive number") from exc
    if parsed <= 0:
        raise QuotaExceeded(f"{label} must be a positive number")
    return parsed


_BrightDataBudget = namedtuple(
    "_BrightDataBudget", "records unit_cost used record_cap spend dollar_cap"
)


def _bright_data_month_budget(keys):
    """Records still affordable this month across every Bright Data source.

    ``run_collection`` sums month-to-date usage from ``call_log`` into
    ``_BRIGHT_DATA_MONTHLY_*`` before the registry runs; this turns that plus the
    configured caps into a single record budget shared by the Facebook and
    Instagram collectors. Raises ``QuotaExceeded`` when nothing is affordable so
    the run fails visibly instead of spending against an uncapped provider
    dataset.
    """
    record_cap = _positive_number(
        keys.get("BRIGHT_DATA_FACEBOOK_MONTHLY_RECORD_CAP", "100"),
        "Bright Data monthly record cap", integer=True)
    unit_cost = _positive_number(
        keys.get("BRIGHT_DATA_COST_PER_RECORD_USD", "0.0007"),
        "Bright Data cost per record")
    dollar_cap = _positive_number(
        keys.get("BRIGHT_DATA_MONTHLY_CAP_USD", "0.10"),
        "Bright Data monthly dollar cap")
    used = int(keys.get("_BRIGHT_DATA_MONTHLY_RECORDS_USED", 0) or 0)
    spend = float(keys.get("_BRIGHT_DATA_MONTHLY_SPEND_USD", 0) or 0)
    affordable = int((max(0.0, dollar_cap - spend) + 1e-12) // unit_cost)
    records = min(max(0, record_cap - used), affordable)
    if records < 1:
        raise QuotaExceeded(
            "Bright Data monthly cap reached before request "
            f"({used}/{record_cap} records, ${spend:.4f}/${dollar_cap:.4f})"
        )
    return _BrightDataBudget(records, unit_cost, used, record_cap, spend, dollar_cap)


# Concrete adapters live in integrations/adapters/ (imported after the shared
# primitives above so their `from core import collector` sees a usable module).
from integrations.adapters import (  # noqa: E402
    AppStoreReviews, ArcticShift, Bluesky, BrightDataFacebookComments,
    BrightDataFacebookPosts, BrightDataGoogleMapsReviews,
    BrightDataInstagramComments, BrightDataInstagramPosts, BrightDataLinkedIn,
    BrightDataQuora, BrightDataSerpReddit, BrightDataSerpX, BrightDataTikTok,
    DataForSEOBrandSerp, DataForSEOSerp, DataForSEOStandard, DataForSEOWebBackfill,
    GoogleNews, GooglePlacesReviews, MetaBase, MetaFacebook, MetaInstagram,
    PlayStoreReviews, RedditFree, RegulatoryWatch, XOwnedPosts, XRecent, YouTube,
    YouTubeOwnedVideos, _BrightDataComments, _BrightDataOwnedChannel)

REGISTRY = [GoogleNews, RegulatoryWatch, ArcticShift, RedditFree, DataForSEOSerp, DataForSEOBrandSerp,
            XRecent, YouTube, Bluesky, AppStoreReviews, PlayStoreReviews,
            MetaFacebook, MetaInstagram, BrightDataFacebookPosts,
            BrightDataFacebookComments, BrightDataInstagramPosts,
            BrightDataInstagramComments, BrightDataGoogleMapsReviews,
            BrightDataLinkedIn, BrightDataTikTok, BrightDataQuora,
            BrightDataSerpX, BrightDataSerpReddit, DataForSEOWebBackfill,
            GooglePlacesReviews, YouTubeOwnedVideos, XOwnedPosts]

# Post-collection steps live in collection/; re-exported so callers and tests
# keep reaching them as collector.dedupe / collector.match / collector.write_status.
from collection import authors as _authors  # noqa: E402
from collection import simhash as _simhash  # noqa: E402
from collection.dedupe import dedupe  # noqa: E402,F401
from collection.match import match  # noqa: E402,F401
from collection.status import write_status  # noqa: E402,F401


# ------------------------------------------------------------------ pipeline
def norm(s):
    return re.sub(r"\W+", " ", (s or "").lower()).strip()


def run_collection(db, workspace_id, run_id, keys, log, only_sources=None):
    """``only_sources`` — a set of source IDs to run (per-source scheduling,
    P2.7); ``None`` runs the whole registry."""
    from db import pipeline, repositories as repo
    from integrations.adapters.contract import CircuitBreaker

    s = db.session
    brands = entity.load(db, workspace_id)
    terms = entity.search_terms(brands)
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    keys = dict(keys)
    keys["_X_MONTHLY_USED"] = pipeline.x_units_this_month(s, month)
    bd_used, bd_spend = pipeline.bright_data_month_usage(s, month)
    keys["_BRIGHT_DATA_MONTHLY_RECORDS_USED"] = bd_used
    keys["_BRIGHT_DATA_MONTHLY_SPEND_USD"] = bd_spend

    keys["_BRIGHT_DATA_FACEBOOK_POST_URLS"] = pipeline.recent_post_urls(
        s, workspace_id, "brightdata_facebook_posts")
    keys["_BRIGHT_DATA_INSTAGRAM_POST_URLS"] = pipeline.recent_post_urls(
        s, workspace_id, "brightdata_instagram_posts")
    log(f"terms · {', '.join(terms)}")

    def count(src, calls=1, units=0, ok=True, unit_cost=None):
        meta = sources.SOURCES[src]
        pipeline.insert_call_log(
            s, workspace_id=workspace_id, run_id=run_id, source=src, calls=calls,
            units=units,
            unit_cost=meta["unit_cost"] if unit_cost is None else unit_cost,
            ok=ok, at=now())

    focus = repo.brands.focus_id_name(s, workspace_id)
    focus_brand_id = focus[0] if focus else None
    retention = repo.retention.policy(s, workspace_id)   # {source_class: mode}

    new = 0
    used = []
    for cls in REGISTRY:
        if only_sources is not None and cls.ID not in only_sources:
            continue
        a = cls(keys, log, count)
        if not a.available():
            log(f"{a.meta['label']} · skipped (no credentials)")
            continue

        state = repo.source_state.load(s, workspace_id, a.ID)

        # Per-workspace opt-out (0027): the source is wired and credentialled
        # but this workspace has switched it off.
        if state and not state.get("enabled", True):
            log(f"{a.meta['label']} · skipped (disabled for this workspace)")
            continue

        # Circuit breaker (P2.2): a source that failed 5 runs straight is
        # skipped until its cooldown elapses, then gets one trial run.
        breaker = CircuitBreaker.restore(state)
        if not breaker.allow():
            log(f"{a.meta['label']} · skipped (circuit open)")
            continue

        log(f"{a.meta['label']} · collecting")
        implicit_rule = a.meta.get("implicit_rule") if a.meta.get("brand_implicit") else None
        got = 0
        adapter_error = None
        try:
            for rec in a.fetch(terms):
                text = " ".join(filter(None, [rec.get("title"), rec.get("body")]))
                sclass = a.source_class
                author_id = _authors.upsert_author(
                    s, workspace_id, platform=a.meta["surface"],
                    name=rec.get("author"), platform_id=rec.get("author_id"),
                    profile_url=rec.get("profile_url"), source_class=sclass,
                    retention_mode=retention.get(sclass, "full"), at=now())
                inserted = pipeline.insert_item(s, (
                    workspace_id, a.meta["surface"], a.ID, a.meta["kind"],
                    rec.get("external_id"), rec.get("url"), rec.get("outlet"),
                    rec.get("author"), rec.get("published_at"), rec.get("title"),
                    rec.get("body"), entity.guess_lang(text), rec.get("rating"),
                    rec.get("sampled", 0),
                    run_id, json.dumps(rec.get("raw") or {}), now(),
                    hashlib.sha256(norm(text).encode()).hexdigest()[:32],
                    _simhash.simhash(norm(text)),
                    author_id, sclass))
                if inserted:
                    got += 1
                    if implicit_rule and focus_brand_id:
                        # This source is about the focus brand by identity (its
                        # own app / pages), so entity rules do not apply.
                        pipeline.insert_implicit_mention(
                            s, brand_id=focus_brand_id, rule=implicit_rule,
                            ws=workspace_id, source=a.ID,
                            external_id=rec.get("external_id"))
        except Exception as e:
            adapter_error = e
            log(f"{a.meta['label']} · error {e}")
            if isinstance(e, QuotaExceeded):
                raise

        now_ts = datetime.now(timezone.utc)
        common = {"last_attempt_at": now_ts, "items_last_run": got,
                  "last_run_id": run_id}
        if adapter_error is None:
            breaker.record_success()
            fields = {**common, "last_success_at": now_ts, "last_error": None,
                      **breaker.snapshot()}
        else:
            breaker.record_failure()
            fields = {**common, "last_error": str(adapter_error)[:2000],
                      **breaker.snapshot()}
        repo.source_state.save(s, workspace_id, a.ID, **fields)
        db.commit()
        new += got
        used.append(a)
        log(f"{a.meta['label']} · {got} new")

    dedupe(db, workspace_id, log)
    match(db, workspace_id, brands, log)
    write_status(db, workspace_id, run_id, used, keys)
    db.commit()

    if keys.get("HF_TOKEN"):
        try:
            sentiment.score_pending(db, workspace_id, keys, log)
        except Exception as e:                       # never fail a collection on it
            log(f"sentiment · skipped ({e})")
        try:
            classify.classify_pending(db, workspace_id, keys, log)
        except Exception as e:
            log(f"classify · skipped ({e})")
    else:
        log("sentiment · HF_TOKEN missing, English mentions left pending")
    db.commit()
    return new
