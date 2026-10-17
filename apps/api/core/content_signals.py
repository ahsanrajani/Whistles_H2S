"""Activity-driven content nudges: what customers are being exposed to right now,
turned into posts the brand should consider publishing.

Three live signals feed it, all already computed elsewhere -- nothing here is
re-scored: the scam scanner on the brand's own comments (``core/scam.py``), the
mention-velocity incident detector (``core/incidents.py``) and the regulatory
feed (``core/regulatory.py``). A nudge always carries its evidence (with a Wilson
interval on any proportion) and a plain template draft, so a person can see why
it was suggested before creating anything. Creating a draft records the signal
that caused it (``content_event`` kind ``signal_origin``) for the closed loop in
``core/content_impact.py``.
"""
from . import content_assist, content_calendar as cc, content_compliance, incidents, regulatory, scam, stats
from .insights import _age_days

_SCAM_WINDOW_DAYS = 14
_SCAM_MIN_FLAGGED = 3
_REG_WINDOW_DAYS = 30
_REG_TOPICS = {"consumer", "cyber", "aml", "enforcement", "digital"}
_REG_LIMIT = 2
# A notice prompts a post only if a banking regulator issued it, or it names the brand
# (the feed also carries stock-exchange items about unrelated companies).
_BANKING_REGULATORS = ("sbp", "state bank", "mohtasib", "banking authority", "ombudsman")
DEFAULT_CHANNEL = "meta"

# Most common scam signal -> (post topic, plain draft). Drafts follow the
# compliance rules in core/content_compliance.py (checked by a test).
_SCAM_ANGLES = {
    "whatsapp": ("Fake support on WhatsApp",
                 "Fake accounts are posing as our support team and asking customers to "
                 "chat on WhatsApp. We never ask you to move a conversation to WhatsApp "
                 "or share your OTP, PIN or card details. Use only our verified app, "
                 "website and helpline."),
    "phone": ("Fake helpline numbers in comments",
              "Phone numbers posted in our comments are not ours. Our official helpline "
              "is listed only on our website and in our app. Please do not call numbers "
              "shared by strangers, and never give out your OTP or PIN."),
    "short_link": ("Shortened links in comments",
                   "Links shared in our comments, especially shortened ones, are not from "
                   "us. Open our app or type our website address yourself, and never "
                   "enter your card or login details through a link you were sent."),
    "telegram": ("Fake Telegram channels",
                 "We do not run any Telegram channel for customer support. Messages "
                 "asking you to join one are scams. Contact us only through our verified "
                 "app, website and helpline."),
    "payout_lure": ("Fake prize and refund offers",
                    "Comments claiming you have won a prize or are owed a refund are "
                    "scams. We never announce prizes or refunds in comments, and we never "
                    "ask for your OTP, PIN or card details to release money."),
    "contact_lure": ("Strangers offering help in comments",
                     "If someone replies to your complaint asking you to message them "
                     "privately, it is not us. Our team answers only from our verified "
                     "account. Never share your OTP, PIN or card details."),
    "impersonation": ("Accounts posing as our support team",
                      "Accounts calling themselves official support in our comments are "
                      "not ours. Check for the verified badge and use only our app, "
                      "website and helpline. We never ask for your OTP or PIN."),
}
_SCAM_DEFAULT = _SCAM_ANGLES["impersonation"]


class SignalError(ValueError):
    """The requested signal is no longer active."""


def _scam_nudge(db, ws) -> list[dict]:
    res = scam.scan(db, ws, days=_SCAM_WINDOW_DAYS)
    s = res["summary"]
    if s["flagged"] < _SCAM_MIN_FLAGGED:
        return []
    top = max((sig for sig in res["signals"] if sig["n"]), key=lambda x: x["n"], default=None)
    topic, draft = _SCAM_ANGLES.get(top["key"] if top else "", _SCAM_DEFAULT)
    p, lo, hi = stats.wilson(s["flagged"], s["scanned"])
    return [{
        "key": f"scam:{top['key'] if top else 'general'}",
        "kind": "scam", "severity": "high" if s["high"] else "elevated",
        "title": f"Warn customers: {topic.lower()}",
        "why": (f"{s['flagged']} of {s['scanned']} comments on the brand's own pages tripped "
                f"scam signals in the last {_SCAM_WINDOW_DAYS} days"
                + (f", {s['repeat_offenders']} repeat posters" if s["repeat_offenders"] else "")
                + (f". Most common: {top['label'].lower()}." if top else ".")),
        "evidence": {"flagged": s["flagged"], "scanned": s["scanned"],
                     "rate": round(p, 4), "ci_low": round(lo, 4), "ci_high": round(hi, 4),
                     "high": s["high"], "repeat_offenders": s["repeat_offenders"]},
        "topic": topic, "draft": draft,
        "links": [{"label": f["text"][:80], "url": f["url"]} for f in res["flagged"][:2]
                  if f.get("url")],
    }]


def _incident_nudges(db, ws) -> list[dict]:
    res = incidents.scan(db, ws)
    out = []
    for brand in res["brands"]:
        if not brand["focus"] or brand["status"] == "normal":
            continue
        gated = [i for i in brand["incidents"] if i["gated_in"]]
        latest = (gated or brand["incidents"] or [None])[-1]
        keywords = latest["keywords"][:4] if latest else []
        what = ", ".join(keywords) if keywords else "the service"
        out.append({
            "key": f"incident:{latest['date'] if latest else res['as_of']}",
            "kind": "incident",
            "severity": "high" if brand["status"] == "incident" else "watch",
            "title": f"Acknowledge customer issues: {what}",
            "why": (f"Mentions of the brand are {brand['peak_z']:.1f} standard deviations above "
                    f"their {brand['baseline']['days']}-day baseline"
                    + (f", with incident words: {what}." if keywords else ".")),
            "evidence": {"peak_z": brand["peak_z"], "status": brand["status"],
                         "baseline_mean": brand["baseline"]["mean"],
                         "count": latest["count"] if latest else None,
                         "keywords": keywords},
            "topic": f"Service update: {what}",
            "draft": (f"We know some customers are facing problems with {what}. Our team is "
                      "working on it and we will update this page as soon as we have news. "
                      "For help, use our verified app, website or helpline only. We will "
                      "never ask for your OTP or PIN."),
            "links": [{"label": s["text"][:80], "url": s["url"]}
                      for s in (latest["sample"] if latest else [])[:2] if s.get("url")],
        })
    return out


def _regulatory_nudges(db, ws) -> list[dict]:
    feed = regulatory.summarize(db, ws)
    out = []
    for n in feed["notices"]:
        age = _age_days(n["published_at"])
        if age is None or not 0 <= age <= _REG_WINDOW_DAYS:
            continue
        banking = any(b in n["regulator"].lower() for b in _BANKING_REGULATORS)
        if not (n["names_focus"] or (banking and _REG_TOPICS & set(n["topics"]))):
            continue
        out.append({
            "key": f"regulatory:{n['id']}", "kind": "regulatory",
            "severity": "elevated" if n["names_focus"] else "watch",
            "title": f"Explain the {n['regulator']} notice to customers",
            "why": (f"{n['regulator']} published \"{n['title'][:110]}\" {age} days ago"
                    + (" and it names the brand." if n["names_focus"] else ".")),
            "evidence": {"regulator": n["regulator"], "age_days": age,
                         "topics": n["topics"], "names_brand": n["names_focus"]},
            "topic": n["title"][:120],
            "draft": (f"{n['regulator']} has issued a notice that may affect you: "
                      f"{n['title'][:140]}. Here is what it means for our customers and what, "
                      "if anything, you need to do. Questions? Reach us through our verified "
                      "app, website or helpline."),
            "links": [{"label": n["title"][:80], "url": n["url"]}] if n.get("url") else [],
        })
        if len(out) >= _REG_LIMIT:
            break
    return out


_SEVERITY_ORDER = {"high": 0, "elevated": 1, "watch": 2}


def nudges(db, ws) -> dict:
    items = _incident_nudges(db, ws) + _scam_nudge(db, ws) + _regulatory_nudges(db, ws)
    items.sort(key=lambda n: (_SEVERITY_ORDER[n["severity"]], n["key"]))
    return {"nudges": items,
            "sources": {"scam_window_days": _SCAM_WINDOW_DAYS,
                        "scam_min_flagged": _SCAM_MIN_FLAGGED,
                        "regulatory_window_days": _REG_WINDOW_DAYS}}


def create_draft(db, ws, actor, key: str, *, channel: str = DEFAULT_CHANNEL,
                 keys: dict | None = None) -> dict:
    """Turn one active nudge into a draft on the calendar, with its compliance
    verdict. The draft is plain template text unless an LLM key is configured,
    in which case the caption is polished -- and then checked like any other."""
    found = next((n for n in nudges(db, ws)["nudges"] if n["key"] == key), None)
    if found is None:
        raise SignalError("that signal is no longer active")
    body, mock = found["draft"], True
    if (keys or {}).get("OPENROUTER_API_KEY") or (keys or {}).get("GOOGLE_API_KEY"):
        try:
            polished = content_assist.suggest(db.session, ws, topic=found["topic"],
                                              draft=found["draft"], channel=channel, keys=keys)
            if not polished["mock"] and polished["caption"].strip():
                body, mock = polished["caption"].strip(), False
        except content_assist.ContentAssistError:
            pass
    cid = cc.create(db.session, ws, actor, title=found["title"][:140], body=body,
                    channel=channel)
    cc.record_origin(db.session, cid, actor, {"signal": found["key"], "signal_kind": found["kind"]})
    verdict = content_compliance.check(body)
    return {"id": cid, "title": found["title"], "mock": mock,
            "compliance": {"severity": verdict["severity"], "score": verdict["score"],
                           "flags": [f["label"] for f in verdict["findings"]]}}
