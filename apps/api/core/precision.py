"""Match-precision report (build plan §4 / P2.8).

Per brand, split by pattern class — ``safe`` (``needs_review = 0``) vs ``gated``
(``needs_review = 1``) — the labelled sample from ``gold_label`` / the review
queue, the point precision and its Wilson 95% interval. ``met`` is true only
when the interval's *lower* bound clears the target (≥ 0.95 safe, ≥ 0.85
gated) — a precision we cannot bound is not a precision we may claim.

The build plan gate is a 200-item sample; ``sample_size`` reports how many
labels exist so far against that target.
"""
from db.analytics import precision as q

from .stats import wilson

SAFE_TARGET = 0.95
GATED_TARGET = 0.85
SAMPLE_TARGET = 200


def _entry(cls, matched, labelled, correct):
    target = GATED_TARGET if cls == "gated" else SAFE_TARGET
    labelled = labelled or 0
    correct = correct or 0
    if labelled:
        p, lo, hi = wilson(correct, labelled)
    else:
        p = lo = hi = None
    return {
        "class": cls, "matched": matched, "labelled": labelled, "correct": correct,
        "precision": round(p, 4) if p is not None else None,
        "ci_low": round(lo, 4) if lo is not None else None,
        "ci_high": round(hi, 4) if hi is not None else None,
        "target": target,
        "met": bool(labelled) and lo is not None and lo >= target,
    }


def match_precision(db, ws) -> dict:
    per_brand: dict[str, dict] = {}
    for name, needs_review, matched, labelled, correct in q.match_precision_rows(db.session, ws):
        cls = "gated" if needs_review else "safe"
        per_brand.setdefault(name, {})[cls] = _entry(cls, matched, labelled, correct)

    brands = []
    for name, classes in sorted(per_brand.items()):
        safe = classes.get("safe") or _entry("safe", 0, 0, 0)
        gated = classes.get("gated") or _entry("gated", 0, 0, 0)
        brands.append({"brand": name, "safe": safe, "gated": gated})

    labelled_total = sum(b["safe"]["labelled"] + b["gated"]["labelled"] for b in brands)
    measured = [c for b in brands for c in (b["safe"], b["gated"]) if c["labelled"]]
    return {
        "brands": brands,
        "sample_size": labelled_total,
        "sample_target": SAMPLE_TARGET,
        "targets": {"safe": SAFE_TARGET, "gated": GATED_TARGET},
        "all_measured_met": bool(measured) and all(c["met"] for c in measured),
    }
