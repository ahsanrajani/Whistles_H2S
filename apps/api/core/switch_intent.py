"""Switch-intent detection: a deterministic "this customer is about to leave" score.

Same discipline as ``core.scam`` / ``core.triage`` — every signal is a named rule
with a fixed integer weight, the score is the sum of the *distinct* signals a
mention trips, and ``scan`` returns the whole policy so the ranking is auditable.
No model.

Corpus: client-safe mentions of the **focus brand** (a switch signal is about
*its* customer churning), deduped to one row per source item.
"""
import re
from collections import defaultdict

from db import repositories as repo
from db.analytics import scanners

from .insights import PERIOD_LABELS, PERIODS, _age_days

# (key, label, weight, pattern) — matched against the mention text.
TEXT_SIGNALS = [
    ("closure", "Explicit account closure", 4,
     r"\b(?:clos(?:e|ing|ure\s+of)\s+(?:my|the|this)\s+account"
     r"|account\s+(?:is\s+)?clos(?:ed|ing)"
     r"|shift(?:ing)?\s+my\s+salary\s+account"
     r"|mov(?:e|ing)\s+my\s+salary(?:\s+account)?"
     r"|port(?:ing)?\s+my\s+salary"
     r"|withdraw(?:ing)?\s+(?:all\s+)?my\s+(?:money|funds)\s+and\s+(?:leav|clos))\b"),
    ("switch_verb", "Switching-banks language", 3,
     r"\b(?:switch(?:ing)?\s+banks?|chang(?:e|ing)\s+banks?|mov(?:e|ing)\s+banks?"
     r"|taking\s+my\s+(?:business|money|account|salary)\s+elsewhere"
     r"|had\s+enough\s+of\s+this\s+bank|done\s+with\s+this\s+bank|last\s+straw)\b"),
    ("rival_preference", "Prefers a rival", 2,
     r"\b(?:should\s+have\s+(?:gone|opened|banked)\s+with"
     r"|wish\s+i\s+(?:had\s+)?(?:chosen|picked|opened\s+with)"
     r"|better\s+(?:service|rates?|app|experience)\s+(?:at|with|from)\s+\w"
     r"|regret\s+(?:choosing|opening|banking))\b"),
    ("warn_others", "Recommending against", 2,
     r"\b(?:don'?t\s+(?:open|use|choose|bank\s+with)|avoid\s+this\s+bank"
     r"|(?:would\s+)?not\s+recommend|stay\s+away\s+from"
     r"|warn(?:ing)?\s+(?:everyone|others|people|you\s+all))\b"),
    ("ultimatum", "Ultimatum / deadline", 2,
     r"(?:if\s+(?:this|it|my\s+issue)\s+(?:is\s+)?not\s+(?:resolved|fixed|sorted)"
     r"[^.\n]{0,40}(?:clos|switch|leav|mov)"
     r"|give\s+you\s+\d+\s+(?:hours?|days?)[^.\n]{0,30}(?:\bor\b|before)"
     r"|fix\s+this\s+or\s+i\s+(?:will|am))"),
    ("tenure", "Long-tenured customer at risk", 2,
     r"\b(?:(?:customer|account\s*holder|banking\s+with\s+\w[\w ]{0,20})\s+"
     r"(?:for|since)\s+(?:\d+\s+years?|20\d\d)"
     r"|(?:loyal|old|long[-\s]?time|\d+[-\s]year)\s+customer)\b"),
]

# (key, label, weight) — from the row's own metadata, not its text.
CONTEXT_SIGNALS = [
    ("negative", "Negative sentiment", 1),
    ("complaint_type", "Classified complaint / fraud", 1),
]

# (key, label, minimum score). Checked high → low; first match wins.
BANDS = [
    ("high", "High", 7),
    ("likely", "Likely", 4),
    ("watch", "Watch", 2),
    ("none", "None", 0),
]

# A rival named next to a move verb — pattern is workspace-specific so it is
# assembled in scan() from the competitor names and passed to score_row().
_COMPETITOR_LEAD = (
    r"(?:switch|shift|mov|chang|transferr?|go|going|went|open(?:ed|ing)?)\w*"
    r"[^.\n]{0,25}?"
)
COMPETITOR_SIGNAL = ("to_competitor", "Naming a bank to move to", 4)

_COMPILED = [(key, label, weight, re.compile(pattern, re.I))
             for key, label, weight, pattern in TEXT_SIGNALS]
_WEIGHT = {key: weight for key, _l, weight, _p in TEXT_SIGNALS}
_WEIGHT.update({key: weight for key, _l, weight in CONTEXT_SIGNALS})
_WEIGHT[COMPETITOR_SIGNAL[0]] = COMPETITOR_SIGNAL[2]
_MAX_SCORE = (sum(w for _k, _l, w, _p in TEXT_SIGNALS)
              + COMPETITOR_SIGNAL[2] + sum(w for _k, _l, w in CONTEXT_SIGNALS))
_QUEUE_LIMIT = 120
_SCAN_LIMIT = 8000


def band_of(score):
    for key, _label, threshold in BANDS:
        if score >= threshold:
            return key
    return "none"


def competitor_pattern(names):
    """A compiled `move-verb … <rival name>` regex, or None when no rivals."""
    cleaned = [re.escape(name.strip()) for name in names if name and name.strip()]
    if not cleaned:
        return None
    return re.compile(_COMPETITOR_LEAD + r"(?:" + "|".join(cleaned) + r")", re.I)


def score_row(text, *, category=None, sentiment=None, rival_rx=None):
    """(score, [signal keys]) for one focus-brand mention. Deterministic."""
    body = text or ""
    hits = [key for key, _l, _w, rx in _COMPILED if rx.search(body)]
    if rival_rx is not None and rival_rx.search(body):
        hits.append(COMPETITOR_SIGNAL[0])
    if sentiment == "neg":
        hits.append("negative")
    if category in ("complaint", "fraud"):
        hits.append("complaint_type")
    return sum(_WEIGHT[key] for key in hits), hits


def policy():
    return {
        "signals": (
            [{"key": k, "label": lbl, "weight": w, "kind": "text"}
             for k, lbl, w, _rx in _COMPILED]
            + [{"key": COMPETITOR_SIGNAL[0], "label": COMPETITOR_SIGNAL[1],
                "weight": COMPETITOR_SIGNAL[2], "kind": "text"}]
            + [{"key": k, "label": lbl, "weight": w, "kind": "context"}
               for k, lbl, w in CONTEXT_SIGNALS]
        ),
        "bands": [{"key": k, "label": lbl, "min_score": t} for k, lbl, t in BANDS],
        "max_score": _MAX_SCORE,
    }


def _trim(text, limit=240):
    return re.sub(r"\s+", " ", (text or "")).strip()[:limit]


def scan(db, ws, days=None):
    """Score focus-brand mentions for switch intent and rank them.

    Pure function of the corpus, so the API returns it unchanged.
    """
    focus = repo.brands.focus_id_name(db.session, ws)
    competitors = repo.brands.competitor_names(db.session, ws)
    rival_rx = competitor_pattern(competitors)

    empty = {
        "coverage": {"scanned": 0, "focus_brand": focus[1] if focus else None,
                     "competitors": competitors,
                     "note": "Client-safe mentions of the focus brand only."},
        "policy": policy(),
        "summary": {"scanned": 0, "flagged": 0, "high": 0, "likely": 0, "watch": 0},
        "signals": [{"key": s["key"], "label": s["label"], "weight": s["weight"],
                     "kind": s["kind"], "n": 0} for s in policy()["signals"]],
        "queue": [], "queue_total": 0,
    }
    if not focus:
        return empty

    rows = scanners.switch_intent_rows(db.session, focus[0], _SCAN_LIMIT)

    scanned = flagged = 0
    signal_counts = {s["key"]: 0 for s in policy()["signals"]}
    band_counts = {key: 0 for key, _l, _t in BANDS}
    queue = []

    for (iid, surface, source, outlet, author, published_at, url,
         text, rating, sentiment, category) in rows:
        if days is not None:
            age = _age_days(published_at)
            if age is None or not 0 <= age < days:
                continue
        if not (text or "").strip():
            continue

        scanned += 1
        score, hits = score_row(text, category=category, sentiment=sentiment,
                                rival_rx=rival_rx)
        band = band_of(score)
        band_counts[band] += 1
        for key in hits:
            signal_counts[key] += 1

        if score >= 2:
            flagged += 1
            queue.append({
                "id": iid, "surface": surface, "source": source, "outlet": outlet,
                "author": author, "published_at": published_at, "url": url,
                "text": _trim(text), "rating": rating, "sentiment": sentiment,
                "type": category, "score": score, "band": band, "signals": hits,
                "competitor_named": COMPETITOR_SIGNAL[0] in hits,
            })

    queue.sort(key=lambda r: (-r["score"], r["published_at"] or "", -r["id"]))

    return {
        "coverage": {
            "scanned": scanned,
            "focus_brand": focus[1],
            "competitors": competitors,
            "note": "Client-safe mentions of the focus brand only. Rival-name "
                    "matching uses the workspace's competitor brands.",
        },
        "policy": policy(),
        "summary": {
            "scanned": scanned,
            "flagged": flagged,
            "high": band_counts["high"],
            "likely": band_counts["likely"],
            "watch": band_counts["watch"],
        },
        "signals": [{"key": s["key"], "label": s["label"], "weight": s["weight"],
                     "kind": s["kind"], "n": signal_counts[s["key"]]}
                    for s in policy()["signals"]],
        "queue": queue[:_QUEUE_LIMIT],
        "queue_total": flagged,
    }
