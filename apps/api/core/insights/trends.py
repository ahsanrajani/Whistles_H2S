"""Volume-over-time surfaces: the raw daily timeline, the smoothed press-volume
trend line and the hour-of-day histogram."""
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from db.analytics import trends as q

from .common import _day_bucket

_TREND_COLORS = ["#2f6f8f", "#5b5f97", "#7d7a52", "#8a5a6d"]


def timeline(db, ws, days=21, surface=None):
    rows = q.timeline_rows(db.session, ws, surface)
    series = defaultdict(Counter)
    for name, raw in rows:
        day = _day_bucket(raw)
        if day:
            series[name][day] += 1
    end = datetime.now(timezone.utc).date()
    axis = [(end - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]
    return axis, {k: [v.get(d, 0) for d in axis] for k, v in series.items()}


def press_volume(db, ws, days=45, surface=None):
    """Mentions per day per brand for the trend chart.

    With no channel filter this is news-wire only (`googlenews_rss`): YouTube
    and Bluesky timestamps are upload dates, not conversation dates, so a mixed
    line would mislead. With a channel selected it follows that surface instead.
    Points are pre-scaled into a 0..100 box for a plain SVG polyline.
    """
    rows = q.press_volume_rows(db.session, ws, surface)
    end = datetime.now(timezone.utc).date()
    axis = [(end - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]
    index = {d: x for x, d in enumerate(axis)}
    per_brand = defaultdict(lambda: [0] * days)
    focus_of = {}
    for name, is_focus, raw in rows:
        focus_of[name] = bool(is_focus)
        day = _day_bucket(raw)
        if day in index:
            per_brand[name][index[day]] += 1

    # Smooth the daily counts with a trailing 7-day mean so a handful of
    # scattered items reads as a trend line, not a sawtooth.
    window = 7 if days >= 14 else 3

    def rolling(counts):
        out = []
        for i in range(len(counts)):
            lo = max(0, i - window + 1)
            span = counts[lo:i + 1]
            out.append(sum(span) / len(span))
        return out

    smoothed = {name: rolling(counts) for name, counts in per_brand.items()}

    raw_peak = max((max(counts) for counts in per_brand.values()), default=0)
    peak = max((max(vals) for vals in smoothed.values()), default=0.0)
    peak_day = None
    if raw_peak:
        for counts in per_brand.values():
            if raw_peak in counts:
                peak_day = axis[counts.index(raw_peak)]
                break

    ordered = sorted(per_brand.items(),
                     key=lambda kv: (not focus_of[kv[0]], -sum(kv[1])))
    # Draw in a wide box so diagonals are not visually skewed when the SVG is
    # stretched to the card width.
    vw, vh, pad = 1000.0, 260.0, 10.0
    step = (vw) / (days - 1) if days > 1 else 0
    scale = peak or 1
    series = []
    ci = 0
    for name, counts in ordered:
        if focus_of[name]:
            color = "#f47a22"
        else:
            color = _TREND_COLORS[ci % len(_TREND_COLORS)]
            ci += 1
        line = smoothed[name]
        coords = [(x * step, pad + (vh - 2 * pad) * (1 - c / scale))
                  for x, c in enumerate(line)]
        pts = _smooth_path(coords)
        area = None
        if focus_of[name]:
            area = f"M0,{vh:.0f} " + pts + f" L{vw:.0f},{vh:.0f} Z"
        series.append({"name": name, "focus": focus_of[name], "color": color,
                       "total": sum(counts), "points": pts, "area": area,
                       "counts": counts, "smooth": [round(v, 2) for v in line]})
    return {"axis": axis, "days": days, "peak": round(peak, 3),
            "raw_peak": raw_peak, "peak_day": peak_day, "window": window,
            "series": series, "vw": int(vw), "vh": int(vh)}


def _smooth_path(coords):
    """A Catmull-Rom-ish path string ("M … C …") through `coords` for a soft
    trend line instead of a jagged polyline."""
    if not coords:
        return ""
    if len(coords) < 3:
        return "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    d = [f"M{coords[0][0]:.1f},{coords[0][1]:.1f}"]
    for i in range(1, len(coords)):
        x0, y0 = coords[i - 1]
        x1, y1 = coords[i]
        xp, yp = coords[i - 2] if i >= 2 else coords[i - 1]
        xn, yn = coords[i + 1] if i + 1 < len(coords) else coords[i]
        c1x, c1y = x0 + (x1 - xp) / 6.0, y0 + (y1 - yp) / 6.0
        c2x, c2y = x1 - (xn - x0) / 6.0, y1 - (yn - y0) / 6.0
        d.append(f"C{c1x:.1f},{c1y:.1f} {c2x:.1f},{c2y:.1f} {x1:.1f},{y1:.1f}")
    return " ".join(d)


def peak_hours(db, ws, surface=None):
    """Hour-of-day histogram over resolvable timestamps + the busiest 2h band."""
    import email.utils as _eu
    rows = q.peak_hour_rows(db.session, ws, surface)
    bars = [0] * 24
    for (raw,) in rows:
        s = str(raw).strip()
        dt = None
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            try:
                dt = _eu.parsedate_to_datetime(s)
            except (TypeError, ValueError):
                dt = None
        if dt is not None:
            bars[dt.hour] += 1
    total = sum(bars)
    if not total:
        return {"bars": bars, "total": 0, "window": None}
    best_start = max(range(24), key=lambda h: bars[h] + bars[(h + 1) % 24])
    end = (best_start + 2) % 24

    def h12(h):
        ap = "AM" if h < 12 else "PM"
        hh = h % 12 or 12
        return f"{hh}{ap}"

    return {"bars": bars, "total": total, "peak": max(bars),
            "window": f"{h12(best_start)}–{h12(end)}"}
