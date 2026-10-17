"""Import verified Google listing enrichment onto existing ``location`` rows.

The input is the key-based branch audit CSV.  It is not a review-level export:
each accepted row may supply a Place ID, the listing's overall rating/count,
and coordinates.  Existing catalogue coordinates are preserved; Google
coordinates only fill a missing pin.  Blank ratings never erase known data.
"""
from datetime import datetime

from sqlalchemy import text


ACCEPTED_STATUSES = {
    "verified_exact_address",
    "verified_by_branch_name",
    "probable_exact_location",
}


def _number(value, cast):
    try:
        return cast(value)
    except (TypeError, ValueError):
        return None


def _checked_at(value):
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def import_rows(session, workspace_id, rows, *, apply=False):
    """Validate and optionally apply enrichment rows. Returns import stats."""
    known = {
        row[0]: {"lat": row[1], "lng": row[2]}
        for row in session.execute(text(
            "SELECT key, lat, lng FROM location WHERE workspace_id=:ws"),
            {"ws": workspace_id}).all()
    }
    stats = {
        "accepted": 0,
        "rated": 0,
        "pins_filled": 0,
        "skipped_unverified": 0,
        "unknown_keys": [],
    }
    for row in rows:
        status = (row.get("google_match_status") or "").strip()
        place_id = (row.get("google_place_id") or "").strip()
        if not place_id or status not in ACCEPTED_STATUSES:
            stats["skipped_unverified"] += 1
            continue
        key = (row.get("key") or "").strip()
        current = known.get(key)
        if current is None:
            stats["unknown_keys"].append(key)
            continue

        lat = _number(row.get("google_latitude"), float)
        lng = _number(row.get("google_longitude"), float)
        fill_pin = (current["lat"] is None or current["lng"] is None) and \
            lat is not None and lng is not None
        rating = _number(row.get("google_rating"), float)
        count = _number(row.get("google_review_count"), int)
        has_rating = rating is not None and count is not None

        stats["accepted"] += 1
        stats["pins_filled"] += int(fill_pin)
        stats["rated"] += int(has_rating)
        if not apply:
            continue

        session.execute(text("""
            UPDATE location SET
              place_id = :pid,
              lat = CASE WHEN lat IS NULL AND :fill_pin THEN :lat ELSE lat END,
              lng = CASE WHEN lng IS NULL AND :fill_pin THEN :lng ELSE lng END,
              geo_precision = CASE
                WHEN (lat IS NULL OR lng IS NULL) AND :fill_pin THEN 'place'
                ELSE geo_precision END,
              rating = CASE WHEN :has_rating THEN :rating ELSE rating END,
              review_count = CASE WHEN :has_rating THEN :review_count ELSE review_count END,
              rating_source = CASE WHEN :has_rating THEN 'google_maps_export' ELSE rating_source END,
              rating_at = CASE WHEN :has_rating THEN COALESCE(:checked_at, now()) ELSE rating_at END
            WHERE workspace_id = :ws AND key = :key
        """), {
            "pid": place_id,
            "fill_pin": fill_pin,
            "lat": lat,
            "lng": lng,
            "has_rating": has_rating,
            "rating": rating,
            "review_count": count,
            "checked_at": _checked_at(row.get("google_checked_at")),
            "ws": workspace_id,
            "key": key,
        })
    return stats
