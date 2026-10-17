"""Anomaly alerting — a delivery layer over the analysis surfaces.

``evaluate`` runs the DB-backed analysis scanners (scam, triage, switch-intent,
incidents, regulatory, sentiment) and applies a set of deterministic threshold
rules; every rule is returned with its current value, its threshold and a
``fired`` flag so the alert always traces back to a number. ``dispatch`` pushes
the firing alerts to a Slack incoming webhook and/or a generic JSON webhook
(wire that one to email / WhatsApp / a queue). No scheduler here — call
``dispatch`` from cron or the UI.
"""
import json
import urllib.request

from . import (branch_perf, incidents, insights, regulatory, scam, source_health,
               switch_intent, triage)

DEFAULT_CONFIG = {
    "scam_flag_rate_pct": 15.0,
    "scam_min_scanned": 20,
    "scam_repeat_offenders": 3,
    "triage_critical": 1,
    "triage_high": 5,
    "switch_high": 3,
    "incident_any": True,
    "regulatory_enforcement_focus": True,
    "negative_share_pct": 40.0,
    "negative_min_scored": 20,
    "branch_rating_floor": 2.8,
    "branch_min_reviews": 5,
    "branch_complaints": 4,
}


def default_config():
    return dict(DEFAULT_CONFIG)


def _config(raw):
    """Merge a stored JSON config (string or dict) over the defaults."""
    merged = dict(DEFAULT_CONFIG)
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            raw = None
    if isinstance(raw, dict):
        for key, value in raw.items():
            if key in merged and isinstance(value, type(merged[key])):
                merged[key] = value
    return merged


def evaluate(db, ws, config=None):
    """All alert rules for a workspace, each with its value / threshold / fired."""
    cfg = _config(config)
    scam_r = scam.scan(db, ws)
    triage_r = triage.scan(db, ws)
    switch_r = switch_intent.scan(db, ws)
    incidents_r = incidents.scan(db, ws)
    regulatory_r = regulatory.summarize(db, ws)
    branches_r = branch_perf.scan(db, ws)
    breakdown = insights.sentiment_breakdown(db, ws)
    focus_sentiment = next((brand for brand in breakdown if brand["focus"]), None)

    alerts = []

    def add(key, severity, title, value, threshold, fired, href, detail):
        alerts.append({
            "key": key, "severity": severity, "title": title,
            "value": value, "threshold": threshold, "fired": bool(fired),
            "href": href, "detail": detail,
        })

    scanned = scam_r["summary"]["scanned"]
    add("scam_flag_rate", "warning", "Scam flag rate elevated",
        scam_r["summary"]["flag_rate"], cfg["scam_flag_rate_pct"],
        scanned >= cfg["scam_min_scanned"]
        and scam_r["summary"]["flag_rate"] >= cfg["scam_flag_rate_pct"],
        "/scam", f"{scam_r['summary']['flagged']} of {scanned} comments flagged")
    add("scam_repeat_offenders", "warning", "Repeat scam commenters",
        scam_r["summary"]["repeat_offenders"], cfg["scam_repeat_offenders"],
        scam_r["summary"]["repeat_offenders"] >= cfg["scam_repeat_offenders"],
        "/scam", f"{scam_r['summary']['repeat_offenders']} commenters with 2+ flagged comments")

    add("triage_critical", "critical", "Critical complaints in the queue",
        triage_r["summary"]["critical"], cfg["triage_critical"],
        triage_r["summary"]["critical"] >= cfg["triage_critical"],
        "/triage", f"{triage_r['summary']['critical']} complaint(s) scored Critical")
    add("triage_high", "warning", "High-risk complaints piling up",
        triage_r["summary"]["high"], cfg["triage_high"],
        triage_r["summary"]["high"] >= cfg["triage_high"],
        "/triage", f"{triage_r['summary']['high']} complaint(s) scored High")

    add("switch_high", "warning", "Elevated switch intent",
        switch_r["summary"]["high"], cfg["switch_high"],
        switch_r["summary"]["high"] >= cfg["switch_high"],
        "/switch-intent", f"{switch_r['summary']['high']} mention(s) at High churn risk")

    incident_brands = [brand["brand"] for brand in incidents_r["brands"]
                       if brand["status"] == "incident"]
    add("incident_firing", "critical", "Mention-velocity incident",
        len(incident_brands), 1,
        cfg["incident_any"] and bool(incident_brands),
        "/incidents", ", ".join(incident_brands) or "none")

    enforcement_hits = [notice for notice in regulatory_r["notices"]
                        if notice["names_focus"] and "enforcement" in notice["topics"]]
    add("regulatory_enforcement", "critical",
        "Regulatory enforcement notice names the focus brand",
        len(enforcement_hits), 1,
        cfg["regulatory_enforcement_focus"] and bool(enforcement_hits),
        "/regulatory", enforcement_hits[0]["title"] if enforcement_hits else "none")

    low_rated = [b for b in branches_r["branches"]
                 if b["mean_rating"] is not None
                 and b["reviews"] >= cfg["branch_min_reviews"]
                 and b["mean_rating"] <= cfg["branch_rating_floor"]]
    add("branch_rating_low", "warning", "Branch rating below floor",
        len(low_rated), 1, bool(low_rated), "/branches",
        ", ".join(f"{b['name']} ({b['mean_rating']}★)" for b in low_rated[:3]) or "none")

    complaint_branches = [b for b in branches_r["branches"]
                          if b["complaints"] >= cfg["branch_complaints"]]
    worst = max(complaint_branches, key=lambda b: b["complaints"], default=None)
    add("branch_complaint_spike", "critical", "Complaint cluster at a branch",
        worst["complaints"] if worst else 0, cfg["branch_complaints"], bool(worst),
        "/branches",
        f"{worst['name']}: {worst['complaints']} complaints, {worst['critical']} critical"
        if worst else "none")

    if focus_sentiment and focus_sentiment["neg_share"] is not None:
        neg_pct = round(focus_sentiment["neg_share"] * 100, 1)
        add("negative_share", "warning", "Negative sentiment share high",
            neg_pct, cfg["negative_share_pct"],
            focus_sentiment["scored"] >= cfg["negative_min_scored"]
            and neg_pct >= cfg["negative_share_pct"],
            "/sentiment",
            f"{focus_sentiment['neg']} of {focus_sentiment['scored']} scored negative")

    # Source health (P2.3): fire when any collector source is stale / failing /
    # circuit-open — i.e. silent beyond 3x its cadence or actively erroring.
    health = source_health.summary(db.session, ws)
    bad = health["unhealthy"]
    add("source_silent", "critical", "A collection source has stopped",
        len(bad), 0, bool(bad), "/admin",
        ", ".join(f"{r['label']} — {r['health']}" for r in bad[:4])
        or "all sources healthy")

    firing = [alert for alert in alerts if alert["fired"]]
    return {
        "config": cfg,
        "alerts": alerts,
        "firing": firing,
        "counts": {
            "rules": len(alerts),
            "firing": len(firing),
            "critical": sum(1 for a in firing if a["severity"] == "critical"),
            "warning": sum(1 for a in firing if a["severity"] == "warning"),
        },
    }


def _post(url, payload, timeout=10):
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "guru-ears/alerts"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return getattr(response, "status", 200)


def render_text(evaluation):
    firing = evaluation["firing"]
    if not firing:
        return "Guru Ears — no alerts firing."
    lines = [f"[{alert['severity'].upper()}] {alert['title']} — {alert['detail']} "
             f"(value {alert['value']} / threshold {alert['threshold']})"
             for alert in firing]
    return f"Guru Ears — {len(firing)} alert(s) firing:\n" + "\n".join(lines)


def dispatch(evaluation, *, slack_url=None, webhook_url=None, poster=_post):
    """Push the firing alerts to the configured channels. Errors are collected,
    not raised, so one bad webhook does not block the other."""
    text = render_text(evaluation)
    targets = [
        ("slack", slack_url, {"text": text}),
        ("webhook", webhook_url, {
            "text": text, "firing": evaluation["firing"],
            "counts": evaluation["counts"],
        }),
    ]
    sent, errors = [], []
    for name, url, payload in targets:
        if not url:
            continue
        try:
            poster(url, payload)
            sent.append(name)
        except Exception as exc:                       # noqa: BLE001 — report, don't crash
            errors.append({"channel": name, "error": str(exc)[:200]})
    return {"sent": sent, "errors": errors,
            "firing": evaluation["counts"]["firing"], "text": text}
