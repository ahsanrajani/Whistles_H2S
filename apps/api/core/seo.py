"""Real search-visibility data already sitting in `item` -- no new adapter,
no new API call. `dataforseo_serp` / `dataforseo_brand_serp` already collect
one row per organic Google result for each tracked brand's name, carrying
its real rank and domain (`item.raw_json`: `{"rank": int, "keyword": str}`,
see integrations/adapters/dataforseo.py). This reshapes that into "who
actually shows up when someone searches this brand's name" -- every domain
listed here genuinely ranked in a real search; nothing is estimated or
invented.
"""
import json
import re
from collections import defaultdict

from sqlalchemy import text as _sql

_SOURCES = ("dataforseo_brand_serp", "dataforseo_serp")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def _brand_slug(name: str) -> str | None:
    """Full brand-name slug (e.g. "Bank Alfalah" -> "bankalfalah"), matched
    against a domain's exact second-level label. A prior version matched on
    just the brand's first word as a substring anywhere in the domain --
    live-verified (2026-09-12, Hamza) to produce real false positives:
    "worldbank.org" / "lloydsbank.com" / "databank.worldbank.org" all
    matched "Bank Alfalah" on a bare "bank" substring, and "chasevalue.pk"
    matched "Chase Securities" on a bare "chase" prefix. Exact-SLD-equality
    against the full name fixes both without guessing -- a brand whose real
    domain doesn't literally spell its name (an abbreviation, e.g. "AKD
    Securities Limited" -> akdsl.com) won't auto-match here; it shows as
    unattributed third-party instead of risking a wrong attribution. Set
    BRAND_DOMAINS for the focus brand rather than relying on this guess."""
    slug = _slug(name)
    return slug if len(slug) >= 3 else None


def _domain_sld(domain: str) -> str:
    """The domain's second-level label -- "www.bankalfalah.com" and
    "bankalfalah.com" both -> "bankalfalah" -- so a stored "www." prefix
    doesn't hide a real match, and "databank.worldbank.org" compares as
    "databank" (its own leftmost label), not the registrable "worldbank"."""
    d = (domain or "").strip().lower()
    if d.startswith("www."):
        d = d[4:]
    return _slug(d.split(".")[0])


def domain_visibility(session, workspace_id: int, *, brands, limit=300) -> dict:
    """`brands`: [{"id","name","is_focus"}, ...] (db.repositories.brands
    .match_rules() shape). A domain is attributed to a brand when the
    brand's own name (slugged) appears in the domain or a sample URL --
    a plain, auditable rule, not a model guess. Everything else (social
    profiles, directories, press, Wikipedia) is left "third_party" --
    real pages that ranked, just not owned by any tracked brand.
    """
    rows = session.execute(_sql("""
        SELECT outlet, url, raw_json FROM item
        WHERE workspace_id = :ws AND source = ANY(:sources) AND outlet IS NOT NULL
        ORDER BY collected_at DESC LIMIT :limit
    """), {"ws": workspace_id, "sources": list(_SOURCES), "limit": limit}).fetchall()

    domains: dict[str, dict] = {}
    for outlet, url, raw_json in rows:
        try:
            raw = json.loads(raw_json or "{}")
        except ValueError:
            raw = {}
        rank = raw.get("rank")
        if rank is None:
            continue
        entry = domains.setdefault(
            outlet, {"best_rank": rank, "appearances": 0, "sample_url": url})
        entry["best_rank"] = min(entry["best_rank"], rank)
        entry["appearances"] += 1

    tokened = [(b["id"], _brand_slug(b["name"])) for b in brands]
    for domain, entry in domains.items():
        sld = _domain_sld(domain)
        entry["brand_id"] = next(
            (bid for bid, tok in tokened if tok and tok == sld), None)

    by_brand: dict[int, list] = defaultdict(list)
    third_party = []
    for domain, entry in sorted(domains.items(), key=lambda kv: kv[1]["best_rank"]):
        row = {"domain": domain, "best_rank": entry["best_rank"],
               "appearances": entry["appearances"], "sample_url": entry["sample_url"]}
        if entry["brand_id"] is not None:
            by_brand[entry["brand_id"]].append(row)
        else:
            third_party.append(row)

    out_brands = [
        {"id": b["id"], "name": b["name"], "is_focus": bool(b["is_focus"]),
         "own_domains": by_brand.get(b["id"], [])}
        for b in brands
    ]
    return {"brands": out_brands, "third_party": third_party[:40],
           "total_domains": len(domains), "total_results": len(rows)}
