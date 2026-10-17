"""Share of voice, outlet reach and the outlet-gap target list."""
from collections import defaultdict

from db.analytics import competitors as q

from ..stats import wilson


def share_of_voice(db, ws, surface=None):
    rows = q.share_of_voice_rows(db.session, ws, surface)
    total = sum(r[3] or 0 for r in rows) or 1
    out = []
    for bid, name, focus, n, review, exc in rows:
        n = n or 0
        p, lo, hi = wilson(n, total)
        out.append({"id": bid, "name": name, "focus": bool(focus), "n": n,
                    "review": review or 0, "excluded": exc or 0,
                    "p": p, "lo": lo, "hi": hi, "total": total})
    return out


def indistinguishable_pairs(sov):
    """Pairs whose intervals overlap. Ranking between them is not supportable."""
    out = []
    for i, a in enumerate(sov):
        for b in sov[i + 1:]:
            if a["lo"] <= b["hi"] and b["lo"] <= a["hi"]:
                out.append((a["name"], b["name"]))
    return out


def outlet_gap(db, ws, focus_name, surface=None):
    """Outlets that cover the competitors but have never mentioned the focus
    brand. This is the join no listening vendor offers, and it converts a
    passive mention count into a target list.
    """
    rows = q.outlet_gap_rows(db.session, ws, surface)
    by_outlet = defaultdict(dict)
    for outlet, brand, focus, n in rows:
        by_outlet[outlet][brand] = n
    gaps = []
    for outlet, brands in by_outlet.items():
        if focus_name in brands:
            continue
        comp_total = sum(brands.values())
        if comp_total >= 1:
            gaps.append({"outlet": outlet, "total": comp_total,
                         "brands": sorted(brands.items(), key=lambda x: -x[1])})
    gaps.sort(key=lambda g: -g["total"])
    reached = sum(1 for o, b in by_outlet.items() if focus_name in b)
    return gaps, reached, len(by_outlet)


def top_outlets(db, ws, limit=10, surface=None):
    return q.top_outlet_rows(db.session, ws, limit, surface)
