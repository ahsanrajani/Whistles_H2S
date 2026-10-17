"""Real, live App Store / Google Play aggregate rating figures for the focus
brand's app: average rating, total rating count, and each store's 1-5 star
histogram.

Real, live network calls (an Apple lookup + a DataForSEO app_info task) only
happen inside ``refresh()``, which is an explicit admin action (POST
/reviews/store-stats/run in api_fastapi/dashboards.py) -- never scheduled,
same posture as the Vantage SEO/panel runs in core/seo_report.py and
core/seo_crawl.py. ``review_context()`` (called on every dashboard read) only
reads back whatever ``refresh()`` last wrote to ``metric_fact`` -- a plain DB
read, no network call, no cost.

Never fabricates: a workspace that hasn't refreshed yet, or a figure a fetch
couldn't get, is null all the way through -- the UI says unknown rather than
falling back to a guessed or stale value.
"""
import base64
import json
import re
import time
from datetime import date
from urllib.error import URLError

from core import collector
from core.stats import wilson
from integrations.adapters import app_meta
from db.repositories import metric_fact as mf_repo
from db.repositories.brands import focus_id_name

API = "https://api.dataforseo.com/v3"
APPSTORE_SOURCE = "appstore"
PLAYSTORE_SOURCE = "playstore"

# The specific nested-array shape Google embeds in the Play Store listing
# page's inline JSON state for "average, [1-star..5-star counts], total
# reviews, total ratings" -- the same embedded-JSON technique the open-source
# `google-play-scraper` library uses (DataForSEO's app_info/app_reviews
# products don't expose a rating breakdown, only the average + total; see
# fetch_playstore_stats). Matched by shape, not by a brittle array index, so
# it survives unrelated reshuffling elsewhere on the page.
_HIST_RE = re.compile(
    r'\[\["\d+(?:\.\d+)?",[\d.]+\],\[null,'
    r'\["[\d,]+",(?P<n1>\d+)\],'
    r'\["[\d,]+",(?P<n2>\d+)\],'
    r'\["[\d,]+",(?P<n3>\d+)\],'
    r'\["[\d,]+",(?P<n4>\d+)\],'
    r'\["[\d,]+",(?P<n5>\d+)\]\],'
    r'\["[\d,]+",(?P<total>\d+)\],'
    r'\["[\d,]+",\d+\]'
)

# Apple's public app page (apps.apple.com) renders its star-mix bars as a
# `<li>` per star with an aria-label of this shape -- e.g.
# `aria-label="5 stars, 74 percent, of ratings are 5 stars"`. Only the
# percentage is real; Apple doesn't publish exact per-star counts anywhere
# public, so `fetch_appstore_histogram()` turns each percentage into an
# approximate count using the real total from fetch_appstore_stats(). This
# markup shape hasn't been re-verified live this session (network access
# wasn't available while writing this) -- if Apple has since changed it,
# the regex simply finds no matches and the function returns None, same
# never-a-guess fallback as fetch_playstore_histogram().
_APPSTORE_HIST_RE = re.compile(
    r'aria-label="(?P<star>[1-5]) stars?,\s*(?P<pct>\d+(?:\.\d+)?) percent'
)


def _get_retry(url, *, headers=None, timeout=30, data=None, retries=2, wait=3):
    """collector._get() with a couple of retries for a transient connect-level
    blip -- same helper as core/seo_crawl.py::_get_retry, duplicated locally
    to keep this module's only dependency on that file conceptual, not a
    private import."""
    for attempt in range(retries + 1):
        try:
            return collector._get(url, headers=headers, timeout=timeout, data=data)
        except (URLError, OSError):
            if attempt == retries:
                raise
            time.sleep(wait)


def fetch_appstore_stats(app_id, country="pk"):
    """Real average rating + total rating count via Apple's free, public
    iTunes lookup endpoint -- no auth, no cost. None if Apple has no listing
    for this id/country or the two fields are both missing."""
    url = f"https://itunes.apple.com/lookup?id={app_id}&country={country}"
    results = (json.loads(_get_retry(url, timeout=20)).get("results")) or []
    if not results:
        return None
    r = results[0]
    rating, count = r.get("averageUserRating"), r.get("userRatingCount")
    if rating is None and count is None:
        return None
    return {"rating": float(rating) if rating is not None else None,
            "count": int(count) if count is not None else None}


def fetch_appstore_histogram(app_id, country="pk", expected_total=None):
    """Best-effort 1-5 star counts for the App Store, derived from the real
    percentages Apple renders on the public app page's star-mix bars. Needs
    `expected_total` (the live count from fetch_appstore_stats) to turn a
    percentage into a count -- without it there's nothing to multiply by, so
    returns None rather than emitting bare percentages as if they were
    counts. Returns None -- never a guess -- if the page layout doesn't
    match, if not all five stars are found, or the percentages don't
    round-trip near 100%."""
    if not expected_total:
        return None
    url = f"https://apps.apple.com/{country}/app/id{app_id}"
    html = _get_retry(url, timeout=30,
                      headers={"Accept-Language": "en-US,en;q=0.9"}).decode("utf-8", "replace")
    pct_by_star = {}
    for m in _APPSTORE_HIST_RE.finditer(html):
        pct_by_star[int(m.group("star"))] = float(m.group("pct"))
    if sorted(pct_by_star) != [1, 2, 3, 4, 5]:
        return None
    if not 90 <= sum(pct_by_star.values()) <= 110:
        return None
    return {str(star): round(pct_by_star[star] / 100 * expected_total) for star in range(1, 6)}


def fetch_playstore_stats(app_id, login, password, location_code=2586, language_code="en"):
    """Real average rating + total rating count via DataForSEO's App Data
    `app_info` product -- task_post + task_get/advanced only, per this repo's
    binding DataForSEO convention (test_integrity.py::
    test_dataforseo_uses_standard_queue), never /live/."""
    auth = base64.b64encode(f"{login}:{password}".encode()).decode()
    hdr = {"Authorization": f"Basic {auth}", "Content-Type": "application/json"}
    task = [{"app_id": app_id, "location_code": location_code, "language_code": language_code}]
    posted = json.loads(_get_retry(
        f"{API}/app_data/google/app_info/task_post", headers=hdr, timeout=45,
        data=json.dumps(task).encode()))
    task_ids = [t.get("id") for t in posted.get("tasks", []) if t.get("id")]
    if not task_ids:
        return None
    task_id = task_ids[0]
    for _ in range(10):
        time.sleep(3)
        fetched = json.loads(collector._get(
            f"{API}/app_data/google/app_info/task_get/advanced/{task_id}",
            headers=hdr, timeout=30))
        tasks = fetched.get("tasks") or []
        result = tasks[0].get("result") if tasks else None
        if result:
            items = (result[0] or {}).get("items") or []
            if not items:
                return None
            rating = (items[0].get("rating") or {}).get("value")
            count = items[0].get("reviews_count")
            if rating is None and count is None:
                return None
            return {"rating": float(rating) if rating is not None else None,
                    "count": int(count) if count is not None else None}
    return None


def fetch_playstore_histogram(app_id, country="pk", expected_total=None):
    """Best-effort 1-5 star counts, scraped straight from the public Play
    Store listing page (free, no DataForSEO cost). The page can embed more
    than one match for this shape (older/cached widgets alongside the live
    one) -- confirmed live 2026-09-14 for com.base.bankalfalah, where an
    earlier block's total (376,273) didn't match the live app_info total
    (377,574) that a later block agreed with. When `expected_total` (the
    live count from fetch_playstore_stats) is given, the block whose total
    matches it is preferred; otherwise the last match wins, on the
    observation that Google renders the live widget after any cached ones.
    Returns None -- never a guess -- if the page layout doesn't match at all.
    """
    url = f"https://play.google.com/store/apps/details?id={app_id}&hl=en&gl={country}"
    html = _get_retry(url, timeout=30,
                      headers={"Accept-Language": "en-US,en;q=0.9"}).decode("utf-8", "replace")
    matches = list(_HIST_RE.finditer(html))
    if not matches:
        return None
    chosen = matches[-1]
    if expected_total is not None:
        for m in matches:
            if int(m.group("total")) == expected_total:
                chosen = m
                break
    return {str(i): int(chosen.group(f"n{i}")) for i in range(1, 6)}


def _meta_row(source, app_id, day, meta):
    """The app's name/icon, stored beside its figures so the card can label
    each app without a network call at read time. Nothing stored when the
    lookup failed."""
    if not (meta.get("name") or meta.get("icon")):
        return []
    return [{"source": source, "entity_type": "app", "entity_ref": app_id,
             "metric": "app_meta", "day": day,
             "dims": {"name": meta.get("name"), "icon": meta.get("icon")}}]


def _refresh_appstore(app_id, cc, today, log):
    rows = []
    try:
        stats = fetch_appstore_stats(app_id, cc)
    except Exception as e:                                       # noqa: BLE001
        log(f"app store {app_id} stats · failed ({e})")
        stats = None
    if stats:
        rows += _fact_rows(APPSTORE_SOURCE, app_id, today, stats)
        log(f"app store {app_id} stats · {stats['rating']}★ · {stats['count']} ratings")
    try:
        hist = fetch_appstore_histogram(app_id, cc, expected_total=stats["count"] if stats else None)
    except Exception as e:                                       # noqa: BLE001
        log(f"app store {app_id} histogram · failed ({e})")
        hist = None
    if hist:
        rows.append({"source": APPSTORE_SOURCE, "entity_type": "app", "entity_ref": app_id,
                    "metric": "rating_histogram", "day": today, "dims": hist})
        log(f"app store {app_id} histogram · {hist}")
    if rows:
        rows += _meta_row(APPSTORE_SOURCE, app_id, today, app_meta.appstore(app_id, cc))
    return rows


def _refresh_playstore(app_id, cc, keys, today, log):
    rows, stats = [], None
    try:
        stats = fetch_playstore_stats(app_id, keys["DATAFORSEO_LOGIN"], keys["DATAFORSEO_PASSWORD"])
    except Exception as e:                                       # noqa: BLE001
        log(f"play store {app_id} stats · failed ({e})")
    if stats:
        rows += _fact_rows(PLAYSTORE_SOURCE, app_id, today, stats)
        log(f"play store {app_id} stats · {stats['rating']}★ · {stats['count']} reviews")
    try:
        hist = fetch_playstore_histogram(app_id, cc, expected_total=stats["count"] if stats else None)
    except Exception as e:                                       # noqa: BLE001
        log(f"play store {app_id} histogram · failed ({e})")
        hist = None
    if hist:
        rows.append({"source": PLAYSTORE_SOURCE, "entity_type": "app", "entity_ref": app_id,
                    "metric": "rating_histogram", "day": today, "dims": hist})
        log(f"play store {app_id} histogram · {hist}")
    if rows:
        rows += _meta_row(PLAYSTORE_SOURCE, app_id, today, app_meta.playstore(app_id, cc))
    return rows


def refresh(session, workspace_id, keys, log=lambda s: None):
    """Fetch real, live aggregate figures right now for EVERY configured app
    (APPSTORE_APP_ID / PLAYSTORE_APP_ID may each list several) and persist
    them to metric_fact, one entity_ref per app. Returns a small
    {store: bool} summary of whether any app in that store wrote; caller
    commits."""
    today = date.today().isoformat()
    cc = (keys.get("APPSTORE_COUNTRY") or "pk").lower()
    wrote = {"appstore": False, "playstore": False}
    rows = []

    ios_ids = app_meta.parse_ids(keys.get("APPSTORE_APP_ID"))
    for app_id in ios_ids:
        got = _refresh_appstore(app_id, cc, today, log)
        rows += got
        wrote["appstore"] = wrote["appstore"] or bool(got)
    if not ios_ids:
        log("app store stats · skipped (no APPSTORE_APP_ID)")

    play_ids = app_meta.parse_ids(keys.get("PLAYSTORE_APP_ID"))
    if play_ids and keys.get("DATAFORSEO_LOGIN") and keys.get("DATAFORSEO_PASSWORD"):
        for app_id in play_ids:
            got = _refresh_playstore(app_id, cc, keys, today, log)
            rows += got
            wrote["playstore"] = wrote["playstore"] or bool(got)
    else:
        log("play store stats · skipped (no PLAYSTORE_APP_ID or DataForSEO credentials)")

    if rows:
        mf_repo.upsert_many(session, workspace_id, rows)
    return wrote


def _fact_rows(source, app_id, day, stats):
    rows = []
    if stats.get("rating") is not None:
        rows.append({"source": source, "entity_type": "app", "entity_ref": app_id,
                    "metric": "rating_avg", "day": day, "value": stats["rating"]})
    if stats.get("count") is not None:
        rows.append({"source": source, "entity_type": "app", "entity_ref": app_id,
                    "metric": "rating_count", "day": day, "value": stats["count"]})
    return rows


def _dims(row):
    d = row["dims"] if row else None
    if isinstance(d, str):
        try:
            return json.loads(d or "{}")
        except ValueError:
            return {}
    return d or {}


def _one_app(session, workspace_id, source, app_id):
    latest = mf_repo.latest_by_metric(session, workspace_id, source, entity_ref=app_id)
    if not latest:
        return None
    avg_row, count_row = latest.get("rating_avg"), latest.get("rating_count")
    rating = float(avg_row["value"]) if avg_row and avg_row["value"] is not None else None
    count = int(count_row["value"]) if count_row and count_row["value"] is not None else None
    hist_row = latest.get("rating_histogram")
    hist = _dims(hist_row) or None
    if rating is None and count is None and not hist:
        return None
    captured = (avg_row or count_row or hist_row)["captured_at"]
    meta = _dims(latest.get("app_meta"))
    icon = meta.get("icon")
    out = {"app_id": app_id, "name": meta.get("name"),
           "icon": icon if isinstance(icon, str) and icon.startswith("https://") else None,
           "rating": rating, "count": count,
           "captured_at": captured.isoformat() if captured else None}
    if hist:
        out["histogram"] = hist
    return out


def _store_apps(session, workspace_id, source):
    """Every app of one store with real figures, in id order."""
    apps = [_one_app(session, workspace_id, source, ref)
            for ref in mf_repo.entity_refs(session, workspace_id, source)]
    return [a for a in apps if a]


def _store_rollup(apps):
    """One store's headline: the app itself when there's one, else the
    count-weighted rollup of its apps."""
    if not apps:
        return None
    return apps[0] if len(apps) == 1 else _combined(*apps)


def _combined(*stores):
    """Derived, count-weighted rollup of whichever of the two stores has real
    figures -- never a fetch of its own. A store only contributes to the
    weighted average if it has both a rating and a count (weighting by an
    unknown count would itself be a guess); histograms are summed star by
    star across whichever stores have one."""
    entries = [e for e in stores if e]
    if not entries:
        return None
    weighted = [(e["rating"], e["count"]) for e in entries if e["rating"] is not None and e["count"] is not None]
    rating = round(sum(r * c for r, c in weighted) / sum(c for _, c in weighted), 2) if weighted else None
    counts = [e["count"] for e in entries if e["count"] is not None]
    count = sum(counts) if counts else None
    hist = {}
    for e in entries:
        for star, n in (e.get("histogram") or {}).items():
            hist[star] = hist.get(star, 0) + n
    captured = max((e["captured_at"] for e in entries if e["captured_at"]), default=None)
    out = {"rating": rating, "count": count, "captured_at": captured}
    if hist:
        out["histogram"] = hist
        total = sum(hist.values())
        if total:
            good = hist.get("4", 0) + hist.get("5", 0)
            gp, glo, ghi = wilson(good, total)
            out["good_share"], out["good_lo"], out["good_hi"] = gp, glo, ghi
    return out


def review_context(session, workspace_id):
    """{"focus_brand_id", "store_stats": {"app_store", "play_store", "combined",
    "apps"} | None} -- the read side dashboards.py::reviews() spreads into its
    payload on every request. Pure DB read, no network call. ``apps`` lists
    every app with its own figures (store, app_id, name, icon, ...);
    ``app_store`` / ``play_store`` roll each store's apps up."""
    focus = focus_id_name(session, workspace_id)
    ios = _store_apps(session, workspace_id, APPSTORE_SOURCE)
    play = _store_apps(session, workspace_id, PLAYSTORE_SOURCE)
    app_store, play_store = _store_rollup(ios), _store_rollup(play)
    stats = None
    if app_store or play_store:
        stats = {"app_store": app_store, "play_store": play_store,
                 "combined": _combined(app_store, play_store),
                 "apps": ([{**a, "store": "app_store"} for a in ios]
                          + [{**a, "store": "play_store"} for a in play])}
    return {"focus_brand_id": focus[0] if focus else None, "store_stats": stats}
