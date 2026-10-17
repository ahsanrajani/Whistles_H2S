"""Site crawl + Core Web Vitals via DataForSEO's On-Page API -- real, costed,
always an explicit admin action, never scheduled (same posture as the AI
panel and the keyword/backlink SEO report). Two DataForSEO products:

* **on_page** -- crawls up to `max_crawl_pages` real pages and scores them
  against DataForSEO's full on-page check set (canonical tags, duplicate
  meta, broken links, image alt text, thin content, ...) -- the "100+
  point" check variety SEMrush markets; a real crawl of N pages, not a
  single-page sample. Site-wide `page_metrics.checks` is what gets stored.
* **on_page/lighthouse** -- a real Google Lighthouse run against the
  homepage (Core Web Vitals: LCP, CLS, TBT, FCP, Speed Index, TTI, plus the
  four Lighthouse category scores). Lighthouse audits one URL at a time and
  takes 30-90s on its own, so this covers the homepage as the
  representative page (the same convention PageSpeed Insights and SEMrush's
  own site-audit summary use), not the whole crawled set.

Both block the request while polling task_post -> task_get, same pattern as
integrations/adapters/dataforseo.py's existing task-based adapters, bounded
so an admin's browser doesn't hang indefinitely.
"""
import base64
import json
import time
from datetime import datetime, timezone
from urllib.error import URLError

from core import collector
from db.repositories import metric_fact as mf_repo

API = "https://api.dataforseo.com/v3"
SOURCE = "dataforseo_crawl"
_POLL_INTERVAL = 5
_CRAWL_MAX_WAIT = 240        # seconds
_LIGHTHOUSE_MAX_WAIT = 150   # seconds


def _auth_headers(keys):
    auth = base64.b64encode(
        f"{keys['DATAFORSEO_LOGIN']}:{keys['DATAFORSEO_PASSWORD']}".encode()).decode()
    return {"Authorization": f"Basic {auth}", "Content-Type": "application/json"}


def _get_retry(url, *, headers, timeout, data=None, retries=2, wait=3):
    """collector._get() with a couple of retries for a transient connect-level
    blip -- live-verified on a dev box as WinError 10013 (an ephemeral port
    landing in a Windows/Hyper-V port-exclusion range), but the same class of
    failure can happen on any host. Used for the one-shot task_post calls,
    which (unlike the poll loops below) have no natural retry cadence of
    their own."""
    for attempt in range(retries + 1):
        try:
            return collector._get(url, headers=headers, timeout=timeout, data=data)
        except (URLError, OSError):
            if attempt == retries:
                raise
            time.sleep(wait)


def _crawl_site(domain, keys, *, max_pages=30):
    """One real on_page crawl, polled to completion or `_CRAWL_MAX_WAIT`.
    Returns `(result, task_id)` -- `result` is None if it never finished in
    time. `task_id` stays queryable against `/on_page/pages` afterwards, so
    it's threaded back through `run()` into the stored facts' `dims` --
    that's what lets the site-health UI later ask "which pages have this
    issue" without re-crawling."""
    hdr = _auth_headers(keys)
    posted = json.loads(_get_retry(
        f"{API}/on_page/task_post", headers=hdr, timeout=30,
        data=json.dumps([{"target": domain, "max_crawl_pages": max_pages,
                          "load_resources": False, "enable_javascript": False}]).encode()))
    task_id = ((posted.get("tasks") or [{}])[0]).get("id")
    if not task_id:
        raise RuntimeError("on_page task_post returned no task id")
    waited = 0
    while waited < _CRAWL_MAX_WAIT:
        time.sleep(_POLL_INTERVAL)
        waited += _POLL_INTERVAL
        try:
            d = json.loads(collector._get(f"{API}/on_page/summary/{task_id}", headers=hdr, timeout=30))
        except (URLError, OSError):
            continue   # a transient network blip mid-poll isn't a real failure
        result = ((d.get("tasks") or [{}])[0].get("result") or [None])[0]
        if result and result.get("crawl_progress") == "finished":
            return result, task_id
    return None, task_id


def pages_for_check(task_id: str, check: str, keys: dict, *, limit=100) -> list[dict]:
    """Real page-level drill-down for one on-page check, queried on demand
    (not pre-fetched per check on every crawl -- that would multiply the
    paid call count by ~17x for data most checks never get clicked into).
    DataForSEO keeps a finished on_page task's crawl data queryable by
    `task_id` for a limited window after completion; a task older than that
    (or from a since-cleared task) raises, surfaced to the admin rather than
    silently returning nothing."""
    if check in _PAGE_METRIC_ONLY:
        raise ValueError(f"'{check}' is a site-wide total from page_metrics, not a "
                          "per-page checks.* field -- there is no page-level drill-down for it")
    hdr = _auth_headers(keys)
    body = [{"id": task_id, "limit": limit, "filters": [["checks." + check, "=", True]]}]
    d = json.loads(collector._get(
        f"{API}/on_page/pages", headers=hdr, timeout=45, data=json.dumps(body).encode()))
    task = (d.get("tasks") or [{}])[0]
    if task.get("status_code") != 20000:
        raise RuntimeError(task.get("status_message") or "on_page/pages request failed")
    result = (task.get("result") or [{}])[0] or {}
    items = result.get("items") or []
    return [{"url": it.get("url"), "status_code": it.get("status_code")} for it in items]


def _lighthouse(url, keys, *, for_mobile=True):
    """One real Lighthouse run against `url`, polled to completion or
    `_LIGHTHOUSE_MAX_WAIT`. Returns the raw Lighthouse report, or None."""
    hdr = _auth_headers(keys)
    posted = json.loads(_get_retry(
        f"{API}/on_page/lighthouse/task_post", headers=hdr, timeout=30,
        data=json.dumps([{"url": url, "for_mobile": for_mobile}]).encode()))
    task_id = ((posted.get("tasks") or [{}])[0]).get("id")
    if not task_id:
        raise RuntimeError("lighthouse task_post returned no task id")
    waited = 0
    while waited < _LIGHTHOUSE_MAX_WAIT:
        time.sleep(_POLL_INTERVAL)
        waited += _POLL_INTERVAL
        try:
            d = json.loads(collector._get(
                f"{API}/on_page/lighthouse/task_get/json/{task_id}", headers=hdr, timeout=45))
        except Exception:                                            # noqa: BLE001
            continue   # a transient network blip mid-poll isn't a real failure
        task = (d.get("tasks") or [{}])[0]
        if task.get("status_code") == 20000:
            result = task.get("result")
            return result[0] if result else None
    return None


# page_metrics carries these four as site-wide aggregate counts (see the
# metric loop in run(), below) -- they are NOT entries in a page's own
# `checks{}` object, so /on_page/pages can't filter pages by them (live-
# confirmed: DataForSEO returns "Invalid Field: 'filters'." for
# checks.duplicate_title / checks.duplicate_description). The site-health UI
# renders these as count-only rows with no drill-down; pages_for_check()
# rejects them outright rather than making the doomed call.
_PAGE_METRIC_ONLY = ("broken_links", "duplicate_content", "duplicate_title", "duplicate_description")

# The exact on-page checks worth surfacing as named facts -- a subset of
# DataForSEO's full check list, chosen for being real, actionable SEO
# problems (not every one of the 100+ raw flags is meaningful on its own).
# The four in _PAGE_METRIC_ONLY are deliberately absent: they're written by
# the metric loop in run() instead, never by this checks{}-keyed loop.
_CRAWL_CHECKS = (
    "no_description", "no_title", "no_h1_tag", "no_image_alt", "no_image_title",
    "no_favicon", "broken_resources", "title_too_long", "title_too_short",
    "low_content_rate", "high_loading_time", "is_redirect", "is_4xx_code", "is_5xx_code",
)
_CWV_AUDITS = (
    ("largest-contentful-paint", "lcp_ms"), ("cumulative-layout-shift", "cls"),
    ("total-blocking-time", "tbt_ms"), ("first-contentful-paint", "fcp_ms"),
    ("speed-index", "speed_index_ms"), ("interactive", "tti_ms"),
)
_CWV_CATEGORIES = ("performance", "accessibility", "best-practices", "seo")


def run(session, workspace_id, keys, brands_with_domains, *, max_pages=30,
       day=None, log=None) -> dict:
    """`brands_with_domains`: [{"id","name","is_focus","domain"}, ...] (same
    shape core/seo_report.py::resolve_domains returns -- reuse that call)."""
    log = log or (lambda *_a: None)
    day = day or datetime.now(timezone.utc).date()
    facts = []
    crawled = cwv_measured = 0
    errors = []
    for b in brands_with_domains:
        domain = b.get("domain")
        if not domain:
            log(f"seo crawl · {b['name']} · no domain known, skipped")
            continue
        dims = {"domain": domain, "brand_id": b["id"], "is_focus": bool(b["is_focus"])}
        try:
            result, task_id = _crawl_site(domain, keys, max_pages=max_pages)
            if result is None:
                errors.append(f"{b['name']} crawl: timed out waiting for the crawl to finish")
                log(f"seo crawl · {b['name']} · crawl still running after "
                    f"{_CRAWL_MAX_WAIT}s, giving up for this run")
            else:
                pm = result.get("page_metrics") or {}
                checks = pm.get("checks") or {}
                domain_info = result.get("domain_info") or {}
                pages_crawled = (domain_info.get("crawl_status") or {}).get("pages_crawled") \
                    or domain_info.get("total_pages")
                crawl_dims = {**dims, "pages_crawled": pages_crawled, "task_id": task_id}
                if pm.get("onpage_score") is not None:
                    facts.append({"source": SOURCE, "entity_type": "site_crawl",
                                 "entity_ref": domain, "metric": "onpage_score",
                                 "day": day, "value": pm["onpage_score"], "dims": crawl_dims})
                for metric in _PAGE_METRIC_ONLY:
                    if pm.get(metric) is not None:
                        facts.append({"source": SOURCE, "entity_type": "site_crawl",
                                     "entity_ref": domain, "metric": metric, "day": day,
                                     "value": pm[metric], "dims": crawl_dims})
                for check in _CRAWL_CHECKS:
                    if checks.get(check) is not None:
                        facts.append({"source": SOURCE, "entity_type": "site_crawl",
                                     "entity_ref": domain, "metric": f"check_{check}",
                                     "day": day, "value": checks[check], "dims": crawl_dims})
                crawled += 1
                log(f"seo crawl · {b['name']} · {pages_crawled} pages, "
                    f"onpage_score {pm.get('onpage_score')}")
        except Exception as e:                                        # noqa: BLE001
            errors.append(f"{b['name']} crawl: {e}")
            log(f"seo crawl · {b['name']} · crawl failed ({e})")

        homepage = f"https://{domain}"
        try:
            lh = _lighthouse(homepage, keys)
            if lh is None:
                errors.append(f"{b['name']} lighthouse: timed out waiting for the audit to finish")
                log(f"seo crawl · {b['name']} · lighthouse still running after "
                    f"{_LIGHTHOUSE_MAX_WAIT}s, giving up for this run")
            else:
                cwv_dims = {**dims, "url": homepage}
                cats = lh.get("categories") or {}
                for cat in _CWV_CATEGORIES:
                    score = (cats.get(cat) or {}).get("score")
                    if score is not None:
                        facts.append({"source": SOURCE, "entity_type": "core_web_vitals",
                                     "entity_ref": homepage,
                                     "metric": f"{cat.replace('-', '_')}_score",
                                     "day": day, "value": round(score * 100, 1),
                                     "dims": cwv_dims})
                audits = lh.get("audits") or {}
                for audit_id, metric_name in _CWV_AUDITS:
                    v = (audits.get(audit_id) or {}).get("numericValue")
                    if v is not None:
                        facts.append({"source": SOURCE, "entity_type": "core_web_vitals",
                                     "entity_ref": homepage, "metric": metric_name,
                                     "day": day, "value": round(v, 1), "dims": cwv_dims})
                cwv_measured += 1
                log(f"seo crawl · {b['name']} · Core Web Vitals measured "
                    f"(performance {round((cats.get('performance') or {}).get('score', 0) * 100)})")
        except Exception as e:                                        # noqa: BLE001
            errors.append(f"{b['name']} lighthouse: {e}")
            log(f"seo crawl · {b['name']} · lighthouse failed ({e})")

    written = mf_repo.upsert_many(session, workspace_id, facts)
    return {"sites_crawled": crawled, "cwv_measured": cwv_measured,
           "facts_written": written, "errors": errors, "day": day.isoformat()}


def _dims(row):
    d = row["dims"]
    if isinstance(d, str):
        try:
            return json.loads(d or "{}")
        except ValueError:
            return {}
    return d or {}


def report(session, workspace_id: int) -> dict:
    """The latest crawl + Core Web Vitals snapshot on file, per brand."""
    from sqlalchemy import text as _sql

    latest_day = session.execute(_sql(
        "SELECT max(day) FROM metric_fact WHERE workspace_id = :ws AND source = :src"),
        {"ws": workspace_id, "src": SOURCE}).scalar()
    if not latest_day:
        return {"day": None, "brands": []}

    rows = session.execute(_sql("""
        SELECT entity_type, entity_ref, metric, value, dims
        FROM metric_fact WHERE workspace_id = :ws AND source = :src AND day = :day
    """), {"ws": workspace_id, "src": SOURCE, "day": latest_day}).mappings().all()

    by_brand: dict[int, dict] = {}

    def brand(bid, is_focus):
        return by_brand.setdefault(bid, {"id": bid, "is_focus": is_focus,
                                         "onpage_score": None, "pages_crawled": None,
                                         "task_id": None, "checks": {}, "cwv": {}, "scores": {}})

    for r in rows:
        dims = _dims(r)
        bid = dims.get("brand_id")
        if bid is None:
            continue
        entry = brand(bid, dims.get("is_focus", False))
        if r["entity_type"] == "site_crawl":
            entry["pages_crawled"] = dims.get("pages_crawled") or entry["pages_crawled"]
            entry["task_id"] = dims.get("task_id") or entry["task_id"]
            if r["metric"] == "onpage_score":
                entry["onpage_score"] = r["value"]
            elif r["metric"].startswith("check_"):
                entry["checks"][r["metric"][len("check_"):]] = r["value"]
            else:
                entry["checks"][r["metric"]] = r["value"]
        elif r["entity_type"] == "core_web_vitals":
            if r["metric"].endswith("_score"):
                entry["scores"][r["metric"][: -len("_score")]] = r["value"]
            else:
                entry["cwv"][r["metric"]] = r["value"]

    if by_brand:
        names = session.execute(_sql(
            "SELECT id, name FROM brand WHERE id = ANY(:ids)"),
            {"ids": list(by_brand)}).all()
        for bid, name in names:
            if bid in by_brand:
                by_brand[bid]["name"] = name
    for entry in by_brand.values():
        entry.setdefault("name", f"Brand {entry['id']}")

    brands = sorted(by_brand.values(), key=lambda b: (not b["is_focus"], b["id"]))
    return {"day": latest_day.isoformat(), "brands": brands}
