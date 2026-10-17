"""Technical SEO -- real keyword rankings + backlink profile per tracked
brand's own domain, via DataForSEO Labs (ranked_keywords) and the Backlinks
API (summary). Real, costed calls -- always an explicit admin action, same
posture as the Vantage AI-visibility panel, never scheduled. Written into
metric_fact (source="dataforseo_seo") so it rides the existing metric
warehouse (build plan P4.1) rather than a new table.

A brand with no known domain (BRAND_DOMAINS unset for it, and none found by
core/seo.py's own-domain search) is skipped, never guessed.
"""
import base64
import json
from datetime import datetime, timezone

from sqlalchemy import text as _sql

from core import collector, seo
from db.repositories import brands as brands_repo
from db.repositories import metric_fact as mf_repo

API = "https://api.dataforseo.com/v3"
SOURCE = "dataforseo_seo"


def _auth_headers(keys):
    auth = base64.b64encode(
        f"{keys['DATAFORSEO_LOGIN']}:{keys['DATAFORSEO_PASSWORD']}".encode()).decode()
    return {"Authorization": f"Basic {auth}", "Content-Type": "application/json"}


def _ranked_keywords(domain, keys, *, limit=20):
    hdr = _auth_headers(keys)
    body = [{"target": domain, "location_code": 2586, "language_code": "en",
            "limit": limit, "order_by": ["keyword_data.keyword_info.search_volume,desc"]}]
    d = json.loads(collector._get(
        f"{API}/dataforseo_labs/google/ranked_keywords/live",
        data=json.dumps(body).encode(), headers=hdr, timeout=45))
    result = ((d.get("tasks") or [{}])[0].get("result") or [{}])[0] or {}
    out = []
    for it in result.get("items") or []:
        kd = it.get("keyword_data") or {}
        info = kd.get("keyword_info") or {}
        se = (it.get("ranked_serp_element") or {}).get("serp_item") or {}
        out.append({"keyword": kd.get("keyword"), "search_volume": info.get("search_volume"),
                   "rank": se.get("rank_absolute"), "url": se.get("url")})
    return out


def _backlinks_summary(domain, keys):
    hdr = _auth_headers(keys)
    body = [{"target": domain, "include_subdomains": True}]
    d = json.loads(collector._get(
        f"{API}/backlinks/summary/live",
        data=json.dumps(body).encode(), headers=hdr, timeout=45))
    result = (d.get("tasks") or [{}])[0].get("result") or []
    if not result or not result[0]:
        return None
    r = result[0]
    return {"backlinks": r.get("backlinks"), "referring_domains": r.get("referring_domains"),
            "referring_main_domains": r.get("referring_main_domains"), "rank": r.get("rank")}


def resolve_domains(session, workspace_id: int, keys: dict) -> list[dict]:
    """Best-effort, never-guessed domain per tracked brand: the focus
    brand's own domain comes *only* from BRAND_DOMAINS (first one listed,
    set via Admin -> API keys -- a real domain, not derived) -- it never
    falls back to the heuristic below, because this domain is what actually
    gets crawled and billed for, and a wrong guess there means running a
    paid crawl/Lighthouse audit against someone else's site and presenting
    it as the client's own (live-verified real risk, 2026-09-12: with
    BRAND_DOMAINS unset, the heuristic's top hit for a brand can be a
    competitor's domain, not the brand's own). A competitor's domain comes
    from core.seo.domain_visibility()'s own-domain attribution (the real
    ranking result whose domain's SLD exactly matches that brand's name) --
    lower stakes since it only affects a competitor's own row, never run
    against without an explicit domain. A brand with neither is returned
    with domain=None and skipped by run()."""
    match_brands = brands_repo.match_rules(session, workspace_id)
    focus_domains = [d.strip() for d in (keys.get("BRAND_DOMAINS") or "").replace(",", " ").split()
                     if d.strip()]
    visibility = seo.domain_visibility(session, workspace_id, brands=match_brands)
    domain_by_brand = {
        b["id"]: (b["own_domains"][0]["domain"] if b["own_domains"] else None)
        for b in visibility["brands"]
    }
    out = []
    for b in match_brands:
        if b["is_focus"]:
            domain = focus_domains[0] if focus_domains else None
        else:
            domain = domain_by_brand.get(b["id"])
        out.append({"id": b["id"], "name": b["name"], "is_focus": bool(b["is_focus"]),
                   "domain": domain})
    return out


def run(session, workspace_id, keys, brands_with_domains, *, day=None, log=None) -> dict:
    """`brands_with_domains`: [{"id","name","is_focus","domain"}, ...]."""
    log = log or (lambda *_a: None)
    day = day or datetime.now(timezone.utc).date()
    facts = []
    keywords_pulled = backlinks_pulled = 0
    errors = []
    for b in brands_with_domains:
        domain = b.get("domain")
        if not domain:
            log(f"seo report · {b['name']} · no domain known, skipped")
            continue
        try:
            kws = _ranked_keywords(domain, keys)
            for kw in kws:
                if kw["rank"] is None or not kw["keyword"]:
                    continue
                facts.append({"source": SOURCE, "entity_type": "keyword",
                             "entity_ref": kw["keyword"], "metric": "rank",
                             "day": day, "value": kw["rank"],
                             "dims": {"domain": domain, "brand_id": b["id"],
                                      "is_focus": bool(b["is_focus"]),
                                      "search_volume": kw["search_volume"], "url": kw["url"]}})
            keywords_pulled += len(kws)
            log(f"seo report · {b['name']} · {len(kws)} keywords")
        except Exception as e:                                      # noqa: BLE001
            errors.append(f"{b['name']} keywords: {e}")
            log(f"seo report · {b['name']} · keywords failed ({e})")
        try:
            bl = _backlinks_summary(domain, keys)
            if bl:
                for metric in ("backlinks", "referring_domains",
                               "referring_main_domains", "rank"):
                    if bl.get(metric) is None:
                        continue
                    facts.append({"source": SOURCE, "entity_type": "backlinks",
                                 "entity_ref": domain, "metric": metric, "day": day,
                                 "value": bl[metric],
                                 "dims": {"brand_id": b["id"], "is_focus": bool(b["is_focus"])}})
                backlinks_pulled += 1
                log(f"seo report · {b['name']} · backlinks summary")
        except Exception as e:                                      # noqa: BLE001
            errors.append(f"{b['name']} backlinks: {e}")
            log(f"seo report · {b['name']} · backlinks failed ({e})")

    written = mf_repo.upsert_many(session, workspace_id, facts)
    return {"keywords_pulled": keywords_pulled, "backlinks_pulled": backlinks_pulled,
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
    """The latest snapshot on file, per brand: top keywords (by real search
    volume) and the backlink summary. Empty for a brand never run() for."""
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
                                         "keywords": [], "backlinks": {}})

    for r in rows:
        dims = _dims(r)
        bid = dims.get("brand_id")
        if bid is None:
            continue
        entry = brand(bid, dims.get("is_focus", False))
        if r["entity_type"] == "keyword":
            entry["keywords"].append({
                "keyword": r["entity_ref"], "rank": int(r["value"]) if r["value"] is not None else None,
                "search_volume": dims.get("search_volume"), "url": dims.get("url"),
            })
        elif r["entity_type"] == "backlinks":
            entry["backlinks"][r["metric"]] = (
                int(r["value"]) if r["value"] is not None else None)

    if by_brand:
        names = session.execute(_sql(
            "SELECT id, name FROM brand WHERE id = ANY(:ids)"),
            {"ids": list(by_brand)}).all()
        for bid, name in names:
            if bid in by_brand:
                by_brand[bid]["name"] = name

    for entry in by_brand.values():
        entry.setdefault("name", f"Brand {entry['id']}")
        entry["keywords"].sort(key=lambda k: -(k["search_volume"] or 0))

    brands = sorted(by_brand.values(), key=lambda b: (not b["is_focus"], b["id"]))
    return {"day": latest_day.isoformat(), "brands": brands}
