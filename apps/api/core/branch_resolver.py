"""Branch resolver: map a mention's text to one physical branch of a catalogue.

Deterministic and auditable -- a small alias table per branch, a fixed weight per
signal, and a confidence floor below which the mention stays *unresolved* rather
than guessed. ``Resolver`` holds one catalogue; ``core/branches.py`` builds the
Bank Alfalah PoC one and ``for_workspace`` builds a tenant's own from its
``location`` rows (aliases derived from name / city / address by fixed rules).
"""
import re

_ALIAS_W = 3
_NAME_CITY_W = 3      # leading name token AND the city, both present
_CODE_W = 4
_MIN_SCORE = 3
_DENOM = 6.0
_GENERIC = re.compile(
    r"\b(branch|office|bancassurance|banca|takaful|il|i\.l\.|new|center|centre|"
    r"csd|liberty|falcon)\b", re.I)


def _rx(phrase):
    return re.compile(r"\b" + re.escape(phrase).replace(r"\ ", r"\s+") + r"\b", re.I)


class Resolver:
    def __init__(self, entries):
        """entries: (key, name, code, city, [alias phrases]); ``code`` may be None."""
        self.entries = list(entries)
        self._compiled = []
        for key, name, code, city, aliases in self.entries:
            lead = re.split(r"[ ,/(]", name.strip())[0]
            same_as_city = lead.lower() == (city or "").lower()
            self._compiled.append((
                key, name, code, city, [_rx(a) for a in aliases],
                _rx(lead) if lead and not same_as_city else None,
                _rx(city) if city else None,
                re.compile(r"\bbranch\s*(?:code\s*)?#?0*" + re.escape(code.lstrip("0") or "0") + r"\b", re.I)
                if code and code.isdigit() else None))

    def catalog(self):
        return [{"key": k, "name": n, "code": c, "city": ct}
                for k, n, c, ct, *_ in self._compiled]

    def resolve_by_name(self, raw_name):
        """Exact display-name match first, then ``resolve``'s looser signals."""
        body = (raw_name or "").strip()
        if not body:
            return None
        norm = re.sub(r"\s+", " ", body).strip().lower()
        for key, name, *_ in self.entries:
            if re.sub(r"\s+", " ", name).strip().lower() == norm:
                return key, "exact_name", 1.0
        return self.resolve(body)

    def resolve(self, text):
        """(branch_key, method, confidence) for the best match, or None. Ties
        between branches resolve to None."""
        body = text or ""
        if not body.strip():
            return None
        scored = []
        for key, _n, _c, _ct, aliases, name_tok, city_rx, code_rx in self._compiled:
            score, method = 0, None
            if any(rx.search(body) for rx in aliases):
                score += _ALIAS_W
                method = "alias"
            if name_tok and city_rx and name_tok.search(body) and city_rx.search(body):
                score += _NAME_CITY_W
                method = method or "name+city"
            if code_rx and code_rx.search(body):
                score += _CODE_W
                method = "code"
            if score >= _MIN_SCORE:
                scored.append((score, key, method))
        if not scored:
            return None
        scored.sort(reverse=True)
        if len(scored) > 1 and scored[0][0] == scored[1][0]:
            return None
        top_score, key, method = scored[0]
        return key, method, round(min(top_score / _DENOM, 1.0), 2)


def derive_aliases(name, city, address):
    """Alias phrases from a location's own fields -- a fixed rule, nothing learned.
    The cleaned name (+ city), and the street/area in the address when it is
    two or more words. A bare city is never an alias (it would claim every
    mention of that city)."""
    out = []
    core = re.sub(r"\(.*?\)", " ", name or "")
    core = re.sub(r"\s+", " ", _GENERIC.sub(" ", core.replace(",", " "))).strip()
    if city:
        core = re.sub(rf"\b{re.escape(city)}\b", " ", core, flags=re.I)
        core = re.sub(r"\s+", " ", core).strip(" ,-")
    if len(core) >= 4 and core.lower() != (city or "").lower():
        out.append(core if not city else f"{core} {city}")
        out.append(f"{core} branch")
    full = re.sub(r"\(.*?\)", " ", name or "").replace(",", " ")
    full = re.sub(r"\s+", " ", full).strip()
    if len(full.split()) >= 2 and full.lower() != (city or "").lower():
        out.append(full)
    for part in [p.strip() for p in (address or "").split(",")][:3]:
        if len(re.findall(r"[A-Za-z]{3,}", part)) >= 2 and not re.search(
                r"\b(floor|plot|office|shop|flat|opposite|near|mall|plaza)\b|\d", part, re.I):
            out.append(part)
    return list(dict.fromkeys(a for a in out if a))


def from_locations(rows):
    """Resolver over ``location`` rows (dicts from db.repositories.locations)."""
    return Resolver((r["key"], r["name"], None, r.get("city") or "",
                     derive_aliases(r["name"], r.get("city"), r.get("address")))
                    for r in rows if r.get("kind", "branch") != "atm")


def for_workspace(db, ws):
    """The workspace's own resolver, else the Bank Alfalah PoC catalogue."""
    from . import branches
    session = getattr(db, "session", None)
    if session is not None:
        from db.repositories import locations
        rows = locations.list_all(session, ws)
        if rows:
            return from_locations(rows)
    return branches.DEFAULT
