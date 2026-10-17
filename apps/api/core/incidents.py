"""Competitor incident detection.

A mention-velocity spike, per brand, scored as a z-score against a trailing
28-day baseline and gated on incident-shaped keywords so a routine marketing
bump does not read as an incident. Deterministic: the window sizes, the z
threshold, the volume floor and the keyword lexicon are all parameters and are
returned in the payload.
"""
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from db.analytics import scanners

from .insights import _day_bucket

# Words that make a volume spike look like an incident rather than a campaign.
INCIDENT_LEXICON = [
    "outage", "down", "not working", "cannot login", "can't login", "can't log in",
    "app crash", "crashed", "server", "system down", "service unavailable",
    "hacked", "hack", "breach", "data leak", "phishing", "scam", "fraud",
    "stolen", "unauthorized", "double charged", "money stuck", "transaction failed",
    "penalty", "fined", "fine imposed", "lawsuit", "sued", "court", "regulator",
    "sbp notice", "mohtasib", "suspended", "shut down", "boycott", "protest",
]
_LEX_RX = [(term, re.compile(r"\b" + re.escape(term).replace(r"\ ", r"\s+") + r"\b", re.I))
           for term in INCIDENT_LEXICON]

_LOOKBACK_DAYS = 35
_BASELINE_DAYS = 28
_RECENT_DAYS = 4
_Z_THRESHOLD = 2.5
_MIN_COUNT = 4
_KEYWORD_SHARE = 0.30
_STDEV_FLOOR = 0.75
_SAMPLE_PER_DAY = 3


def _mean_stdev(values):
    if not values:
        return 0.0, 0.0
    mean = sum(values) / len(values)
    if len(values) < 2:
        return mean, 0.0
    var = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return mean, var ** 0.5


def _keyword_hits(text):
    return sorted({term for term, rx in _LEX_RX if rx.search(text or "")})


def scan(db, ws, *, z_threshold=_Z_THRESHOLD, min_count=_MIN_COUNT,
         keyword_share=_KEYWORD_SHARE):
    """Per-brand mention-velocity z-scores and any keyword-gated incidents.

    Pure function of the corpus so the API returns it unchanged.
    """
    rows = scanners.incident_rows(db.session, ws)

    end = datetime.now(timezone.utc).date()
    axis = [(end - timedelta(days=i)).isoformat()
            for i in range(_LOOKBACK_DAYS - 1, -1, -1)]
    axis_index = {day: pos for pos, day in enumerate(axis)}
    baseline_days = set(axis[:_LOOKBACK_DAYS - _RECENT_DAYS])
    recent_days = axis[_LOOKBACK_DAYS - _RECENT_DAYS:]

    per_brand_day = defaultdict(lambda: defaultdict(list))  # brand -> day -> [rows]
    focus_of = {}
    for name, is_focus, iid, raw, outlet, url, text in rows:
        focus_of[name] = bool(is_focus)
        day = _day_bucket(raw)
        if day in axis_index:
            per_brand_day[name][day].append((iid, outlet, url, text))

    brands = []
    incident_count = 0
    for name, is_focus in sorted(focus_of.items(), key=lambda kv: (not kv[1], kv[0])):
        by_day = per_brand_day.get(name, {})
        counts = {day: len(by_day.get(day, ())) for day in axis}
        base_values = [counts[day] for day in axis if day in baseline_days]
        mean, stdev = _mean_stdev(base_values)
        denom = max(stdev, _STDEV_FLOOR)

        series = [{"date": day, "count": counts[day],
                   "z": round((counts[day] - mean) / denom, 2)} for day in axis]

        incidents = []
        peak_z = 0.0
        elevated_hit = False
        for day in recent_days:
            count = counts[day]
            z = (count - mean) / denom
            peak_z = max(peak_z, z)
            if count >= min_count and z >= z_threshold * 0.6:
                elevated_hit = True
            if z < z_threshold or count < min_count:
                continue
            day_rows = by_day.get(day, [])
            kw_rows = [r for r in day_rows if _keyword_hits(r[3])]
            share = round(len(kw_rows) / count, 2) if count else 0.0
            keywords = sorted({kw for r in kw_rows for kw in _keyword_hits(r[3])})
            incidents.append({
                "date": day, "count": count, "z": round(z, 2),
                "baseline_mean": round(mean, 2),
                "keyword_share": share, "keywords": keywords,
                "gated_in": share >= keyword_share,
                "sample": [{"id": r[0], "outlet": r[1], "url": r[2],
                            "text": re.sub(r"\s+", " ", (r[3] or "")).strip()[:200]}
                           for r in (kw_rows or day_rows)[:_SAMPLE_PER_DAY]],
            })

        gated = [inc for inc in incidents if inc["gated_in"]]
        if gated:
            status = "incident"
            incident_count += 1
        elif incidents or elevated_hit:
            status = "elevated"
        else:
            status = "normal"

        brands.append({
            "brand": name, "focus": is_focus,
            "baseline": {"mean": round(mean, 2), "stdev": round(stdev, 2),
                         "days": len(base_values)},
            "recent": series[-_RECENT_DAYS:],
            "series": series,
            "peak_z": round(peak_z, 2),
            "incidents": incidents,
            "status": status,
        })

    brands.sort(key=lambda b: ({"incident": 0, "elevated": 1, "normal": 2}[b["status"]],
                               -b["peak_z"], not b["focus"], b["brand"]))
    return {
        "params": {
            "lookback_days": _LOOKBACK_DAYS, "baseline_days": _BASELINE_DAYS,
            "recent_days": _RECENT_DAYS, "z_threshold": z_threshold,
            "min_count": min_count, "keyword_share": keyword_share,
            "stdev_floor": _STDEV_FLOOR,
        },
        "as_of": end.isoformat(),
        "axis": axis,
        "lexicon": INCIDENT_LEXICON,
        "brands": brands,
        "incident_count": incident_count,
        "elevated_count": sum(1 for b in brands if b["status"] == "elevated"),
    }
