"""Product-line share of voice.

Deterministic keyword tagging of focus-brand mentions into product lines
(cards, auto finance, Islamic, remittances, the app, …). A mention can carry
more than one tag; one that matches nothing is counted as ``other``. The
keyword lists are the whole policy and are returned in the payload.
"""
import re

from db.analytics import scanners

from . import product_line_sets, vertical
from .insights import _age_days
from .stats import wilson

PRODUCT_LINES = product_line_sets.BANKING        # default / back-compat name


def _term_regex(term):
    star = term.endswith("*")
    core = re.escape(term[:-1] if star else term).replace(r"\ ", r"\s+")
    return r"\b" + core + ("" if star else r"\b")


def _line_regex(keywords):
    return re.compile("|".join(_term_regex(term) for term in keywords), re.I)


_SAMPLE_PER_LINE = 4


def _compiled(kind):
    return [(key, label, _line_regex(kws)) for key, label, kws in product_line_sets.SETS[kind]]


_COMPILED_BY = {kind: _compiled(kind) for kind in product_line_sets.SETS}
_COMPILED = _COMPILED_BY["banking"]
_KEYWORDS = {key: kws for key, _l, kws in PRODUCT_LINES}


def classify_text(text, kind="banking"):
    """The product-line keys a mention's text matches (may be empty)."""
    body = text or ""
    return [key for key, _label, rx in _COMPILED_BY[kind] if rx.search(body)]


def policy(kind="banking"):
    return {"vertical": kind,
            "lines": [{"key": k, "label": lbl, "keywords": kws}
                      for k, lbl, kws in product_line_sets.SETS[kind]]}


def _trim(text, limit=220):
    return re.sub(r"\s+", " ", (text or "")).strip()[:limit]


def scan(db, ws, days=None):
    """Product-line counts, share of voice and sentiment for the focus brand.

    Pure function of the corpus so the API returns it unchanged.
    """
    from db import repositories as repo
    kind = vertical.of(db, ws)
    compiled = _COMPILED_BY[kind]
    focus = repo.brands.focus_id_name(db.session, ws)
    if not focus:
        return {
            "coverage": {"focus_brand": None, "total": 0, "classified": 0,
                         "unclassified": 0, "multi_line": 0},
            "policy": policy(kind),
            "lines": [{"key": k, "label": lbl, "keywords": kws, "n": 0,
                       "share": 0.0, "pos": 0, "neu": 0, "neg": 0, "scored": 0,
                       "neg_share": None, "neg_lo": None, "neg_hi": None,
                       "sample": []} for k, lbl, kws in product_line_sets.SETS[kind]],
            "other": {"n": 0, "share": 0.0},
        }

    rows = scanners.product_line_rows(db.session, focus[0])

    agg = {key: {"n": 0, "pos": 0, "neu": 0, "neg": 0, "sample": []}
           for key, _label, _rx in compiled}
    total = classified = unclassified = multi = other_n = 0

    for iid, outlet, url, published_at, text, label in rows:
        if days is not None:
            age = _age_days(published_at)
            if age is None or not 0 <= age < days:
                continue
        if not (text or "").strip():
            continue
        total += 1
        keys = classify_text(text, kind)
        if not keys:
            unclassified += 1
            other_n += 1
            continue
        classified += 1
        if len(keys) > 1:
            multi += 1
        for key in keys:
            bucket = agg[key]
            bucket["n"] += 1
            if label in ("pos", "neu", "neg"):
                bucket[label] += 1
            if len(bucket["sample"]) < _SAMPLE_PER_LINE:
                bucket["sample"].append({
                    "id": iid, "outlet": outlet, "url": url,
                    "published_at": published_at, "sentiment": label,
                    "text": _trim(text),
                })

    tag_total = sum(bucket["n"] for bucket in agg.values()) or 1
    lines = []
    for key, label, _rx in compiled:
        bucket = agg[key]
        scored = bucket["pos"] + bucket["neu"] + bucket["neg"]
        p, lo, hi = wilson(bucket["neg"], scored) if scored else (None, None, None)
        lines.append({
            "key": key, "label": label,
            "keywords": next(k for kk, _l, k in product_line_sets.SETS[kind] if kk == key),
            "n": bucket["n"], "share": round(100 * bucket["n"] / tag_total, 1),
            "pos": bucket["pos"], "neu": bucket["neu"], "neg": bucket["neg"],
            "scored": scored, "neg_share": p, "neg_lo": lo, "neg_hi": hi,
            "sample": bucket["sample"],
        })
    lines.sort(key=lambda line: -line["n"])

    return {
        "coverage": {
            "focus_brand": focus[1], "total": total,
            "classified": classified, "unclassified": unclassified,
            "multi_line": multi,
        },
        "policy": policy(kind),
        "lines": lines,
        "other": {"n": other_n,
                  "share": round(100 * other_n / total, 1) if total else 0.0},
    }
