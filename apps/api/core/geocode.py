"""Address -> coordinates via OpenStreetMap Nominatim (free; <=1 request/second,
identifying User-Agent -- https://operations.osmfoundation.org/policies/nominatim/).

Never a guess: each query tier is progressively coarser and the tier that
matched is returned as ``precision`` so the UI can say "approximate". A city
centroid is *not* a branch location, so a result that only resolves to the
city is rejected (returns None) and the location keeps NULL coordinates.
Results outside Pakistan's bounding box are rejected.
"""
import json
import math
import re
import time
import urllib.parse

from . import collector

NOMINATIM = "https://nominatim.openstreetmap.org/search"
UA = "guru-portal-geocoder/1.0"
_PK = (23.5, 60.8, 37.2, 77.9)                       # south, west, north, east
_UNIT = re.compile(
    r"^(?:(?:office|shop|flat|plot|suite|room)\s*(?:no\.?)?\s*#?\s*[\w/\-]+[,\s]+|"
    r"(?:ground|mezzanine|upper ground|\d+(?:st|nd|rd|th))\s+floor[,\s]+|"
    r"(?:m\d|g-\d|\d+[-/]\w+)[,\s]+|\(?shop.*?\)?,?\s*)", re.I)
_NOISE = re.compile(r"\b(opposite|near|besides?|behind|in front of|upper floor of)\b.*?(?=,|$)", re.I)


def _strip_units(address):
    prev = None
    while prev != address:
        prev, address = address, _UNIT.sub("", address.strip())
    return _NOISE.sub("", address).strip(" ,")


def tiers(address, city):
    """[(precision, query)] from most to least specific."""
    clean = _strip_units(address or "")
    parts = [p.strip() for p in clean.split(",") if p.strip()]
    def q(text_):                      # don't repeat the city the address already ends with
        return text_ + ("" if text_.lower().rstrip().endswith(city.lower()) else ", " + city) + ", Pakistan"
    out = []
    if address:
        out.append(("address", q(address)))
    if len(parts) >= 2:
        out.append(("street", q(", ".join(parts[:3]))))
        out.append(("area", q(", ".join(parts[-2:]))))
    return out


MAX_KM_FROM_CITY = 40          # a street/area hit farther than this is a namesake elsewhere
_centres = {}


def _km(a, b):
    p = math.pi / 180
    x = (math.sin((b[0] - a[0]) * p / 2) ** 2 +
         math.cos(a[0] * p) * math.cos(b[0] * p) * math.sin((b[1] - a[1]) * p / 2) ** 2)
    return 12742 * math.asin(math.sqrt(x))


def city_centre(city, sleep=1.1):
    """(lat, lng) of the city itself (cached), or None."""
    if city not in _centres:
        try:
            url = NOMINATIM + "?" + urllib.parse.urlencode(
                {"q": f"{city}, Pakistan", "format": "jsonv2", "limit": 1, "countrycodes": "pk"})
            hits = json.loads(collector._get(url, timeout=30, headers={"User-Agent": UA}))
            _centres[city] = (float(hits[0]["lat"]), float(hits[0]["lon"])) if hits else None
        except Exception:                                    # noqa: BLE001
            _centres[city] = None
        time.sleep(sleep)
    return _centres[city]


def _lookup(query):
    url = NOMINATIM + "?" + urllib.parse.urlencode(
        {"q": query, "format": "jsonv2", "limit": 1, "countrycodes": "pk"})
    hits = json.loads(collector._get(url, timeout=30, headers={"User-Agent": UA}))
    if not hits:
        return None
    h = hits[0]
    lat, lng = float(h["lat"]), float(h["lon"])
    if not (_PK[0] <= lat <= _PK[2] and _PK[1] <= lng <= _PK[3]):
        return None
    if h.get("addresstype") in ("city", "state", "country", "county", "state_district", "region"):
        return None                                   # only the city resolved -- not a branch
    return lat, lng


def geocode(address, city, sleep=1.1):
    """(lat, lng, precision) or None."""
    centre = city_centre(city, sleep) if city else None
    for precision, q in tiers(address, city):
        try:
            hit = _lookup(q)
        except Exception:                             # noqa: BLE001
            hit = None
        time.sleep(sleep)
        if hit and centre and _km(centre, hit) > MAX_KM_FROM_CITY:
            hit = None                                # same street name in another city
        if hit:
            return hit[0], hit[1], precision
    return None
