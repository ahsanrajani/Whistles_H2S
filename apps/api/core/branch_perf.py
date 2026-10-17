"""Branch & ATM performance — per-branch rollup of Maps reviews + social listening.

Deterministic. For each branch in ``core.branches`` we pull its client-safe
mentions (Google-Maps review items carry the branch id in ``raw_json``; every
other surface is resolved with ``branches.resolve``), then compute:

  * review count, mean rating + Wilson interval, and the 30-day rating delta
  * negative-sentiment share of the social mentions
  * complaint count, and how many of those score Critical/High on the existing
    ``core.triage`` escalation scorer
  * which operational issues the text mentions (fixed keyword lexicon)

An attention score is the sum of fixed rules over those numbers — no model, no
learned threshold — and branches rank worst-first. The whole policy is returned
in the payload.
"""
import json
import re

from . import branch_resolver, triage, vertical
from db import repositories as repo
from db.analytics import scanners

from .insights import _age_days
from .stats import wilson

# key, label, keyword pattern (case-insensitive).
ISSUES = [
    ("queue", "Queue / wait time",
     r"\b(?:wait(?:ed|ing)?|queu(?:e|ing)|long\s+line|no\s+token|token\s+system"
     r"|30\+?\s*min|45\s*min|hour(?:s)?\s+(?:wait|in\s+line|standing)|only\s+one\s+counter"
     r"|no\s+(?:staff|teller)\s+at\s+(?:the\s+)?counter|left\s+waiting)\b"),
    ("staff", "Staff behaviour",
     r"\b(?:rude(?:ly)?|misbehav|mis-?behav|moody|arrogant|unprofessional|humiliat"
     r"|unhelpful|un-?cooperative|not\s+cooperative|refused\s+to\s+help|shouted"
     r"|dismiss(?:ed|ive)|(?:worst|poor|third[-\s]?class|pathetic)\s+staff|attitude)\b"),
    ("atm_cash", "ATM / cash",
     r"\b(?:atm\s+(?:not\s+working|out\s+of\s+(?:cash|order)|down|declined|rejected"
     r"|ate\s+my\s+card|swallowed\s+(?:my\s+)?card)|cash\s+not\s+dispensed"
     r"|(?:amount|money)\s+(?:deducted|debited)\s+but\s+(?:no\s+cash|not\s+dispensed)"
     r"|no\s+cash\s+in\s+(?:the\s+)?atm)\b"),
    ("biometric", "Biometric / verification",
     r"\b(?:biometric|\bbvs\b|verisys|nadra\s+verif|fingerprint\s+(?:not|fail|didn'?t)"
     r"|verification\s+(?:not\s+available|failed|down|machine))\b"),
    ("system_down", "System / app down",
     r"\b(?:system\s+(?:down|not\s+working|offline|slow)|server\s+down|link\s+(?:is\s+)?down"
     r"|network\s+(?:down|issue|problem)|branch\s+offline|app\s+(?:down|not\s+working|crash))\b"),
    ("account_block", "Account / card blocked",
     r"\b(?:account\s+(?:blocked|frozen|locked|on\s+hold|suspended|closed)"
     r"|card\s+blocked|\bcdd\b|\bpep\b|kyc\s+hold|salary\s+not\s+(?:credited|accepted|deposited))\b"),
    ("cheque", "Cheque / clearing",
     r"\b(?:cheque\s+(?:bounce[d]?|not\s+clear|clearing\s+delay|held)|clearing\s+(?:delay|held)"
     r"|pay\s?order\s+(?:delay|not)|dd\s+not\s+(?:made|issued))\b"),
    ("mis_selling", "Mis-selling",
     r"\b(?:mis[-\s]?sold|misleading\s+(?:sales|sale|information)|hidden\s+(?:charge|fee)"
     r"|without\s+(?:my\s+)?consent|forced\s+(?:me\s+)?to\s+(?:buy|open|take)"
     r"|insurance\s+(?:added|sold|without)|charged\s+extra\s+fee)\b"),
]

# Insurance branches: what customers complain about at an office / bancassurance desk.
ISSUES_INSURANCE = [
    ISSUES[0],
    ISSUES[1],
    ("claim_delay", "Claim delay / rejection",
     r"\b(?:claim\s+(?:rejected|denied|declined|delayed|pending|not\s+(?:paid|settled|processed))"
     r"|rejected\s+(?:my\s+)?claim|no\s+claim\s+settlement|claim\s+(?:is\s+)?still\s+pending)\b"),
    ("payout_delay", "Maturity / surrender payout",
     r"\b(?:maturity\s+(?:amount\s+)?(?:not\s+(?:paid|received)|delayed|pending)"
     r"|surrender\s+(?:value\s+)?(?:not\s+(?:paid|received)|delayed|deduct\w*|pending)"
     r"|not\s+received\s+(?:my\s+)?(?:maturity|payout|amount)|payout\s+delay\w*)\b"),
    ("no_response", "No response / follow-up",
     r"\b(?:no\s+(?:response|reply|follow[-\s]?up)|not\s+(?:responding|responded|replying)"
     r"|nobody\s+(?:called|responded|replied)|(?:call|phone)\s+not\s+(?:answered|picked))\b"),
    ("premium_dispute", "Premium / deduction dispute",
     r"\b(?:premium\s+(?:deducted|increased|not\s+(?:refunded|credited|updated))"
     r"|extra\s+(?:premium|deduction)|deducted\s+twice|wrong\s+deduction"
     r"|auto[-\s]?debit\s+(?:issue|problem|error))\b"),
    ("policy_docs", "Policy documents / records",
     r"\b(?:policy\s+(?:document|bond|copy|number)\s+(?:not|missing|delay)"
     r"|(?:not\s+received|never\s+received)\s+(?:my\s+)?policy|records?\s+(?:not|missing|wrong)"
     r"|cnic\s+(?:wrong|mismatch))\b"),
    ISSUES[7],
]

BANDS = [("high", "High", 7), ("elevated", "Elevated", 4),
         ("watch", "Watch", 2), ("none", "None", 0)]

_COMPILED_BY = {kind: [(k, lbl, re.compile(p, re.I)) for k, lbl, p in issues]
                for kind, issues in (("banking", ISSUES), ("insurance", ISSUES_INSURANCE))}
_COMPILED = _COMPILED_BY["banking"]
_MIN_REVIEWS = 4
_RECENT_DAYS = 30
_SAMPLE = 5


def band_of(score):
    for key, _label, threshold in BANDS:
        if score >= threshold:
            return key
    return "none"


def _issue_hits(text, kind="banking"):
    body = text or ""
    return [key for key, _lbl, rx in _COMPILED_BY[kind] if rx.search(body)]


def policy(kind="banking"):
    return {
        "vertical": kind,
        "issues": [{"key": k, "label": lbl} for k, lbl, _rx in _COMPILED_BY[kind]],
        "bands": [{"key": k, "label": lbl, "min_score": t} for k, lbl, t in BANDS],
        "min_reviews": _MIN_REVIEWS, "recent_days": _RECENT_DAYS,
    }


def _score(branch):
    """Attention score for one branch bucket — fixed rules over its numbers."""
    score = 0
    rating, reviews = branch["mean_rating"], branch["reviews"]
    if reviews >= _MIN_REVIEWS and rating is not None:
        if rating <= 2.5:
            score += 3
        elif rating <= 3.5:
            score += 2
    if branch["rating_delta"] is not None and branch["rating_delta"] <= -0.7:
        score += 2
    if branch["critical"] >= 1:
        score += 3
    if branch["complaints"] >= 3:
        score += 2
    if branch["neg_share"] is not None and branch["social"] >= 5 and branch["neg_share"] >= 0.5:
        score += 2
    score += min(sum(1 for issue in branch["issues"] if issue["n"] >= 2), 3)
    return score


def _trim(text, limit=260):
    return re.sub(r"\s+", " ", (text or "")).strip()[:limit]


def row_branch_key(raw_json, text, resolver):
    """(branch key or None, resolved_by_text) — review items carry their
    branch id in raw_json; anything else is resolved from its text."""
    try:
        key = (json.loads(raw_json) or {}).get("branch_key")
    except (TypeError, ValueError):
        key = None
    if key is not None:
        return key, False
    hit = resolver.resolve(text)
    return (hit[0], True) if hit else (None, False)


def is_bad(rating, sentiment, category):
    """A row counts toward issue themes when it reads as a complaint."""
    return (rating or 5) <= 2 or sentiment == "neg" or category in ("complaint", "fraud")


def scan(db, ws, days=None):
    """Per-branch performance rollup. Pure function of the workspace corpus."""
    focus = repo.brands.focus_id_name(db.session, ws)
    kind = vertical.of(db, ws)
    issue_defs = _COMPILED_BY[kind]
    resolver = branch_resolver.for_workspace(db, ws)
    base = {
        "policy": policy(kind),
        "coverage": {"focus_brand": focus[1] if focus else None,
                     "branches": len(resolver.entries), "reviews": 0,
                     "social_matched": 0, "unresolved_social": 0},
        "summary": {"branches_flagged": 0, "high": 0, "elevated": 0,
                    "reviews": 0, "mean_rating": None},
        "branches": [],
    }
    if not focus:
        return base

    rows = scanners.branch_perf_rows(db.session, focus[0])

    buckets = {}
    for key, name, code, city, _aliases in resolver.entries:
        buckets[key] = {
            "key": key, "name": name, "code": code or key, "city": city,
            "_ratings": [], "_ratings_recent": [], "_ratings_prev": [],
            "reviews": 0, "social": 0, "_neg": 0, "_scored": 0,
            "complaints": 0, "critical": 0,
            "_issue_n": {k: 0 for k, _l, _rx in issue_defs},
            "_samples": [],
        }
    reviews_total = unresolved = social_matched = 0
    all_ratings = []

    for (iid, surface, source, outlet, published_at, url, text, rating,
         raw_json, sentiment, category) in rows:
        if days is not None:
            age = _age_days(published_at)
            if age is None or not 0 <= age < days:
                continue
        if not (text or "").strip():
            continue

        is_review = surface == "branch_review"
        key, by_text = row_branch_key(raw_json, text, resolver)
        if by_text and not is_review:
            social_matched += 1
        elif key is None and not is_review and (category in ("complaint", "fraud")
                                                or sentiment == "neg" or (rating or 0) in (1, 2)):
            unresolved += 1
        if key is None or key not in buckets:
            continue

        bucket = buckets[key]
        age = _age_days(published_at)
        issues = _issue_hits(text, kind) if is_bad(rating, sentiment, category) else []
        for issue_key in issues:
            bucket["_issue_n"][issue_key] += 1

        if is_review:
            reviews_total += 1
            bucket["reviews"] += 1
            if rating:
                bucket["_ratings"].append(rating)
                all_ratings.append(rating)
                if age is not None and age < _RECENT_DAYS:
                    bucket["_ratings_recent"].append(rating)
                elif age is not None and age < _RECENT_DAYS * 3:
                    bucket["_ratings_prev"].append(rating)
        else:
            bucket["social"] += 1
        if sentiment in ("pos", "neu", "neg"):
            bucket["_scored"] += 1
            if sentiment == "neg":
                bucket["_neg"] += 1
        if category in ("complaint", "fraud") or sentiment == "neg" or (rating or 0) in (1, 2):
            bucket["complaints"] += 1
            tscore, _hits = triage.score_row(text, category=category, rating=rating,
                                             sentiment=sentiment)
            if triage.band_of(tscore) in ("high", "critical"):
                bucket["critical"] += 1
        if len(bucket["_samples"]) < 40:
            bucket["_samples"].append({
                "id": iid, "surface": surface, "source": source,
                "outlet": outlet, "url": url, "published_at": published_at,
                "rating": rating, "sentiment": sentiment,
                "issue": issues[0] if issues else None,
                "text": _trim(text),
                "_bad": (rating or 5) <= 2 or sentiment == "neg"
                        or category in ("complaint", "fraud"),
            })

    out = []
    for bucket in buckets.values():
        ratings = bucket["_ratings"]
        mean = round(sum(ratings) / len(ratings), 2) if ratings else None
        p, lo, hi = wilson(sum(1 for r in ratings if r <= 2), len(ratings)) if ratings else (None, None, None)
        recent = bucket["_ratings_recent"]
        prev = bucket["_ratings_prev"]
        r_recent = round(sum(recent) / len(recent), 2) if recent else None
        r_prev = round(sum(prev) / len(prev), 2) if prev else None
        delta = round(r_recent - r_prev, 2) if (r_recent is not None and r_prev is not None) else None
        scored, neg = bucket["_scored"], bucket["_neg"]
        neg_share = round(neg / scored, 2) if scored else None
        issue_rows = sorted(
            ({"key": k, "label": lbl, "n": bucket["_issue_n"][k]}
             for k, lbl, _rx in issue_defs if bucket["_issue_n"][k]),
            key=lambda x: -x["n"])
        branch = {
            "key": bucket["key"], "name": bucket["name"], "code": bucket["code"],
            "city": bucket["city"],
            "reviews": bucket["reviews"], "mean_rating": mean,
            "neg_review_share": p, "neg_review_lo": lo, "neg_review_hi": hi,
            "rating_recent": r_recent, "rating_prev": r_prev, "rating_delta": delta,
            "social": bucket["social"], "neg": neg, "neg_share": neg_share,
            "complaints": bucket["complaints"], "critical": bucket["critical"],
            "issues": issue_rows,
            "top_issue": issue_rows[0]["key"] if issue_rows else None,
        }
        branch["score"] = _score(branch)
        branch["band"] = band_of(branch["score"])
        bad_dates = [s["published_at"] for s in bucket["_samples"]
                     if s["_bad"] and s["published_at"]]
        branch["last_flag_at"] = max(bad_dates) if bad_dates else None
        samples = sorted(bucket["_samples"], key=lambda s: (not s["_bad"], s["published_at"] or ""),
                         reverse=False)
        samples.sort(key=lambda s: (not s["_bad"], -(s["id"])))
        branch["samples"] = [{k: v for k, v in s.items() if k != "_bad"}
                             for s in samples[:_SAMPLE]]
        out.append(branch)

    out.sort(key=lambda b: (-b["score"], -(b["complaints"]), b["mean_rating"] or 5, b["name"]))
    flagged = [b for b in out if b["band"] in ("high", "elevated")]

    return {
        "policy": policy(kind),
        "coverage": {
            "focus_brand": focus[1], "branches": len(resolver.entries),
            "reviews": reviews_total, "social_matched": social_matched,
            "unresolved_social": unresolved,
        },
        "summary": {
            "branches_flagged": len(flagged),
            "high": sum(1 for b in out if b["band"] == "high"),
            "elevated": sum(1 for b in out if b["band"] == "elevated"),
            "reviews": reviews_total,
            "mean_rating": round(sum(all_ratings) / len(all_ratings), 2) if all_ratings else None,
        },
        "branches": out,
    }
