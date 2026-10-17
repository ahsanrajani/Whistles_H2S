"""Impersonation / brand-abuse monitoring.

Defensive only: generate deterministic lookalike-domain permutations of the
focus brand's own domains, then best-effort check each for a live DNS record and
for a certificate seen in Certificate Transparency (crt.sh). Every technique has
a fixed weight and the risk score is the sum of the technique weight plus fixed
bonuses for "resolves" and "seen in CT", so a ranking always traces back to a
rule. Network failures degrade to ``unknown`` / ``unavailable`` — they never
raise.
"""
import json
import socket
import time
import urllib.parse
import urllib.request

# (technique key, label, weight).
TECHNIQUES = [
    ("combo", "Brand + keyword", 4),
    ("subdomain_bait", "Login / secure bait", 3),
    ("transposition", "Adjacent characters swapped", 3),
    ("replacement", "Character look-alike swap", 3),
    ("omission", "Character dropped", 2),
    ("repetition", "Character doubled", 2),
    ("insertion", "Extra character", 2),
    ("tld_swap", "Same name, different TLD", 2),
    ("hyphenation", "Hyphen inserted", 1),
    ("ct_observed", "Seen in Certificate Transparency", 4),
]
_WEIGHT = {key: weight for key, _label, weight in TECHNIQUES}

BANDS = [("high", "High", 8), ("elevated", "Elevated", 5),
         ("watch", "Watch", 2), ("none", "None", 0)]

_RESOLVES_BONUS = 3
_CT_BONUS = 4
_MAX_CANDIDATES = 60
_DEFAULT_BUDGET_S = 6.0
_MULTI_TLD = {"com.pk", "org.pk", "net.pk", "gov.pk", "edu.pk", "co.uk", "com.au"}
_SWAP_TLDS = ["com", "net", "org", "co", "info", "online", "site", "app",
              "com.pk", "pk", "bank"]
_KEYBOARD = {"a": "s", "s": "a", "e": "r", "o": "0", "l": "1", "i": "1",
             "n": "m", "m": "n", "b": "v", "c": "x", "t": "y"}
_BAIT_PREFIX = ["login-", "secure-", "my-", "online-", "portal-"]
_BAIT_SUFFIX = ["-login", "-secure", "-verify", "-online", "-portal", "-help"]
_COMBO_SUFFIX = ["bank", "pk", "official", "care", "support"]


def _norm(domain):
    text = (domain or "").strip().lower()
    if "://" in text:
        text = text.split("://", 1)[1]
    text = text.split("/", 1)[0].split("?", 1)[0]
    return text[4:] if text.startswith("www.") else text


def _split(domain):
    parts = domain.split(".")
    if len(parts) >= 3 and ".".join(parts[-2:]) in _MULTI_TLD:
        return ".".join(parts[:-2]), ".".join(parts[-2:])
    if len(parts) >= 2:
        return ".".join(parts[:-1]), parts[-1]
    return domain, ""


def permutations(domain):
    """Deterministic ``[(candidate_domain, technique_key)]`` for one domain.

    The base domain itself is never returned. Order is stable: by descending
    technique weight, then alphabetically.
    """
    domain = _norm(domain)
    sld, tld = _split(domain)
    dotted = f".{tld}" if tld else ""
    out = {}

    def add(candidate, technique):
        candidate = candidate.lower()
        if candidate and candidate != domain and candidate not in out:
            out[candidate] = technique

    for index in range(len(sld)):
        add(sld[:index] + sld[index + 1:] + dotted, "omission")
        add(sld[:index + 1] + sld[index] + sld[index + 1:] + dotted, "repetition")
        char = sld[index]
        if char in _KEYBOARD:
            add(sld[:index] + _KEYBOARD[char] + sld[index + 1:] + dotted, "replacement")
        add(sld[:index] + char + char + sld[index + 1:] + dotted, "insertion")
    for index in range(len(sld) - 1):
        add(sld[:index] + sld[index + 1] + sld[index] + sld[index + 2:] + dotted,
            "transposition")
    for other in _SWAP_TLDS:
        if other != tld:
            add(f"{sld}.{other}", "tld_swap")
    for prefix in _BAIT_PREFIX:
        add(f"{prefix}{sld}{dotted}", "subdomain_bait")
    for suffix in _BAIT_SUFFIX:
        add(f"{sld}{suffix}{dotted}", "subdomain_bait")
    for suffix in _COMBO_SUFFIX:
        add(f"{sld}{suffix}{dotted}", "combo")
        add(f"{sld}-{suffix}{dotted}", "combo")
    if "-" not in sld and len(sld) > 6:
        add(f"{sld[:len(sld) // 2]}-{sld[len(sld) // 2:]}{dotted}", "hyphenation")

    return sorted(out.items(),
                  key=lambda pair: (-_WEIGHT[pair[1]], pair[0]))


def band_of(score):
    for key, _label, threshold in BANDS:
        if score >= threshold:
            return key
    return "none"


def policy():
    return {
        "techniques": [{"key": k, "label": lbl, "weight": w} for k, lbl, w in TECHNIQUES],
        "bands": [{"key": k, "label": lbl, "min_score": t} for k, lbl, t in BANDS],
        "resolves_bonus": _RESOLVES_BONUS, "ct_bonus": _CT_BONUS,
    }


def _resolve(host):
    try:
        socket.getaddrinfo(host, None)
        return "resolves"
    except socket.gaierror:
        return "nxdomain"
    except Exception:
        return "unknown"


def _ct_query(stem):
    """Distinct lowercase cert names from crt.sh containing ``stem``, or None."""
    url = ("https://crt.sh/?output=json&q="
           + urllib.parse.quote(f"%{stem}%"))
    request = urllib.request.Request(url, headers={"User-Agent": "guru-ears/brand-watch"})
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            rows = json.loads(response.read() or b"[]")
    except Exception:
        return None
    names = set()
    for row in rows if isinstance(rows, list) else []:
        for line in str(row.get("name_value", "")).splitlines():
            line = line.strip().lower().lstrip("*.")
            if stem in line:
                names.add(line)
    return names


def scan(domains, *, resolve=None, ct_query=None, budget_s=_DEFAULT_BUDGET_S,
         clock=time.monotonic):
    """Rank lookalike-domain candidates for the given official domains."""
    resolve = resolve or _resolve
    ct_query = ct_query or _ct_query
    official = []
    for domain in domains or []:
        normalised = _norm(domain)
        if normalised and normalised not in official:
            official.append(normalised)

    if not official:
        return {"official": [], "policy": policy(), "ct_status": "skipped",
                "summary": {"candidates": 0, "resolving": 0, "ct_observed": 0,
                            "dns_checked": 0, "high": 0, "elevated": 0, "watch": 0},
                "candidates": []}

    stems = sorted({_split(domain)[0] for domain in official})
    ct_names, ct_status = set(), "ok"
    for stem in stems:
        result = ct_query(stem)
        if result is None:
            ct_status = "unavailable"
        else:
            ct_names |= result

    candidates = {}
    for domain in official:
        for candidate, technique in permutations(domain):
            candidates.setdefault(candidate, technique)
    for name in sorted(ct_names):
        if name not in official and name not in candidates:
            candidates[name] = "ct_observed"

    ordered = sorted(candidates.items(),
                     key=lambda pair: (-_WEIGHT[pair[1]], pair[0]))[:_MAX_CANDIDATES]

    deadline = clock() + budget_s
    dns_checked = 0
    rows = []
    for candidate, technique in ordered:
        if clock() < deadline:
            dns = resolve(candidate)
            dns_checked += 1
        else:
            dns = "unknown"
        ct_observed = candidate in ct_names
        score = _WEIGHT[technique]
        if dns == "resolves":
            score += _RESOLVES_BONUS
        if ct_observed and technique != "ct_observed":
            score += _CT_BONUS
        rows.append({
            "domain": candidate, "technique": technique,
            "dns": dns, "ct_observed": ct_observed,
            "score": score, "band": band_of(score),
        })

    rows.sort(key=lambda row: (-row["score"], row["domain"]))
    return {
        "official": official,
        "policy": policy(),
        "ct_status": ct_status,
        "summary": {
            "candidates": len(rows),
            "resolving": sum(1 for row in rows if row["dns"] == "resolves"),
            "ct_observed": sum(1 for row in rows if row["ct_observed"]),
            "dns_checked": dns_checked,
            "high": sum(1 for row in rows if row["band"] == "high"),
            "elevated": sum(1 for row in rows if row["band"] == "elevated"),
            "watch": sum(1 for row in rows if row["band"] == "watch"),
        },
        "candidates": rows,
    }
