"""Date / SVG helpers shared by the insight surfaces, and the period keys.

The rule for everything under `core/insights/`: an insight is only worth showing
if it survives its own uncertainty. Anything that would flip on a handful of
items gets returned with the caveat attached, not stripped of it. The
aggregation SQL these surfaces run lives in `db/analytics/`.
"""
import email.utils
from datetime import datetime, timedelta, timezone

# Still imported as `insights.SAFE_SQL` by the deterministic scanners' policy
# text; the analytics layer has its own copy in db/analytics/_util.py.
SAFE_SQL = "('public','licensed')"

PERIODS = {"7d": 7, "30d": 30, "90d": 90, "12mo": 365, "all": None}
PERIOD_LABELS = {"7d": "last 7 days", "30d": "last 30 days",
                 "90d": "last 90 days", "12mo": "last 12 months",
                 "all": "all time"}


def _day_bucket(raw):
    """A published_at value → 'YYYY-MM-DD', or None. Google News RSS emits
    RFC-822 dates; every other source emits ISO. Both are accepted here."""
    if not raw:
        return None
    s = str(raw).strip()
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    try:
        return email.utils.parsedate_to_datetime(s).date().isoformat()
    except (TypeError, ValueError, IndexError):
        return None


def _age_days(raw):
    """Whole days between a published_at value and today, or None."""
    day = _day_bucket(raw)
    if not day:
        return None
    try:
        d = datetime.strptime(day, "%Y-%m-%d").date()
    except ValueError:
        return None
    return (datetime.now(timezone.utc).date() - d).days


def _split_window(rows, days, value=lambda r: 1):
    """Sum `value(row)` over rows dated in the current `days` window and the one
    before it. `rows` is `[(published_at, …), …]`. Returns (cur_sum, cur_n,
    prior_sum, prior_n)."""
    cs = cn = ps = pn = 0
    for row in rows:
        age = _age_days(row[0])
        if age is None:
            continue
        if 0 <= age < days:
            cs += value(row); cn += 1
        elif days <= age < 2 * days:
            ps += value(row); pn += 1
    return cs, cn, ps, pn


def _pct_delta(cur, prior):
    if not prior:
        return None
    return (cur - prior) / prior * 100


def _iso_weeks(back=12):
    end = datetime.now(timezone.utc).date()
    monday = end - timedelta(days=end.weekday())
    return [(monday - timedelta(weeks=i)) for i in range(back - 1, -1, -1)]


def _poly(values, lo=0.0, hi=100.0, vw=600.0, vh=150.0, pad=8.0):
    """A list of numbers (None allowed) → one SVG polyline `points` string in a
    vw×vh box. Missing points are skipped and the x-axis is compressed."""
    pts = [v for v in values if v is not None]
    if len(pts) < 2 or hi <= lo:
        return ""
    step = vw / (len(pts) - 1)
    return " ".join(
        f"{x*step:.1f},"
        f"{pad + (vh - 2*pad) * (1 - (min(max(v, lo), hi) - lo) / (hi - lo)):.1f}"
        for x, v in enumerate(pts))
