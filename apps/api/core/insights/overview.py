"""Overview-page surfaces: the coverage ledger, language and mention mix, the
three-sentence headline and the ranked action cards."""
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from .. import sources
from ..stats import delta_is_real
from db.analytics import overview as q

from .common import _age_days, _day_bucket, _pct_delta
from .competitors import indistinguishable_pairs


def surface_ledger(db, ws, run_id):
    rows = q.surface_status_rows(db.session, ws, run_id)
    safe_labels = {meta["label"] for meta in sources.SOURCES.values()
                   if meta.get("client_safe")}
    connectable = {meta["surface"] for meta in sources.SOURCES.values()
                   if meta.get("client_safe") and meta["surface"] != "—"}
    order = {"collected": 0, "sampled": 1, "failed": 2}
    ledger = []
    for surface, state, n_sources, can_estimate, note in rows:
        if state == "unmonitorable" or surface not in connectable:
            continue
        # Sanitize historical runs written before status filtering existed.
        if state in ("collected", "sampled"):
            labels = [label.strip() for label in (note or "").split(";")]
            labels = [label for label in labels if label in safe_labels]
            if not labels:
                state, n_sources, can_estimate, note = "failed", 0, 0, "Not connected"
            else:
                note = "; ".join(labels)
        ledger.append({"surface": surface, "state": state, "n": n_sources,
                       "estimable": bool(can_estimate), "note": note})
    return sorted(ledger, key=lambda row: (order.get(row["state"], 9), row["surface"]))


def language_mix(db, ws, surface=None):
    rows = q.language_rows(db.session, ws, surface)
    total = sum(r[1] for r in rows) or 1
    return [{"lang": l or "unknown", "n": n, "pct": n / total,
             "scored_n": scored, "eligible": (l == "en")}
            for l, n, scored in rows]


def top_authors(db, ws, limit=8, surface=None):
    """Named voices carrying the conversation — channels, handles, bylines."""
    rows = q.author_rows(db.session, ws, surface)
    out = [(a, n) for a, n in rows
           if n >= 3 and "bot" not in a.lower() and not a.isdigit()]
    return out[:limit]


def mention_mix(db, ws, surface=None, days=None):
    """Per-type breakdown of client-safe mentions for the conversation-mix
    widget: count, share, sentiment split, and an optional period delta.
    A mention with no classification row counts as `other`, so the widget reads
    sensibly before any scoring run.
    """
    from ..classify import CATEGORIES, COLOUR_OF, LABEL_OF

    rows = q.mention_mix_rows(db.session, ws, surface)

    agg = {k: {"n": 0, "pos": 0, "neu": 0, "neg": 0} for k, _h, _c in CATEGORIES}
    cur, prior = Counter(), Counter()
    for cat, label, pub in rows:
        if cat not in agg:
            cat = "other"
        agg[cat]["n"] += 1
        if label in ("pos", "neu", "neg"):
            agg[cat][label] += 1
        if days:
            age = _age_days(pub)
            if age is None:
                continue
            if 0 <= age < days:
                cur[cat] += 1
            elif days <= age < 2 * days:
                prior[cat] += 1

    total = sum(a["n"] for a in agg.values())
    cats = []
    for k, _h, _c in CATEGORIES:
        a = agg[k]
        if not a["n"]:
            continue
        cats.append({
            "key": k, "label": LABEL_OF[k], "colour": COLOUR_OF[k],
            "n": a["n"], "pct": round(100 * a["n"] / total, 1) if total else 0.0,
            "pos": a["pos"], "neu": a["neu"], "neg": a["neg"],
            "delta_pct": _pct_delta(cur[k], prior[k]) if days else None,
        })
    cats.sort(key=lambda d: -d["n"])
    return {"total": total, "cats": cats}


def headline(db, ws, sov, gaps, ledger, role="admin", senti=None, outlets=None):
    """Three sentences a person can repeat in a meeting.

    The third sentence is audience-specific: an operator gets listening-coverage
    status; a client gets sentiment (when scored) or how concentrated the
    conversation is.
    """
    out = []
    focus = next((b for b in sov if b["focus"]), None)
    pairs = indistinguishable_pairs(sov)
    if focus:
        out.append({
            "kind": "share",
            "text": f"{focus['name']} holds {focus['p']*100:.1f}% of collected mentions, "
                    f"with a 95% interval of {focus['lo']*100:.1f}–{focus['hi']*100:.1f}%.",
            "sub": (f"{len(pairs)} brand pairs have overlapping intervals, so their "
                    f"ordering is not supportable from this data."
                    if pairs else "No overlapping intervals: the ranking is supportable."),
        })
    if gaps:
        top = gaps[0]
        out.append({
            "kind": "gap",
            "text": f"{len(gaps)} outlets have covered the competitor set and never "
                    f"mentioned {focus['name'] if focus else 'the focus brand'}.",
            "sub": f"Largest is {top['outlet']} with {top['total']} competitor mentions. "
                   f"This is a target list, not a score.",
        })
    if role == "admin":
        active = [l for l in ledger if l["state"] in ("collected", "sampled")]
        pending = [l for l in ledger if l["state"] == "failed"]
        nonest = [l for l in ledger
                  if l["state"] in ("collected", "sampled") and not l["estimable"]]
        out.append({
            "kind": "coverage",
            "text": f"{len(active)} of {len(ledger)} connectable surfaces are active.",
            "sub": (f"{len(pending)} await credentials. {len(nonest)} active surfaces do not "
                    f"yet have enough independent sources for coverage estimation."),
        })
        return out

    focus_senti = next((s for s in (senti or []) if s.get("focus")), None)
    if focus_senti and focus_senti["scored"]:
        share = focus_senti["neg_share"] or 0
        half = max(share - (focus_senti["neg_lo"] or 0),
                   (focus_senti["neg_hi"] or 0) - share) * 100
        out.append({
            "kind": "sentiment",
            "text": f"{focus_senti['name']} negative sentiment is {share*100:.0f}% "
                    f"(±{half:.0f}) of {focus_senti['scored']} scored English mentions.",
            "sub": (f"{focus_senti['pos']} positive, {focus_senti['neu']} neutral, "
                    f"{focus_senti['neg']} negative. English only."),
        })
    elif outlets:
        sov_total = sum(b["n"] or 0 for b in sov) or 1
        top3 = outlets[:3]
        covered = min(sum(n for _o, n in top3), sov_total)
        out.append({
            "kind": "concentration",
            "text": f"The top {len(top3)} outlets carry {covered/sov_total*100:.0f}% "
                    f"of the tracked conversation.",
            "sub": (", ".join(o for o, _n in top3) + "." if top3 else
                    "Not enough outlet data yet."),
        })
    return out


# ------------------------------------------------------------- action cards
_TONE_RANK = {"risk": 0, "watch": 1, "opportunity": 2, "ok": 3}


def _recent_windows(db, ws, days=7):
    """Per-brand match counts for the last `days` days and the `days` before
    that, from any `published_at` that resolves to a day (ISO or RFC-822)."""
    rows = q.recent_window_rows(db.session, ws)
    today = datetime.now(timezone.utc).date()
    recent_from = today - timedelta(days=days)
    prior_from = today - timedelta(days=2 * days)
    win = defaultdict(lambda: [0, 0])          # [recent, prior]
    for name, raw in rows:
        day = _day_bucket(raw)
        if not day:
            continue
        try:
            d = datetime.strptime(day, "%Y-%m-%d").date()
        except ValueError:
            continue
        if d > recent_from:
            win[name][0] += 1
        elif d > prior_from:
            win[name][1] += 1
    return {name: tuple(v) for name, v in win.items()}


def action_cards(db, ws, sov, gaps, ledger, langs, senti, role="admin"):
    """A short, ranked list of things a person could act on this week.

    Every card has to survive its own uncertainty: momentum uses
    `stats.delta_is_real`, sentiment gaps use non-overlapping Wilson intervals,
    and anything that would flip on a handful of items is not shown.
    """
    cards = []
    focus = next((b for b in sov if b["focus"]), None)
    focus_name = focus["name"] if focus else None

    # Momentum — the sharpest brand whose share-of-window shift is real.
    windows = _recent_windows(db, ws)
    n_recent = sum(v[0] for v in windows.values())
    n_prior = sum(v[1] for v in windows.values())
    if n_recent and n_prior:
        ranked = sorted(windows.items(), key=lambda kv: abs(kv[1][0] - kv[1][1]),
                        reverse=True)
        for name, (k_recent, k_prior) in ranked:
            if k_recent == k_prior or not delta_is_real(k_recent, n_recent,
                                                        k_prior, n_prior):
                continue
            up = k_recent > k_prior
            is_focus = name == focus_name
            tone = "risk" if up != is_focus else "opportunity"
            cards.append({
                "tone": tone, "tag": "Momentum",
                "title": f"{name} {'gaining' if up else 'losing'} share of coverage",
                "body": (f"{k_recent} matches in the last 7 days, "
                         f"{'up' if up else 'down'} from {k_prior} the week before."),
                "stat": f"{'▲' if up else '▼'} {k_prior} → {k_recent}",
                "action": {"label": "See the mentions", "href": "/evidence"},
            })
            break

    # Coverage gap — the biggest outlet the focus brand is absent from.
    if gaps:
        g = gaps[0]
        cards.append({
            "tone": "opportunity", "tag": "Coverage gap",
            "title": f"{g['outlet']} covers the competitors, not {focus_name or 'the focus brand'}",
            "body": (f"{g['total']} competitor mention{'s' if g['total'] != 1 else ''} here, "
                     f"none for {focus_name or 'the focus brand'}."),
            "stat": f"{g['total']} competitor mentions",
            "action": {"label": "Open this outlet",
                       "href": f"/evidence?outlet={quote(g['outlet'])}"},
        })

    # Review backlog — gated matches with no gold label yet.
    backlog = q.review_backlog_count(db.session, ws)
    if backlog:
        cards.append({
            "tone": "watch", "tag": "Calibration",
            "title": f"{backlog} gated match{'es' if backlog != 1 else ''} unreviewed",
            "body": ("Label these to verify the gated rule counts and get a "
                     "precision figure per rule."),
            "stat": f"{backlog} to label",
            "action": {"label": "Work the review queue", "href": "/review"},
        })

    # Estimability — an active client-safe surface without a second source.
    nonest = [l for l in ledger
              if l["state"] in ("collected", "sampled") and not l["estimable"]]
    if nonest:
        s = nonest[0]
        cards.append({
            "tone": "watch", "tag": "Coverage estimation",
            "title": f"{s['surface'].replace('_', ' ').title()} has one source",
            "body": ("Add a second independent source on this surface to estimate "
                     "total coverage."),
            "stat": f"{s['n']} of 2 sources",
            "action": {"label": "Add a source key", "href": "/admin#keys"},
        })

    # Roman Urdu reach — unscored by design, worth stating if it is large.
    ru = next((l for l in langs if l["lang"] == "roman_urdu"), None)
    if ru and ru["pct"] >= 0.15:
        cards.append({
            "tone": "watch", "tag": "Language reach",
            "title": f"{ru['pct']*100:.0f}% of the conversation is Roman Urdu",
            "body": ("Tracked and searchable. Sentiment is scored for English, so "
                     "the sentiment split reflects English mentions."),
            "stat": f"{ru['n']} mentions",
            "action": None,
        })

    # Sentiment — a real, separable negative-share gap against a competitor.
    scored_total = sum(s["scored"] for s in senti)
    if scored_total and focus:
        f = next((s for s in senti if s["focus"]), None)
        if f and f["scored"] and f["neg_share"] is not None:
            worse_than = None
            for s in senti:
                if s["focus"] or not s["scored"] or s["neg_share"] is None:
                    continue
                if (f["neg_share"] > s["neg_share"] and
                        delta_is_real(f["neg"], f["scored"], s["neg"], s["scored"])):
                    worse_than = s
                    break
            if worse_than:
                cards.append({
                    "tone": "risk", "tag": "Sentiment",
                    "title": f"{f['name']} negativity runs above {worse_than['name']}",
                    "body": (f"{f['neg_share']*100:.0f}% negative for {f['name']} vs "
                             f"{worse_than['neg_share']*100:.0f}% for {worse_than['name']}, "
                             f"on scored English mentions."),
                    "stat": f"{f['neg']}/{f['scored']} negative",
                    "action": {"label": "Read the negative mentions", "href": "/evidence"},
                })
            else:
                cards.append({
                    "tone": "ok", "tag": "Sentiment",
                    "title": f"{f['name']} negative share is {f['neg_share']*100:.0f}%",
                    "body": (f"95% range {f['neg_lo']*100:.0f}–{f['neg_hi']*100:.0f}%, "
                             f"over {f['scored']} scored English mentions."),
                    "stat": f"{f['neg']}/{f['scored']} negative",
                    "action": {"label": "Open evidence", "href": "/evidence"},
                })

    if role != "admin":
        # Operator to-dos (review queue, adding source keys) are not the
        # client's to action, so they do not belong on the client overview.
        cards = [c for c in cards if not (
            c.get("action") and c["action"]["href"].startswith(("/admin", "/review")))]

    cards.sort(key=lambda c: _TONE_RANK.get(c["tone"], 9))
    cards = cards[:4]
    if not cards:
        cards.append({
            "tone": "ok", "tag": "Steady",
            "title": "No significant change this period",
            "body": "Share of voice, sentiment and coverage are holding steady.",
            "stat": None, "action": None,
        })
    return cards
