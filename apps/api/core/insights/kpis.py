"""The headline number row and the current-vs-previous window deltas that feed
its tiles."""
from db.analytics import kpis as q

from ..stats import delta_is_real, wilson
from .common import _pct_delta, _split_window


def deltas(db, ws, days=30, surface=None):
    """Current vs previous `days` window for the headline client metrics.
    Each entry is {now, prior, pct, dir} where `pct` is None unless the move
    clears its guard."""
    out = {}

    m = q.mention_dates(db.session, ws, surface)
    cn, _c, pn, _p = _split_window(m, days)
    pct = _pct_delta(cn, pn) if (pn and delta_is_real(cn, cn + pn, pn, cn + pn)) else None
    out["mentions"] = {"now": cn, "prior": pn, "pct": pct,
                       "dir": "up" if (pct or 0) >= 0 else "down"}

    srows = q.focus_sentiment_dates(db.session, ws, surface)
    cp, cnn, pp, pnn = _split_window(srows, days, value=lambda r: 1 if r[1] == "pos" else 0)
    if cnn >= 20 and pnn >= 20:
        now, prior = cp / cnn * 100, pp / pnn * 100
        out["positive"] = {"now": now, "prior": prior, "pct": now - prior,
                           "dir": "up" if now >= prior else "down"}
    else:
        out["positive"] = {"now": None, "prior": None, "pct": None, "dir": "up"}

    frows = q.focus_flag_dates(db.session, ws, surface)
    fc, fcn, fp, fpn = _split_window(frows, days, value=lambda r: 1 if r[1] else 0)
    if fcn >= 20 and fpn >= 20:
        now, prior = fc / fcn * 100, fp / fpn * 100
        out["sov"] = {"now": now, "prior": prior, "pct": now - prior,
                      "dir": "up" if now >= prior else "down"}
    else:
        out["sov"] = {"now": None, "prior": None, "pct": None, "dir": "up"}

    rrows = q.rating_dates(db.session, ws)
    rc, rcn, rp, rpn = _split_window(rrows, days, value=lambda r: r[1])
    if rcn >= 5 and rpn >= 5:
        now, prior = rc / rcn, rp / rpn
        out["rating"] = {"now": now, "prior": prior, "pct": now - prior,
                         "dir": "up" if now >= prior else "down"}
    else:
        out["rating"] = {"now": None, "prior": None, "pct": None, "dir": "up"}
    return out


def kpis(db, ws, sov, senti, surface=None, days=30, period_label="", reviews=None, dl=None):
    """The headline number row. Each tile carries a value, a qualifier and an
    optional period delta."""
    tiles = []
    focus = next((b for b in sov if b["focus"]), None)
    total = sum(b["n"] or 0 for b in sov)
    dl = dl or {}
    focus_id = focus["id"] if focus else None

    md = dl.get("mentions") or {}
    sub = (f"{md.get('now', 0):,} in the {period_label}" if period_label
           else f"{md.get('now', 0):,} dated")
    tiles.append({"key": "mentions", "label": "Mentions collected",
                  "value": f"{total:,}", "sub": sub, "delta": md.get("pct"),
                  "href": "/mentions"})

    fs = next((s for s in senti if s.get("focus")), None)
    if fs and fs["scored"]:
        p, lo, hi = wilson(fs["pos"], fs["scored"])
        tiles.append({"key": "positive", "label": "Positive sentiment",
                      "value": f"{p*100:.0f}%",
                      "sub": f"95% {lo*100:.0f}–{hi*100:.0f}% · {fs['scored']:,} scored",
                      "delta": (dl.get("positive") or {}).get("pct"),
                      "href": "/sentiment"})
    if focus:
        rank = 1 + sum(1 for b in sov if (b["n"] or 0) > (focus["n"] or 0))
        half = max(focus["p"] - focus["lo"], focus["hi"] - focus["p"]) * 100
        tiles.append({"key": "sov", "label": "Share of voice",
                      "value": f"{focus['p']*100:.0f}%",
                      "sub": f"±{half:.0f} · rank {rank} of {len(sov)}",
                      "delta": (dl.get("sov") or {}).get("pct"),
                      "href": "/competitors"})
    if reviews and reviews.get("overall_n"):
        rd = (dl.get("rating") or {}).get("pct")
        tiles.append({"key": "rating", "label": "App rating",
                      "value": f"{reviews['overall_avg']:.1f}★",
                      "sub": f"{reviews['overall_n']:,} reviews",
                      "delta": (round(rd, 1) if rd is not None else None),
                      "href": "/reviews"})
    return tiles
