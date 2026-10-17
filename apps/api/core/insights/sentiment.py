"""Per-brand sentiment split, the focus-brand gauge and the weekly trend."""
from datetime import datetime, timedelta

from db.analytics import sentiment as q

from ..stats import wilson
from .common import _day_bucket, _iso_weeks, _poly


def sentiment_breakdown(db, ws, surface=None):
    """Per-brand pos/neu/neg over English scored mentions, with a Wilson
    interval on the negative share. `pending` counts English mentions not yet
    scored; `not_scored` counts everything the model is not allowed to judge.
    """
    rows = q.breakdown_rows(db.session, ws, surface)
    out = []
    for bid, name, focus, pos, neu, neg, not_scored, pending in rows:
        pos, neu, neg = pos or 0, neu or 0, neg or 0
        scored = pos + neu + neg
        p, lo, hi = wilson(neg, scored) if scored else (None, None, None)
        out.append({"id": bid, "name": name, "focus": bool(focus),
                    "pos": pos, "neu": neu, "neg": neg, "scored": scored,
                    "not_scored": not_scored or 0, "pending": pending or 0,
                    "neg_share": p, "neg_lo": lo, "neg_hi": hi})
    return out


def gauge(senti, cx=60, cy=60, r=50):
    """Semicircular sentiment gauge for the focus brand: arc-path `d` strings
    for negative / neutral / positive segments, left to right over the top."""
    focus = next((s for s in (senti or []) if s.get("focus")), None)
    if not focus or not focus["scored"]:
        return None
    scored = focus["scored"]
    fr = {"neg": focus["neg"] / scored, "neu": focus["neu"] / scored,
          "pos": focus["pos"] / scored}
    import math

    def pt(frac):
        ang = math.pi * (1 + frac)                 # 180deg -> 360deg
        return cx + r * math.cos(ang), cy + r * math.sin(ang)

    segs = []
    acc = 0.0
    for key in ("neg", "neu", "pos"):
        a, b = acc, acc + fr[key]
        acc = b
        if b - a < 1e-4:
            continue
        x0, y0 = pt(a)
        x1, y1 = pt(b)
        # Every segment is at most half a circle (b - a <= 1 spans <= 180deg),
        # so the arc is always the minor one: large-arc-flag is always 0.
        segs.append({"cls": key,
                     "d": f"M{x0:.2f},{y0:.2f} A{r},{r} 0 0,1 {x1:.2f},{y1:.2f}"})
    tx0, ty0 = pt(0)
    tx1, ty1 = pt(1)
    track = f"M{tx0:.2f},{ty0:.2f} A{r},{r} 0 0,1 {tx1:.2f},{ty1:.2f}"
    pos_share = fr["pos"]
    p, lo, hi = wilson(focus["pos"], scored)
    return {"track": track, "segs": segs, "pos_pct": round(pos_share * 100),
            "lo": round(lo * 100), "hi": round(hi * 100),
            "pos": focus["pos"], "neu": focus["neu"], "neg": focus["neg"],
            "scored": scored, "name": focus["name"],
            "vb_h": round(cy + 8)}


def sentiment_trend(db, ws, weeks=12):
    """Weekly positive / negative share of scored English focus-brand mentions."""
    rows = q.focus_scored_rows(db.session, ws)
    axis = _iso_weeks(weeks)
    idx = {w.isoformat(): i for i, w in enumerate(axis)}
    tot = [0] * weeks
    pos = [0] * weeks
    neg = [0] * weeks
    for raw, label in rows:
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
            tot[i] += 1
            if label == "pos":
                pos[i] += 1
            elif label == "neg":
                neg[i] += 1
    pos_s = [round(100 * p / t) if t else None for p, t in zip(pos, tot)]
    neg_s = [round(100 * n / t) if t else None for n, t in zip(neg, tot)]
    return {"axis": [w.isoformat() for w in axis], "pos": pos_s, "neg": neg_s, "n": tot,
            "pos_points": _poly(pos_s), "neg_points": _poly(neg_s),
            "has_data": any(t for t in tot)}
