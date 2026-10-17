"""App-store review surfaces: store scorecard, weekly mean and the daily
rolling rating timeline for before/after comparisons."""
import json
from datetime import datetime, timedelta, timezone

from db.analytics import reviews as q

from ..stats import wilson
from .common import _day_bucket, _iso_weeks, _poly


def _app(raw_json):
    """Which app a review belongs to -- {id, name, icon} from the collector's
    ``raw``, or None for reviews collected before multi-app support."""
    try:
        raw = json.loads(raw_json or "{}")
    except (TypeError, ValueError):
        return None
    if not isinstance(raw, dict) or not raw.get("app_id"):
        return None
    icon = raw.get("app_icon")
    return {"id": raw["app_id"], "name": raw.get("app_name"),
            "icon": icon if isinstance(icon, str) and icon.startswith("https://") else None}


def app_reviews(db, ws, recent_limit=6):
    """App-store review ratings for the focus brand's app: per-store average and
    star histogram, the >=4-star share with a Wilson band, and recent reviews
    -- both one merged newest-first list (`recent`, back-compat) and, since
    `rows` already comes back newest-first, up to `recent_limit` per store
    (`stores[].recent`) so a store with fewer/older reviews can't crowd a
    busier one out of its own top-N.
    """
    rows = q.scorecard_rows(db.session, ws)
    if not rows:
        return None

    stores = {}
    dist_all = [0, 0, 0, 0, 0]
    for outlet, rating, published_at, text, url, raw_json in rows:
        store = outlet or "Store"
        s = stores.setdefault(store, {"store": store, "n": 0, "sum": 0,
                                      "dist": [0, 0, 0, 0, 0], "recent": []})
        s["n"] += 1
        s["sum"] += rating
        s["dist"][rating - 1] += 1
        dist_all[rating - 1] += 1
        if len(s["recent"]) < recent_limit:
            s["recent"].append({"rating": rating, "when": (published_at or "")[:10],
                                "text": (text or "").strip()[:240], "url": url,
                                "app": _app(raw_json)})
    for s in stores.values():
        s["avg"] = round(s["sum"] / s["n"], 2)
        s.pop("sum")

    overall_n = len(rows)
    overall_avg = round(sum(r[1] for r in rows) / overall_n, 2)
    good = dist_all[3] + dist_all[4]
    gp, glo, ghi = wilson(good, overall_n)
    recent = [{"store": o or "Store", "rating": rt, "when": (p or "")[:10],
               "text": (t or "").strip()[:240], "url": u, "app": _app(rj)}
              for o, rt, p, t, u, rj in rows[:recent_limit]]
    return {"stores": sorted(stores.values(), key=lambda s: -s["n"]),
            "dist": dist_all, "overall_n": overall_n, "overall_avg": overall_avg,
            "good_share": gp, "good_lo": glo, "good_hi": ghi, "recent": recent}


def review_trend(db, ws, weeks=12):
    """Weekly mean app rating."""
    rows = q.rating_rows(db.session, ws)
    axis = _iso_weeks(weeks)
    idx = {w.isoformat(): i for i, w in enumerate(axis)}
    s = [0.0] * weeks
    n = [0] * weeks
    for raw, rating in rows:
        day = _day_bucket(raw)
        if not day:
            continue
        try:
            d = datetime.strptime(day, "%Y-%m-%d").date()
        except ValueError:
            continue
        wk = (d - timedelta(days=d.weekday())).isoformat()
        if wk in idx:
            i = idx[wk]
            s[i] += rating
            n[i] += 1
    avg = [round(s[i] / n[i], 2) if n[i] else None for i in range(weeks)]
    return {"axis": [w.isoformat() for w in axis], "avg": avg, "n": n,
            "points": _poly(avg, lo=1.0, hi=5.0), "has_data": any(n)}


def rating_timeline(db, ws, days=90, window=7):
    """Daily app-rating series with a `window`-day rolling view — a rolling
    mean (1–5) and the rolling share of new ratings by star. This is the
    before/after comparison surface: pair it with an event marker.
    """
    rows = q.rating_rows(db.session, ws)
    today = datetime.now(timezone.utc).date()
    axis = [(today - timedelta(days=days - 1 - i)) for i in range(days)]
    idx = {d.isoformat(): i for i, d in enumerate(axis)}
    day_sum = [0.0] * days
    day_n = [0] * days
    day_star = [[0] * 5 for _ in range(days)]     # day_star[i][star-1]
    for raw, rating in rows:
        day = _day_bucket(raw)
        if not day or day not in idx:
            continue
        i = idx[day]
        day_sum[i] += rating
        day_n[i] += 1
        day_star[i][rating - 1] += 1

    roll_avg, roll_n = [], []
    roll_share = {s: [] for s in range(1, 6)}
    for i in range(days):
        lo = max(0, i - window + 1)
        w_sum = sum(day_sum[lo:i + 1])
        w_n = sum(day_n[lo:i + 1])
        roll_n.append(w_n)
        roll_avg.append(round(w_sum / w_n, 3) if w_n else None)
        for star in range(1, 6):
            w_star = sum(day_star[j][star - 1] for j in range(lo, i + 1))
            roll_share[star].append(round(w_star / w_n, 4) if w_n else None)
    return {
        "axis": [d.isoformat() for d in axis],
        "roll_avg": roll_avg, "roll_n": roll_n,
        "roll_share": {str(k): v for k, v in roll_share.items()},
        "window": window, "days": days, "has_data": any(day_n),
    }
