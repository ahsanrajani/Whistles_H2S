"""Pre-approval compliance check for content-calendar drafts.

Deterministic only. Each rule is a named regex with a fixed integer weight; a
draft's score is the sum of the weights of the *distinct* rules it trips, and
the severity band comes from that score. No model scores anything -- the rules
and bands below are the whole policy and ``check`` returns them, so every flag
is auditable back to a rule. Drafts are also held to the same standard as the
scam scanner (``core/scam.py``): a bank post that itself trips a scam signal
(WhatsApp contact, shortened link, phone number...) is flagged.

The only model involvement is ``rewrite``, which asks Gemini for a safer
version of the text, and is never auto-applied and never changes the score.
Mock mode (no GOOGLE_API_KEY / OPENROUTER_API_KEY) returns a deterministic
rewrite so the flow works offline.
"""
import re
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import text as _sql

from integrations.llm import panel

from . import regulatory, scam

# (key, label, weight, pattern, guidance, regulatory topic). Order = display order.
RULES = [
    ("guaranteed_return", "Guaranteed or risk-free return claim", 5,
     r"\bguarantee[sd]?\s+(?:returns?|profits?|income|growth|yield)\b"
     r"|\bassured\s+(?:returns?|profits?)\b|\brisk[-\s]?free\b|\bno\s+risk\b"
     r"|\bzero\s+risk\b|\b100\s?%\s+(?:safe|secure|returns?)\b|\bdouble\s+your\s+money\b",
     "Returns on investments cannot be guaranteed. Remove the claim or state the "
     "return as illustrative and subject to market risk.", "consumer"),
    ("unrealistic_yield", "Headline yield without basis", 3,
     r"\b\d{2,3}\s?%\s*(?:returns?|profit|monthly|per\s+month|p\.?m\.?|weekly)\b",
     "A double-digit monthly or weekly figure reads as a promise. Give the "
     "period, the source and the basis of any rate quoted.", "consumer"),
    ("sensitive_data_request", "Asks customers for OTP, PIN or card details", 6,
     r"\b(?:share|send|enter|provide|confirm|verify|reply\s+with)\b[^.\n]{0,40}"
     r"\b(?:otp|pin|password|cvv|card\s+number|cnic|account\s+number)\b",
     "Banks never ask for OTP, PIN or full card details on social media. This "
     "wording also trains customers to fall for scams.", "cyber"),
    ("regulator_endorsement", "Implied regulator endorsement", 4,
     r"\b(?:sbp|secp|state\s+bank)\s+(?:approved|endorsed|guaranteed|backed)\b"
     r"|\b(?:approved|endorsed|guaranteed)\s+by\s+(?:the\s+)?(?:sbp|secp|state\s+bank)\b",
     "Regulator approval or backing must not be implied unless it is exact "
     "and documented.", "enforcement"),
    ("urgency_pressure", "Pressure or urgency wording", 2,
     r"\b(?:limited\s+time|act\s+now|last\s+chance|hurry|only\s+today"
     r"|expires?\s+tonight|don'?t\s+miss)\b",
     "Urgency pushes customers to decide before reading terms. Soften it or "
     "give a real end date.", "consumer"),
    ("superlative", "Unsubstantiated superlative", 1,
     r"\b(?:best|number\s+one|no\.?\s?1|#1|unbeatable|lowest\s+ever)\b",
     "Back a 'best' or '#1' claim with a named source and date, or drop it.",
     "consumer"),
]

# Rule that fires on an *absence*: an investment-style claim with no disclaimer.
_PRODUCT_RX = re.compile(
    r"\b(?:invest\w*|mutual\s+fund|returns?|profits?|dividends?|savings?\s+plan"
    r"|\bnav\b|stocks?|equity|sukuk|term\s+deposit)\b", re.I)
_DISCLAIMER_RX = re.compile(
    r"past\s+performance|subject\s+to\s+(?:market\s+)?risk|terms\s+(?:and|&)\s+conditions"
    r"|\bt&cs?\b|risk\s+disclosure|read\s+the\s+offering|not\s+guaranteed"
    r"|regulated\s+by|\bsbp\b|\bsecp\b|shariah\s+(?:board|compliant)", re.I)
_MISSING_DISCLAIMER = (
    "missing_disclaimer", "Investment wording without a risk disclaimer", 3,
    "Add a short disclaimer (for example 'Returns are not guaranteed. Subject to "
    "market risk. Terms apply.').", "consumer")

SAFE_DISCLAIMER = "Returns are not guaranteed. Subject to market risk. Terms apply."

# Scam-scanner signals reused on outgoing copy. Weight is the scanner's own.
_SCAM_REUSE = ("whatsapp", "phone", "short_link", "telegram", "contact_lure",
               "payout_lure", "impersonation")
_SCAM_GUIDANCE = (
    "The same pattern is what the scam scanner flags on comments. Use only "
    "official channels and the brand's verified website or app.")

BANDS = [("high", "Fix before approval", 7), ("review", "Compliance review", 3),
         ("note", "Minor note", 1), ("clear", "Clear", 0)]
_MODEL_ID = "gemini"

_COMPILED = [(k, lbl, w, re.compile(p, re.I), g, t) for k, lbl, w, p, g, t in RULES]
_SCAM_BY_KEY = {k: (lbl, w) for k, lbl, w, _rx in scam.SIGNALS}
_SCAM_RX = {k: re.compile(p, re.I) for k, _l, _w, p in scam.SIGNALS}


def severity_of(score: int) -> str:
    for key, _label, floor in BANDS:
        if score >= floor:
            return key
    return "clear"


def policy() -> dict:
    return {
        "rules": [{"key": k, "label": lbl, "weight": w, "topic": t}
                  for k, lbl, w, _rx, _g, t in _COMPILED]
        + [{"key": _MISSING_DISCLAIMER[0], "label": _MISSING_DISCLAIMER[1],
            "weight": _MISSING_DISCLAIMER[2], "topic": _MISSING_DISCLAIMER[4]}]
        + [{"key": f"scam:{k}", "label": _SCAM_BY_KEY[k][0],
            "weight": _SCAM_BY_KEY[k][1], "topic": "cyber"} for k in _SCAM_REUSE],
        "bands": [{"key": k, "label": lbl, "min_score": floor} for k, lbl, floor in BANDS],
    }


# A sentence that warns customers ("we never ask for your OTP", "beware of fake
# accounts") has to be able to name the thing it warns about, so a negated
# request and word-only scam signals are not flagged inside awareness copy.
# Concrete contact details (a phone number, a link) are flagged regardless.
_NEGATION_RX = re.compile(r"\b(?:never|not|no|don'?t|do\s+not|without)\b[^.\n]{0,70}$", re.I)
_AWARENESS_RX = re.compile(
    r"\b(?:beware|scams?|scammers?|fake|fraud(?:ulent)?|phishing|impersonat\w*"
    r"|never\s+ask|we\s+never|do\s+not|don'?t|not\s+(?:from|ours|us))\b", re.I)
_WORD_ONLY_SCAM = {"whatsapp", "telegram", "payout_lure", "contact_lure", "impersonation"}


def _phrases(rx, body: str, *, skip_negated: bool = False) -> list[str]:
    out = []
    for m in rx.finditer(body):
        if skip_negated and _NEGATION_RX.search(body[max(0, m.start() - 80):m.start()]):
            continue
        out.append(re.sub(r"\s+", " ", m.group(0)).strip())
    return out[:3]


def check(body: str) -> dict:
    """Score one draft. Pure function of the text."""
    body = body or ""
    findings = []
    for key, label, weight, rx, guidance, topic in _COMPILED:
        found = _phrases(rx, body, skip_negated=(key == "sensitive_data_request"))
        if found:
            findings.append({"key": key, "label": label, "weight": weight,
                             "matches": found, "guidance": guidance, "topic": topic})
    if _PRODUCT_RX.search(body) and not _DISCLAIMER_RX.search(body):
        key, label, weight, guidance, topic = _MISSING_DISCLAIMER
        findings.append({"key": key, "label": label, "weight": weight,
                         "matches": _phrases(_PRODUCT_RX, body), "guidance": guidance,
                         "topic": topic})
    awareness = bool(_AWARENESS_RX.search(body))
    for key in _SCAM_REUSE:
        if awareness and key in _WORD_ONLY_SCAM:
            continue
        found = _phrases(_SCAM_RX[key], body)
        if found:
            label, weight = _SCAM_BY_KEY[key]
            findings.append({"key": f"scam:{key}", "label": label, "weight": weight,
                             "matches": found, "guidance": _SCAM_GUIDANCE, "topic": "cyber"})
    score = sum(f["weight"] for f in findings)
    return {"score": score, "severity": severity_of(score), "findings": findings,
            "awareness_context": awareness, "checked_chars": len(body),
            "policy": policy()}


def _related_notices(db, ws, body: str, findings: list[dict], limit: int = 3) -> list[dict]:
    topics = set(regulatory.classify_text(body)) | {f["topic"] for f in findings}
    if not topics:
        return []
    feed = regulatory.summarize(db, ws)
    out = []
    for notice in feed["notices"]:
        shared = sorted(topics & set(notice["topics"]))
        if shared:
            out.append({"id": notice["id"], "regulator": notice["regulator"],
                        "title": notice["title"], "url": notice["url"],
                        "published_at": notice["published_at"], "topics": shared})
        if len(out) >= limit:
            break
    return out


def _mock_rewrite(body: str, findings: list[dict]) -> str:
    fixed = body
    for f in findings:
        for phrase in f["matches"]:
            if not f["key"].startswith("missing"):
                fixed = re.sub(re.escape(phrase), "", fixed, flags=re.I)
    fixed = re.sub(r"[ \t]{2,}", " ", fixed)
    fixed = re.sub(r"\s+([,.!?])", r"\1", fixed).strip()
    if any(f["key"] in ("missing_disclaimer", "guaranteed_return", "unrealistic_yield")
           for f in findings) and SAFE_DISCLAIMER not in fixed:
        fixed = f"{fixed}\n\n{SAFE_DISCLAIMER}".strip()
    return fixed


def rewrite(body: str, findings: list[dict], *, keys: dict | None = None) -> dict:
    """A safer version of ``body`` -- advice only, never auto-applied."""
    keys = keys or {}
    if not findings:
        return {"text": body, "mock": not (keys.get("GOOGLE_API_KEY")
                                           or keys.get("OPENROUTER_API_KEY"))}
    if not keys.get("GOOGLE_API_KEY") and not keys.get("OPENROUTER_API_KEY"):
        return {"text": _mock_rewrite(body, findings), "mock": True}
    issues = "; ".join(f"{f['label']} ({', '.join(repr(m) for m in f['matches'])})"
                       for f in findings)
    prompt = "\n".join([
        "You are a compliance editor for a bank's social media team in Pakistan.",
        f"Rewrite the post below so it fixes these problems: {issues}.",
        "Keep the meaning, tone and length close to the original. Never promise "
        "returns. Never ask for OTP, PIN or card details. Never tell customers to "
        "contact the bank on WhatsApp or through a shortened link. Add a one-line "
        "risk disclaimer if the post talks about investing, returns or profit.",
        "Return only the rewritten post. No markdown, no preamble, no quotes.",
        "", "POST:", body,
    ])
    try:
        _provider, _model, out = panel.ask(_MODEL_ID, prompt, keys=keys)
    except Exception as exc:                                          # noqa: BLE001
        return {"text": _mock_rewrite(body, findings), "mock": True, "error": str(exc)}
    return {"text": out.strip(), "mock": False}


def review(db, ws, body: str, *, want_rewrite: bool = False,
           keys: dict | None = None) -> dict:
    """The full pre-approval verdict: score, findings, nearby regulator notices
    and (on request) a suggested rewrite."""
    out = check(body)
    out["related_notices"] = _related_notices(db, ws, body, out["findings"])
    out["rewrite"] = (rewrite(body, out["findings"], keys=keys)
                      if want_rewrite and out["findings"] else None)
    return out


def risk_map(session, ws: int, start: date, end: date) -> dict:
    """{content id: {severity, score}} for every item in the window, so the
    calendar can badge a risky draft without opening it."""
    lo = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
    hi = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
    rows = session.execute(_sql("""
        SELECT id, body FROM content_item
        WHERE workspace_id = :ws AND state <> 'published'
          AND ((scheduled_for >= :lo AND scheduled_for < :hi) OR scheduled_for IS NULL)
    """), {"ws": ws, "lo": lo, "hi": hi}).mappings().all()
    out = {}
    for row in rows:
        res = check(row["body"])
        if res["severity"] != "clear":
            out[row["id"]] = {"severity": res["severity"], "score": res["score"]}
    return {"risk": out}
