"""What customers actually do around the brand's own posts.

Reads the posts and comments the collectors already stored (``core/owned_posts``)
and answers four plain questions: which posts beat the brand's own baseline,
whether scammers are working a popular post, which topics draw reaction and
complaints, and when the audience responds. Nothing here is modelled -- every
figure is a count or a ratio of counts, every proportion carries a Wilson
interval, and anything resting on too little history says so instead of
guessing (a platform that exposes no metrics shows ``null``, never zero).
"""
import re
import statistics
from datetime import datetime, timedelta, timezone

from . import incidents, owned_posts, scam, stats

ENGAGEMENT_KEYS = ("likes", "comments", "shares", "reposts", "replies", "quotes")
_POST_LIMIT = 40
_COMMENT_POSTS = 12              # comment-level analysis (one query per post)
_BASELINE_MIN_POSTS = 5
_ABOVE, _BELOW = 1.5, 0.5        # engagement vs the brand's own median
_RISK_FLAGGED = 2                # scam-flagged comments before a post is "worked"
_TIMING_MIN_POSTS = 10
_TZ = timezone(timedelta(hours=5), "Asia/Karachi")
_DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_DAYPARTS = (("night", 0, 6), ("morning", 6, 12), ("afternoon", 12, 18), ("evening", 18, 24))

# (key, label, pattern): what a post is about, in customers' own terms.
TOPICS = [
    ("fraud_awareness", "Fraud awareness",
     r"\b(?:scam|fraud|phishing|fake|beware|otp|pin|safe(?:ty|guard))\b"),
    ("savings_rates", "Savings and profit rates",
     r"\b(?:profit\s+rate|savings?|deposit|interest|returns?|rate\b)"),
    ("cards_payments", "Cards and payments",
     r"\b(?:cards?|debit|credit|payments?|raast|qr|wallet|atm)\b"),
    ("digital_banking", "Digital banking and app",
     r"\b(?:app|mobile\s+banking|internet\s+banking|digital|online|login|update)\b"),
    ("financing", "Loans and financing",
     r"\b(?:loans?|financing|mortgage|home\s+finance|auto\s+finance|installments?)\b"),
    ("campaigns", "Offers and campaigns",
     r"\b(?:offer|discount|cash\s?back|reward|campaign|win|giveaway|eid|ramadan)\b"),
]
_TOPIC_RX = [(k, lbl, re.compile(p, re.I)) for k, lbl, p in TOPICS]


def _engagement(metrics) -> int | None:
    if not metrics:
        return None
    vals = [metrics[k] for k in ENGAGEMENT_KEYS
            if isinstance(metrics.get(k), (int, float))]
    return int(sum(vals)) if vals else None


def _when(raw):
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_TZ)


def _interval(k: int, n: int) -> dict | None:
    if n == 0:
        return None
    p, lo, hi = stats.wilson(k, n)
    return {"k": k, "n": n, "rate": round(p, 4), "ci_low": round(lo, 4), "ci_high": round(hi, 4)}


def _comment_signals(session, ws, post) -> dict:
    comments = owned_posts.comments_for(session, ws, source=post["source"],
                                        post_external_id=post["external_id"])
    flagged = complaints = 0
    for c in comments:
        body = c.get("body") or ""
        if scam.score_text(body)[0] >= 1:
            flagged += 1
        if incidents._keyword_hits(body):                       # noqa: SLF001
            complaints += 1
    return {"n": len(comments), "flagged": flagged, "complaints": complaints}


def _topics_of(post) -> list[str]:
    text = " ".join(filter(None, (post.get("title"), post.get("body"))))
    return [k for k, _lbl, rx in _TOPIC_RX if rx.search(text)]


def _timing(rows, baseline) -> dict:
    """Average engagement-vs-baseline by weekday and by daypart (Karachi time)."""
    timed = [(w, r) for w, r in rows if w is not None]
    if baseline is None or len(timed) < _TIMING_MIN_POSTS:
        return {"available": False, "tz": "Asia/Karachi (UTC+5)", "posts": len(timed),
                "needed": _TIMING_MIN_POSTS,
                "note": f"Needs at least {_TIMING_MIN_POSTS} dated posts with engagement; "
                        f"{len(timed)} on file."}

    def bucket(keyfn, labels):
        acc = {k: [] for k in labels}
        for when, ratio in timed:
            acc[keyfn(when)].append(ratio)
        return [{"label": k, "posts": len(v),
                 "ratio": round(statistics.mean(v), 2) if v else None}
                for k, v in acc.items()]

    by_day = bucket(lambda w: _DAYS[w.weekday()], _DAYS)
    by_part = bucket(lambda w: next(n for n, lo, hi in _DAYPARTS if lo <= w.hour < hi),
                     [n for n, _lo, _hi in _DAYPARTS])
    best = lambda rows_: max((r for r in rows_ if r["posts"] >= 2),           # noqa: E731
                             key=lambda r: r["ratio"], default=None)
    return {"available": True, "tz": "Asia/Karachi (UTC+5)", "posts": len(timed),
            "by_weekday": by_day, "by_daypart": by_part,
            "best_weekday": best(by_day), "best_daypart": best(by_part)}


def performance(db, ws) -> dict:
    session = db.session
    posts = owned_posts.recent(session, ws, limit=_POST_LIMIT)
    with_eng = [(p, _engagement(p["metrics"])) for p in posts]
    values = [e for _p, e in with_eng if e is not None]
    baseline = (statistics.median(values)
                if len(values) >= _BASELINE_MIN_POSTS else None)

    rows, topic_acc, timed = [], {}, []
    for idx, (post, eng) in enumerate(with_eng):
        ratio = round(eng / baseline, 2) if (eng is not None and baseline) else None
        band = (None if ratio is None else
                "above" if ratio >= _ABOVE else "below" if ratio <= _BELOW else "typical")
        sig = _comment_signals(session, ws, post) if idx < _COMMENT_POSTS else None
        topics = _topics_of(post)
        worked = bool(sig and sig["flagged"] >= _RISK_FLAGGED)
        rows.append({
            "platform": post["platform_label"], "url": post["url"],
            "published_at": post["published_at"],
            "text": re.sub(r"\s+", " ", post["body"] or post["title"] or "")[:140],
            "engagement": eng, "vs_baseline": ratio, "band": band, "topics": topics,
            "comments": None if sig is None else {
                "n": sig["n"], "scam_flagged": _interval(sig["flagged"], sig["n"]),
                "complaints": _interval(sig["complaints"], sig["n"])},
            "scammers_working_it": worked,
        })
        for t in topics:
            acc = topic_acc.setdefault(t, {"posts": 0, "eng": [], "c_k": 0, "c_n": 0})
            acc["posts"] += 1
            if eng is not None:
                acc["eng"].append(eng)
            if sig:
                acc["c_k"] += sig["complaints"]
                acc["c_n"] += sig["n"]
        timed.append((_when(post["published_at"]), ratio))

    labels = {k: lbl for k, lbl, _rx in _TOPIC_RX}
    topics_out = [{
        "key": k, "label": labels[k], "posts": a["posts"],
        "avg_engagement": round(statistics.mean(a["eng"]), 1) if a["eng"] else None,
        "complaints": _interval(a["c_k"], a["c_n"]),
    } for k, a in topic_acc.items()]
    topics_out.sort(key=lambda t: (-(t["avg_engagement"] or 0), t["key"]))

    timing = _timing([(w, r) for w, r in timed if r is not None], baseline)
    return {
        "baseline": {"median_engagement": baseline, "posts_with_metrics": len(values),
                     "needed": _BASELINE_MIN_POSTS,
                     "note": None if baseline is not None else
                     f"Needs at least {_BASELINE_MIN_POSTS} posts with engagement counts; "
                     f"{len(values)} on file."},
        "posts": rows, "topics": topics_out, "timing": timing,
        "digest": _digest(rows, topics_out, timing, baseline),
        "policy": {"engagement_keys": list(ENGAGEMENT_KEYS), "above": _ABOVE,
                   "below": _BELOW, "scammer_flag_min": _RISK_FLAGGED,
                   "topics": [{"key": k, "label": lbl} for k, lbl, _p in TOPICS]},
    }


def _digest(rows, topics, timing, baseline) -> list[dict]:
    """A few plain sentences, each backed by the numbers above."""
    out = []
    worked = [r for r in rows if r["scammers_working_it"]]
    for r in sorted(worked, key=lambda r: -(r["engagement"] or 0))[:2]:
        f = r["comments"]["scam_flagged"]
        out.append({"kind": "risk", "text": (
            f"Scam comments are clustering under a {r['platform']} post "
            f"({f['k']} of {f['n']} comments flagged): \"{r['text'][:70]}\". "
            "Consider pinning a warning or replying from the verified account."),
            "url": r["url"]})
    above = [r for r in rows if r["band"] == "above"]
    if above and baseline:
        top = max(above, key=lambda r: r["vs_baseline"])
        out.append({"kind": "win", "text": (
            f"Best recent post: {top['vs_baseline']}x the brand's usual engagement "
            f"on {top['platform']}: \"{top['text'][:70]}\"."), "url": top["url"]})
    ranked = [t for t in topics if t["posts"] >= 2 and t["avg_engagement"] is not None]
    if ranked:
        t = ranked[0]
        out.append({"kind": "topic", "text": (
            f"{t['label']} posts draw the most reaction ({t['avg_engagement']} on average "
            f"across {t['posts']} posts).")})
    if timing["available"] and timing["best_weekday"] and timing["best_daypart"]:
        out.append({"kind": "timing", "text": (
            f"Posts do best on {timing['best_weekday']['label']} "
            f"({timing['best_weekday']['ratio']}x baseline) and in the "
            f"{timing['best_daypart']['label']} ({timing['best_daypart']['ratio']}x), "
            f"{timing['tz']}.")})
    if not out:
        out.append({"kind": "empty", "text": (
            "Not enough post history yet to draw conclusions. Connect an owned channel "
            "and collect a few weeks of posts and comments.")})
    return out
