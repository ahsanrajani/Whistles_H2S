"""Comment-level scam and brand-abuse signal scoring.

Deterministic only. Each signal is a named regex with a fixed integer weight; a
comment's score is the sum of the weights of the *distinct* signals it trips. No
model, no learned threshold — the weights and severity bands below are the whole
policy, and ``scan`` returns them to the UI so every flag is auditable.

Scope: comments on the focus brand's own Facebook/Instagram channels (Bright Data
and Meta Graph). Commenter identity is only ever handled as the one-way
``raw_json.actor_hash`` written at collection time, or a hash of the display name
when that is all the provider gave — never the raw handle.
"""
import hashlib
import json
import re
from collections import defaultdict

from db.analytics import scanners

from .insights import PERIOD_LABELS, PERIODS, _age_days

# (key, label, weight, pattern). Weight is the score contribution when the
# pattern matches at least once in a comment body. List order is display order.
SIGNALS = [
    ("whatsapp", "WhatsApp contact", 4,
     r"\bwhat'?s\s?app\b|\bwa\.me/|chat\.whatsapp\.com"),
    ("phone", "Phone number", 3,
     r"(?<!\w)(?:\+?92[-\s]?|0)?3\d{2}[-\s]?\d{7}(?!\w)"
     r"|(?<!\w)\+?\d[\d\s().-]{8,}\d(?!\w)"),
    ("short_link", "Shortened link", 3,
     r"\b(?:bit\.ly|tinyurl\.com|t\.co|cutt\.ly|rb\.gy|is\.gd|goo\.gl|ow\.ly"
     r"|rebrand\.ly|linktr\.ee)/\S+"),
    ("telegram", "Telegram handle", 3, r"\bt\.me/\S+|\btelegram\b"),
    ("payout_lure", "Payout / prize lure", 2,
     r"\b(?:you(?:'ve| have)?\s+won|lucky\s+draw|lottery|prize\s+money|congratulations?"
     r"|claim\s+your|reward\s+points?|cash\s?back\s+offer|refund\s+department)\b"),
    ("contact_lure", "Off-channel contact lure", 2,
     r"\b(?:dm\s+me|inbox\s+me|message\s+me\s+(?:privately|directly)"
     r"|contact\s+(?:our\s+)?(?:agent|admin|manager|representative)"
     r"|help\s?line\s+number|customer\s+care\s+number)\b"),
    ("impersonation", "Support impersonation", 2,
     r"\b(?:official\s+(?:support|help\s?desk|whats\s?app)|verified\s+team"
     r"|account\s+(?:officer|manager|department)\s+(?:here|contact)"
     r"|quick\s+support\s+team)\b"),
]

# (key, label, minimum score). Checked high → low; first match wins.
SEVERITY_BANDS = [
    ("high", "High", 7),
    ("elevated", "Elevated", 4),
    ("low", "Low", 1),
    ("clear", "Clear", 0),
]

# Owned-channel comment sources. Bright Data comment rows are all comments; the
# Meta sources also carry posts, so raw_json.kind is checked per row.
COMMENT_SOURCES = (
    "brightdata_facebook_comments", "brightdata_instagram_comments",
    "meta_facebook", "meta_instagram",
)

_COMPILED = [(key, label, weight, re.compile(pattern, re.I))
             for key, label, weight, pattern in SIGNALS]
_WEIGHT = {key: weight for key, _label, weight, _pattern in SIGNALS}
_MAX_SCORE = sum(_WEIGHT.values())
_FLAGGED_LIMIT = 100
_OFFENDER_LIMIT = 20
_SCAN_LIMIT = 6000


def score_text(text):
    """(score, [signal keys]) for one comment body. Deterministic."""
    body = text or ""
    hits = [key for key, _label, _weight, rx in _COMPILED if rx.search(body)]
    return sum(_WEIGHT[key] for key in hits), hits


def severity_of(score):
    for key, _label, threshold in SEVERITY_BANDS:
        if score >= threshold:
            return key
    return "clear"


def _actor_ref(raw, author):
    """A stable, non-reversible id for one commenter, or None."""
    stored = raw.get("actor_hash")
    if stored:
        return "a:" + str(stored)[:16]
    if author and author.strip():
        return "n:" + hashlib.sha256(author.strip().lower().encode()).hexdigest()[:16]
    return None


def _trim(text, limit=220):
    return re.sub(r"\s+", " ", (text or "")).strip()[:limit]


def policy():
    """The full, static scoring policy — also embedded in every scan payload."""
    return {
        "signals": [{"key": k, "label": lbl, "weight": w}
                    for k, lbl, w, _rx in _COMPILED],
        "bands": [{"key": k, "label": lbl, "min_score": t}
                  for k, lbl, t in SEVERITY_BANDS],
        "max_score": _MAX_SCORE,
    }


def scan(db, ws, surface=None, days=None):
    """Score every owned-channel comment for scam signals and aggregate.

    Pure function of the workspace's stored comments: same corpus in, same
    payload out, so the API can return it without recomputation.
    """
    rows = scanners.scam_comment_rows(db.session, ws, list(COMMENT_SOURCES),
                                      _SCAN_LIMIT, surface)

    scanned = with_actor = 0
    seen_sources = set()
    signal_counts = {key: 0 for key, _lbl, _w, _rx in _COMPILED}
    band_counts = {key: 0 for key, _lbl, _t in SEVERITY_BANDS}
    flagged = []
    offenders = defaultdict(lambda: {
        "actor_ref": None, "comments": 0, "flagged": 0, "score_sum": 0,
        "max_score": 0, "surfaces": set(), "signals": set(), "sample": "",
    })

    for (iid, i_surface, source, outlet, author, published_at, url,
         title, body, raw_json, brand) in rows:
        try:
            raw = json.loads(raw_json) if raw_json else {}
        except (TypeError, ValueError):
            raw = {}
        if not isinstance(raw, dict) or raw.get("kind") != "comment":
            continue
        text = " ".join(part for part in (title, body) if part)
        if not text.strip():
            continue
        if days is not None:
            age = _age_days(published_at)
            if age is None or not 0 <= age < days:
                continue

        scanned += 1
        seen_sources.add(source)
        score, hits = score_text(text)
        for key in hits:
            signal_counts[key] += 1
        severity = severity_of(score)
        band_counts[severity] += 1

        actor_ref = _actor_ref(raw, author)
        if actor_ref:
            with_actor += 1
            bucket = offenders[actor_ref]
            bucket["actor_ref"] = actor_ref
            bucket["comments"] += 1
            bucket["surfaces"].add(i_surface)
            if score >= 1:
                bucket["flagged"] += 1
                bucket["score_sum"] += score
                bucket["max_score"] = max(bucket["max_score"], score)
                bucket["signals"].update(hits)
                if not bucket["sample"]:
                    bucket["sample"] = _trim(text, 160)

        if score >= 1:
            flagged.append({
                "id": iid, "brand": brand, "surface": i_surface, "source": source,
                "outlet": outlet, "author_ref": actor_ref,
                "published_at": published_at, "url": url,
                "text": _trim(text), "score": score, "severity": severity,
                "signals": hits, "repeat": False,
            })

    repeat_refs = {ref for ref, data in offenders.items() if data["flagged"] >= 2}
    for row in flagged:
        row["repeat"] = row["author_ref"] in repeat_refs
    flagged.sort(key=lambda r: (-r["score"], r["published_at"] or "", -r["id"]))

    offender_rows = [{
        "actor_ref": data["actor_ref"],
        "comments": data["comments"],
        "flagged": data["flagged"],
        "score_sum": data["score_sum"],
        "max_score": data["max_score"],
        "max_severity": severity_of(data["max_score"]),
        "surfaces": sorted(s for s in data["surfaces"] if s),
        "signals": sorted(data["signals"]),
        "sample": data["sample"],
        "repeat": data["actor_ref"] in repeat_refs,
    } for data in offenders.values() if data["flagged"] >= 1]
    offender_rows.sort(key=lambda r: (-int(r["repeat"]), -r["flagged"],
                                      -r["score_sum"], r["actor_ref"]))

    flagged_n = len(flagged)
    return {
        "surface": surface or "all",
        "coverage": {
            "scanned": scanned,
            "with_actor_id": with_actor,
            "sources": sorted(seen_sources),
            "note": "Comments on the focus brand's own Facebook and Instagram "
                    "channels only. Commenter identity is one-way hashed.",
        },
        "policy": policy(),
        "summary": {
            "scanned": scanned,
            "flagged": flagged_n,
            "flag_rate": round(100 * flagged_n / scanned, 1) if scanned else 0.0,
            "high": band_counts["high"],
            "elevated": band_counts["elevated"],
            "low": band_counts["low"],
            "repeat_offenders": len(repeat_refs),
        },
        "signals": [{"key": k, "label": lbl, "weight": w, "n": signal_counts[k]}
                    for k, lbl, w, _rx in _COMPILED],
        "flagged": flagged[:_FLAGGED_LIMIT],
        "flagged_total": flagged_n,
        "offenders": offender_rows[:_OFFENDER_LIMIT],
    }
