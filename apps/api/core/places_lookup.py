"""Locate a branch through Google Places Text Search (needs GOOGLE_PLACES_API_KEY).

Only a listing whose *name* says Jubilee and that sits within
``geocode.MAX_KM_FROM_CITY`` of the city is accepted -- a namesake elsewhere, or
another company on the same street, is rejected and the caller keeps what it had.
The hit carries its Google ``place_id`` (also what the reviews collector needs).
"""
import json
import urllib.error

from . import collector, geocode

TEXT_SEARCH = "https://places.googleapis.com/v1/places:searchText"   # Places API (New)
PRECISION = "place"                # a Google business listing, not a geometric guess


def queries(name, city, brand="Jubilee Life Insurance"):
    base = name.split("(")[0].strip(" ,")
    if city and city.lower() not in base.lower():
        base = f"{base} {city}"
    return [f"{brand} {base}", f"{brand} {city}" if city else brand]


def _accept(places, city, centre):
    for r in places:
        loc = r.get("location") or {}
        name = (r.get("displayName") or {}).get("text") or ""
        if "jubilee" not in name.lower() or "latitude" not in loc:
            continue
        pt = (loc["latitude"], loc["longitude"])
        if centre and geocode._km(centre, pt) > geocode.MAX_KM_FROM_CITY:
            continue
        return pt[0], pt[1], r.get("id")
    return None


def locate(name, city, key, brand="Jubilee Life Insurance"):
    """(lat, lng, place_id, PRECISION) or None."""
    centre = geocode.city_centre(city) if city else None
    for q in queries(name, city, brand):
        body = json.dumps({"textQuery": q + ", Pakistan", "regionCode": "PK"}).encode()
        try:
            payload = json.loads(collector._get(TEXT_SEARCH, timeout=30, data=body, headers={
                "Content-Type": "application/json", "X-Goog-Api-Key": key,
                "X-Goog-FieldMask": "places.id,places.displayName,places.location"}))
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"places: HTTP {e.code} {e.read()[:200]!r}") from e
        hit = _accept(payload.get("places") or [], city, centre)
        if hit:
            return (*hit, PRECISION)
    return None
