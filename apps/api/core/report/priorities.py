"""The ranked, clickable "what to act on" list shared by the Overview strip and
the executive PDF."""
from .. import alerts, branch_perf, switch_intent
from .common import _ago

_SEVERITY_RANK = {"critical": 0, "warning": 1, "info": 2}


def priorities(db, ws):
    """Ranked, clickable action items across the analysis surfaces."""
    out = []
    evaluation = alerts.evaluate(db, ws)
    for rule in evaluation["firing"]:
        out.append({
            "key": rule["key"], "severity": rule["severity"],
            "title": rule["title"], "detail": rule["detail"],
            "href": rule["href"], "when": None,
        })

    switch_r = switch_intent.scan(db, ws)
    at_risk = switch_r["summary"]["high"] + switch_r["summary"]["likely"]
    if at_risk >= 3:
        named = sum(1 for row in switch_r["queue"]
                    if row["band"] in ("high", "likely") and row.get("competitor_named"))
        out.append({
            "key": "switch_at_risk", "severity": "warning",
            "title": f"{at_risk} customers likely to switch",
            "detail": f"{switch_r['summary']['high']} high / {switch_r['summary']['likely']} likely"
                      + (f" · {named} name a rival bank" if named else ""),
            "href": "/switch-intent", "when": None,
        })

    branches_r = branch_perf.scan(db, ws)
    flagged = [b for b in branches_r["branches"]
               if b["band"] in ("high", "elevated") and b["last_flag_at"]]
    flagged.sort(key=lambda b: b["last_flag_at"], reverse=True)
    if flagged:
        recent = flagged[0]
        when = _ago(recent["last_flag_at"])
        branch_items = [i for i in out if i["key"].startswith("branch_")]
        branch_alert = next((i for i in branch_items if i["severity"] == "critical"),
                            branch_items[0] if branch_items else None)
        if branch_alert is not None:
            branch_alert["when"] = when
            branch_alert["detail"] += f" · most recent {recent['name']}"
        else:
            out.append({
                "key": "branch_recent",
                "severity": "critical" if recent["critical"] else "warning",
                "title": f"Issue at {recent['name']}",
                "detail": (f"{recent['complaints']} complaints, mean {recent['mean_rating']}★"
                           + (f" · {recent['critical']} critical" if recent["critical"] else "")),
                "href": "/branches", "when": when,
            })

    seen, deduped = set(), []
    for item in out:
        if item["key"] in seen:
            continue
        seen.add(item["key"])
        deduped.append(item)
    deduped.sort(key=lambda i: _SEVERITY_RANK.get(i["severity"], 3))
    return deduped
