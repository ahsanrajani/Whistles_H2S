"""Entity resolution, driven from the DB so /admin can edit rules live.

The rules are data, not code, but the *shape* of the rules is deliberate:
a safe list that matches on its own, a gated list that only matches when
banking context co-occurs, and an exclusion list for same-group entities.
"""
import json
import re

_F = re.IGNORECASE

SEED = [
    {
        "name": "Bank Alfalah", "is_focus": 1,
        "safe": [r"\bbank\s*al[- ]?falah\b", r"\bbankalfalah\b"],
        # `alfalah` collides with Al-Falah University (Faridabad), Al Falah
        # Academy (Norcross GA), Alfalah Residence (Riyadh), the Al Falah
        # district of Abu Dhabi. `alfa` — the app customers actually name —
        # collides with Alfa Romeo, Alfa Laval, Alfa Lebanon and "alpha".
        "gated": {r"\bal[- ]?falah\b": "alfalah_bare", r"\balfa\b": "alfa_app"},
        "context": [r"\bbank(ing)?\b", r"\baccount\b", r"\bdebit\b",
                    r"\bcredit\s*card\b", r"\batm\b", r"\bibft\b", r"\braast\b",
                    r"\btransfer\b", r"\bbranch\b", r"\bapp\b", r"\bcheque\b",
                    r"\bloan\b", r"\bdeposit\b", r"\bbalance\b", r"\bswift\b",
                    r"\bpkr\b", r"\brupees?\b", r"\bpayment\b", r"\bcard\b"],
        "exclude": [
            [r"\balfalah\s+(asset\s+management|investments?|insurance|securities|ghp)\b",
             "sibling legal entity"],
            [r"\bal[- ]?falah\s+(university|academy|college|school|residence|trust)\b",
             "unrelated Alfalah"],
            [r"\bbank\s*alfalah\s*cup\b", "defunct 2003 sponsorship"],
        ],
    },
    {"name": "Meezan Bank", "is_focus": 0,
     "safe": [r"\bmeezan\s*bank\b", r"\bmeezanbank\b"],
     "gated": {r"\bmeezan\b": "meezan_bare"},
     "context": [r"\bbank(ing)?\b", r"\bislamic\b", r"\baccount\b", r"\bbranch\b"],
     "exclude": []},
    {"name": "HBL", "is_focus": 0,
     "safe": [r"\bhabib\s*bank\b", r"\bhbl\b"],
     "gated": {}, "context": [], "exclude": [[r"\bhbl\s*psl\b", "cricket sponsorship"]]},
    {"name": "UBL", "is_focus": 0,
     "safe": [r"\bunited\s*bank\s*limited\b", r"\bubl\b"],
     "gated": {}, "context": [], "exclude": []},
]


def load(db, workspace_id):
    from db import repositories as repo
    return repo.brands.match_rules(db.session, workspace_id)


def _any(pats, text):
    return any(re.search(p, text, _F) for p in pats)


def classify(text, brands):
    """-> [(brand_id, rule, needs_review, excluded, reason)]"""
    text = text or ""
    out = []
    for b in brands:
        rule = None
        review = 0
        if _any(b["safe"], text):
            rule = "exact_name"
        else:
            for pat, rname in (b["gated"] or {}).items():
                if re.search(pat, text, _F):
                    if _any(b["context"], text):
                        # Gated hits are never counted silently. They enter the
                        # precision queue by construction.
                        rule, review = rname, 1
                    break
        if not rule:
            continue
        excluded, reason = 0, None
        for pair in (b["exclude"] or []):
            if re.search(pair[0], text, _F):
                excluded, reason = 1, pair[1]
                break
        out.append((b["id"], rule, review, excluded, reason))
    return out


ROMAN_URDU = [r"\bhai\b", r"\bnahi\b", r"\bnhi\b", r"\bkya\b", r"\bkar\b",
              r"\bmera\b", r"\bapna\b", r"\bbohat\b", r"\bbht\b", r"\bacha\b",
              r"\bkoi\b", r"\bkuch\b", r"\bwala\b", r"\bpaisa\b", r"\bpese\b",
              r"\bkhata\b", r"\bmilta\b", r"\bhogaya\b", r"\byar\b", r"\bbhai\b"]


def guess_lang(text):
    """Triage only. Its single job is deciding sentiment eligibility."""
    t = (text or "").lower()
    if re.search(r"[\u0600-\u06FF]", t):
        return "ur"
    if sum(1 for p in ROMAN_URDU if re.search(p, t)) >= 2:
        return "roman_urdu"
    return "en" if t.strip() else "unknown"


def search_terms(brands):
    """Collection terms are deliberately broader than match rules: collect
    wide, reject centrally, so precision is measurable rather than assumed."""
    terms = []
    for b in brands:
        terms.append(b["name"])
        for pat in b["safe"]:
            # Turn a regex back into a plain phrase only when it is safely
            # literal. A half-unescaped pattern makes a worse query than the
            # brand name we already have, so anything doubtful is skipped.
            lit = pat.replace(r"\b", "").replace(r"\s*", " ").replace(r"\s+", " ")
            if re.search(r"[\\\[\]()?*+|^$]", lit):
                continue
            lit = re.sub(r"\s+", " ", lit).strip()
            if 3 < len(lit) < 40 and lit.lower() not in [t.lower() for t in terms]:
                terms.append(lit)
    return terms[:8]
