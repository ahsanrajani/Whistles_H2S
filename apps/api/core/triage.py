"""Complaint severity triage: a deterministic escalation-risk score.

Same discipline as ``core.scam`` — every signal is a named rule with a fixed
integer weight, the score is the sum of the *distinct* signals a complaint
trips, and ``scan`` returns the whole policy so the ranking is auditable. No
model, no learned threshold, no "priority" the operator can't trace back to a
rule.

Corpus: client-safe mentions that already read as a complaint — classified
``complaint`` or ``fraud``, or negative sentiment, or a 1–2★ app review — with
one row per source item (the focus brand's row wins when a story names several).
"""
import json
import re
from collections import defaultdict

from db.analytics import scanners

from .insights import PERIOD_LABELS, PERIODS, _age_days

# (key, label, weight, pattern) — matched against the complaint text.
TEXT_SIGNALS = [
    ("regulator", "Regulator / ombudsman named", 4,
     r"\b(?:banking\s+mohtasib|\bmohtasib\b|state\s+bank(?:\s+of\s+pakistan)?|\bsbp\b"
     r"|\bsecp\b|consumer\s+court|federal\s+ombudsman|wafaqi\s+mohtasib"
     r"|complain(?:t|ed|ing)?\s+to\s+(?:the\s+)?(?:sbp|state\s+bank|mohtasib|regulator))\b"),
    ("legal", "Legal action threatened", 3,
     r"\b(?:legal\s+(?:action|notice)|\blawyer\b|\bsue\b|\bsuing\b"
     r"|take\s+(?:you|this)\s+to\s+court|file\s+(?:an?\s+)?(?:f\.?i\.?r|case)|defamation)\b"),
    ("financial_loss", "Unrecovered financial loss", 3,
     r"\b(?:unauthori[sz]ed\s+(?:transaction|debit|payment|withdrawal)"
     r"|money\s+(?:deducted|debited|gone|stolen|lost|not\s+reversed)"
     r"|amount\s+(?:deducted|debited)\s+but\s+not"
     r"|fraudulent(?:ly)?\s+(?:charged|debited|withdrawn)"
     r"|lost\s+(?:pkr|rs\.?|rupees)|scammed\s+out\s+of)\b"),
    ("public_escalation", "Threat to go public", 2,
     r"\b(?:going\s+to\s+(?:post|share|tweet|expose)|will\s+(?:post|share|expose|escalate)"
     r"|tag(?:ging)?\s+(?:the\s+)?media|screenshots?\s+(?:attached|below|here)"
     r"|make\s+this\s+viral|every(?:one|where)\s+should\s+know)\b"),
    ("hardship", "Vulnerable / hardship context", 2,
     r"\b(?:salary\s+(?:account|stuck|not\s+credited)|pension|medical\s+emergency"
     r"|in\s+the\s+hospital|stuck\s+abroad|no\s+money\s+(?:for|to)"
     r"|elderly\s+(?:parent|mother|father)|school\s+fee)\b"),
    ("unresolved", "Unresolved or repeat contact", 2,
     r"\b(?:still\s+(?:not|un)\s*resolved|no\s+(?:response|reply|resolution|update)"
     r"|(?:second|third|3rd|2nd|fourth)\s+time|(?:days|weeks?|months?)\s+(?:now|and\s+counting)"
     r"|complaint\s+(?:number|no\.?|#)|ticket\s+(?:number|no\.?|#)"
     r"|follow(?:ing)?\s*up\s+since)\b"),
    ("access_blocked", "Account access blocked", 2,
     r"\b(?:account\s+(?:blocked|locked|frozen|suspended|disabled)"
     r"|can'?t\s+(?:log\s*in|access|withdraw|transfer)|locked\s+out"
     r"|card\s+(?:blocked|declined|not\s+working))\b"),
    ("churn", "Churn / reputation language", 1,
     r"\b(?:clos(?:e|ing)\s+my\s+account|switch(?:ing)?\s+to\s+another\s+bank"
     r"|worst\s+bank|never\s+(?:again|using|use)|shame\s+on|pathetic\s+service)\b"),
]

# (key, label, weight) — derived from the row's own metadata, not its text.
CONTEXT_SIGNALS = [
    ("fraud_type", "Classified as fraud", 2),
    ("one_star", "1-star app review", 2),
    ("two_star", "2-star app review", 1),
    ("negative", "Negative sentiment", 1),
]

# (key, label, minimum score). Checked high → low; first match wins.
BANDS = [
    ("critical", "Critical", 8),
    ("high", "High", 5),
    ("elevated", "Elevated", 3),
    ("watch", "Watch", 1),
    ("routine", "Routine", 0),
]

_COMPILED = [(key, label, weight, re.compile(pattern, re.I))
             for key, label, weight, pattern in TEXT_SIGNALS]
_WEIGHT = {key: weight for key, _l, weight, _p in TEXT_SIGNALS}
_WEIGHT.update({key: weight for key, _l, weight in CONTEXT_SIGNALS})
_MAX_SCORE = (sum(w for _k, _l, w, _p in TEXT_SIGNALS)
              + _WEIGHT["fraud_type"] + _WEIGHT["one_star"] + _WEIGHT["negative"])
_QUEUE_LIMIT = 120
_SCAN_LIMIT = 8000


def band_of(score):
    for key, _label, threshold in BANDS:
        if score >= threshold:
            return key
    return "routine"


def score_row(text, *, category=None, rating=None, sentiment=None):
    """(score, [signal keys]) for one complaint. Deterministic."""
    body = text or ""
    hits = [key for key, _l, _w, rx in _COMPILED if rx.search(body)]
    if category == "fraud":
        hits.append("fraud_type")
    if rating == 1:
        hits.append("one_star")
    elif rating == 2:
        hits.append("two_star")
    if sentiment == "neg":
        hits.append("negative")
    return sum(_WEIGHT[key] for key in hits), hits


def policy():
    return {
        "signals": (
            [{"key": k, "label": lbl, "weight": w, "kind": "text"}
             for k, lbl, w, _rx in _COMPILED]
            + [{"key": k, "label": lbl, "weight": w, "kind": "context"}
               for k, lbl, w in CONTEXT_SIGNALS]
        ),
        "bands": [{"key": k, "label": lbl, "min_score": t} for k, lbl, t in BANDS],
        "max_score": _MAX_SCORE,
    }


def _trim(text, limit=240):
    return re.sub(r"\s+", " ", (text or "")).strip()[:limit]


def scan(db, ws, days=None):
    """Score complaint-shaped mentions for escalation risk and rank them.

    Pure function of the workspace corpus so the API can return it unchanged.
    """
    rows = scanners.triage_rows(db.session, ws, _SCAN_LIMIT)

    # One row per source item — the focus brand's mention represents a shared story.
    best = {}
    for row in rows:
        iid, is_focus, needs_review = row[0], row[3], row[14]
        rank = (0 if is_focus else 1, needs_review, iid)
        if iid not in best or rank < best[iid][0]:
            best[iid] = (rank, row)

    scanned = flagged = 0
    signal_counts = {key: 0 for key in _WEIGHT}
    band_counts = {key: 0 for key, _l, _t in BANDS}
    by_brand = defaultdict(lambda: {"brand": None, "focus": False, "scanned": 0,
                                    "flagged": 0, "high": 0})
    queue = []

    for _rank, row in best.values():
        (iid, _bid, brand, is_focus, surface, source, outlet, author,
         published_at, url, text, rating, sentiment, category, needs_review) = row
        if days is not None:
            age = _age_days(published_at)
            if age is None or not 0 <= age < days:
                continue
        if not (text or "").strip():
            continue

        scanned += 1
        score, hits = score_row(text, category=category, rating=rating,
                                sentiment=sentiment)
        band = band_of(score)
        band_counts[band] += 1
        for key in hits:
            signal_counts[key] += 1

        bucket = by_brand[brand]
        bucket["brand"] = brand
        bucket["focus"] = bool(is_focus)
        bucket["scanned"] += 1

        if score >= 1:
            flagged += 1
            bucket["flagged"] += 1
            if band in ("high", "critical"):
                bucket["high"] += 1
            queue.append({
                "id": iid, "brand": brand, "focus": bool(is_focus),
                "surface": surface, "source": source, "outlet": outlet,
                "author": author, "published_at": published_at, "url": url,
                "text": _trim(text), "rating": rating, "sentiment": sentiment,
                "type": category, "needs_review": needs_review,
                "score": score, "band": band, "signals": hits,
            })

    queue.sort(key=lambda r: (-r["score"], r["published_at"] or "", -r["id"]))
    brands = sorted(by_brand.values(),
                    key=lambda b: (not b["focus"], -b["flagged"], b["brand"] or ""))

    return {
        "coverage": {
            "scanned": scanned,
            "focus_brand": next((b["brand"] for b in brands if b["focus"]), None),
            "note": "Client-safe mentions that already read as a complaint "
                    "(classified complaint/fraud, negative sentiment, or 1–2★).",
        },
        "policy": policy(),
        "summary": {
            "scanned": scanned,
            "flagged": flagged,
            "critical": band_counts["critical"],
            "high": band_counts["high"],
            "elevated": band_counts["elevated"],
            "watch": band_counts["watch"],
            "focus_flagged": sum(b["flagged"] for b in brands if b["focus"]),
        },
        "signals": (
            [{"key": k, "label": lbl, "weight": w, "kind": "text", "n": signal_counts[k]}
             for k, lbl, w, _rx in _COMPILED]
            + [{"key": k, "label": lbl, "weight": w, "kind": "context",
                "n": signal_counts[k]} for k, lbl, w in CONTEXT_SIGNALS]
        ),
        "queue": queue[:_QUEUE_LIMIT],
        "queue_total": flagged,
        "by_brand": brands,
    }
