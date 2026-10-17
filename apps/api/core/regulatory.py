"""Regulatory watch: a dated feed of SBP / Banking Mohtasib / PSX notices.

The ``regulatory_watch`` collector stores these as ``regulatory``-surface items
with no mention. This module reads them back, tags each notice with a topic
(keyword rules) and any workspace brand it names, and returns a feed the API
hands straight to the UI. Deterministic: the topic lexicon is returned in the
payload.
"""
import json
import re

# (key, label, keyword-alternation pattern), case-insensitive.
TOPICS = [
    ("enforcement", "Enforcement & penalties",
     r"penalt|fine[ds]?\b|monetary\s+penalty|sanction|show[-\s]?cause|action\s+against"
     r"|violation|non[-\s]?compliance|imposed\s+a?\s*fine"),
    ("consumer", "Consumer protection",
     r"consumer\s+protection|complaint|grievance|mis[-\s]?sell|unfair|fair\s+treatment"
     r"|refund|redress|dispute\s+resolution"),
    ("digital", "Digital banking & payments",
     r"digital\s+bank|\braast\b|\bibft\b|instant\s+payment|e-?money|\bemi\b|payment\s+system"
     r"|open\s+bank|\bapi\b|branchless|mobile\s+wallet|\bqr\b"),
    ("cyber", "Cybersecurity & fraud",
     r"cyber|information\s+security|\bict\b\s+security|data\s+breach|phishing|fraud"
     r"|social\s+engineering|resilience|technology\s+risk"),
    ("aml", "AML / CFT & KYC",
     r"\baml\b|\bcft\b|money\s+laundering|terror\s+financing|\bkyc\b|\bcdd\b|beneficial\s+owner"
     r"|sanctions\s+screening|suspicious\s+transaction"),
    ("prudential", "Prudential & capital",
     r"capital\s+adequacy|\bcar\b|basel|provisioning|liquidity|\bnpls?\b|exposure\s+limit"
     r"|prudential\s+regulation|minimum\s+capital"),
    ("fx", "FX & remittances",
     r"exchange\s+rate|foreign\s+exchange|\bfx\b|remittanc|roshan\s+digital|\brda\b"
     r"|exporters?|import\s+payment|home\s+remittance"),
    ("rates", "Policy rate & monetary",
     r"policy\s+rate|monetary\s+policy|\bkibor\b|discount\s+rate|inflation\s+target"
     r"|open\s+market\s+operation"),
    ("markets", "Market & listing (PSX)",
     r"listing|de[-\s]?list|trading\s+halt|circuit\s+breaker|book\s+building|\bipo\b"
     r"|corporate\s+action|board\s+meeting|dividend|announcement"),
]

_COMPILED = [(key, label, re.compile(pattern, re.I)) for key, label, pattern in TOPICS]
_KEYWORDS = {key: [t.strip() for t in pattern.split("|")]
             for key, _label, pattern in TOPICS}
_FEED_LIMIT = 150


def classify_text(text):
    """Topic keys a notice's text matches (may be empty)."""
    body = text or ""
    return [key for key, _label, rx in _COMPILED if rx.search(body)]


def policy():
    return {"topics": [{"key": k, "label": lbl, "keywords": _KEYWORDS[k]}
                       for k, lbl, _rx in _COMPILED]}


def _trim(text, limit=320):
    return re.sub(r"\s+", " ", (text or "")).strip()[:limit]


def summarize(db, ws):
    """The regulatory feed for a workspace, tagged by topic and brand.

    Pure function of the stored ``regulatory_watch`` items so the API returns it
    unchanged.
    """
    from db import repositories as repo
    brands = [(n, bool(f)) for n, f in repo.brands.name_focus_all(db.session, ws)]
    brand_rx = {name: re.compile(r"\b" + re.escape(name) + r"\b", re.I)
                for name, _focus in brands}
    focus_name = next((name for name, focus in brands if focus), None)

    from db.analytics import scanners
    rows = scanners.regulatory_item_rows(db.session, ws, _FEED_LIMIT)

    notices = []
    regulator_n = {}
    topic_n = {key: 0 for key, _l, _rx in _COMPILED}
    brand_hit_n = {name: 0 for name, _f in brands}
    for iid, outlet, url, published_at, title, body, raw_json in rows:
        try:
            raw = json.loads(raw_json) if raw_json else {}
        except (TypeError, ValueError):
            raw = {}
        regulator = (raw.get("regulator") if isinstance(raw, dict) else None) or outlet or "—"
        text = " ".join(part for part in (title, body) if part)
        topics = classify_text(text)
        named = sorted(name for name, rx in brand_rx.items() if rx.search(text))

        regulator_n[regulator] = regulator_n.get(regulator, 0) + 1
        for key in topics:
            topic_n[key] += 1
        for name in named:
            brand_hit_n[name] += 1

        notices.append({
            "id": iid, "regulator": regulator, "url": url,
            "published_at": published_at, "title": _trim(title, 240),
            "summary": _trim(body) if body and body != title else "",
            "topics": topics, "brands": named,
            "names_focus": bool(focus_name and focus_name in named),
        })

    return {
        "focus_brand": focus_name,
        "policy": policy(),
        "total": len(notices),
        "regulators": sorted(({"name": name, "n": n}
                              for name, n in regulator_n.items()),
                             key=lambda r: (-r["n"], r["name"])),
        "topics": [{"key": k, "label": lbl, "n": topic_n[k]}
                   for k, lbl, _rx in _COMPILED],
        "brand_hits": sorted(({"brand": name, "n": n}
                              for name, n in brand_hit_n.items() if n),
                             key=lambda r: (-r["n"], r["brand"])),
        "notices": notices,
    }
