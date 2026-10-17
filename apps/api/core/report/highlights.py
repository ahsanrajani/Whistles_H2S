"""Everything the executive PDF and the Overview strip need, in one payload."""
from datetime import datetime, timezone

from db.analytics import dashboards as dq

from .. import branch_perf, insights, scam, switch_intent, triage
from .common import _ago
from .priorities import priorities


def highlights(db, ws):
    """Everything the executive PDF and the Overview strip need."""
    focus_name = dq.focus_brand_name(db.session, ws)
    triage_r = triage.scan(db, ws)
    scam_r = scam.scan(db, ws)
    switch_r = switch_intent.scan(db, ws)
    branches_r = branch_perf.scan(db, ws)
    breakdown = insights.sentiment_breakdown(db, ws)
    focus_sent = next((b for b in breakdown if b["focus"]), None)
    sov = [
        {"name": b["name"], "focus": b["focus"], "pct": round(b["p"] * 100, 1)}
        for b in insights.share_of_voice(db, ws) if b["n"]
    ][:5]

    mentions = dq.focus_mention_count(db.session, ws)

    switch_samples = [
        {"text": row["text"], "band": row["band"], "when": _ago(row["published_at"])}
        for row in switch_r["queue"] if row["band"] in ("high", "likely")
    ][:3]
    worst = [
        {"name": b["name"], "city": b["city"], "mean_rating": b["mean_rating"],
         "complaints": b["complaints"], "critical": b["critical"],
         "top_issue": b["top_issue"], "score": b["score"], "band": b["band"],
         "when": _ago(b["last_flag_at"])}
        for b in branches_r["branches"] if b["band"] in ("high", "elevated")
    ][:6]

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "focus_brand": focus_name,
        "priorities": priorities(db, ws),
        "numbers": {
            "mentions": mentions,
            "negative_share_pct": round((focus_sent["neg_share"] or 0) * 100, 1) if focus_sent else None,
            "switch_at_risk": switch_r["summary"]["high"] + switch_r["summary"]["likely"],
            "triage_critical": triage_r["summary"]["critical"],
            "triage_high": triage_r["summary"]["high"],
            "scam_flag_rate_pct": scam_r["summary"]["flag_rate"],
            "branches_flagged": branches_r["summary"]["branches_flagged"],
        },
        "sentiment": {
            "pos": focus_sent["pos"], "neu": focus_sent["neu"], "neg": focus_sent["neg"],
        } if focus_sent else {"pos": 0, "neu": 0, "neg": 0},
        "share_of_voice": sov,
        "switch_samples": switch_samples,
        "worst_branches": worst,
    }
