"""Per-workspace branch / office / ATM catalogue (``location``)."""
import re

from sqlalchemy import text

_COLS = ("key", "kind", "name", "city", "region", "address", "lat", "lng", "place_id", "geo_precision", "source")


def slugify(*parts):
    return re.sub(r"[^a-z0-9]+", "-", " ".join(p for p in parts if p).lower()).strip("-")


def upsert_many(session, workspace_id, rows):
    """Insert or update by (workspace, key). A NULL in ``rows`` never erases a
    known value (so a re-run of a coordinate-less importer keeps geocoded lat/lng).
    Returns the number of rows written."""
    for r in rows:
        params = {c: r.get(c) for c in _COLS}
        params["kind"] = params["kind"] or "branch"
        params["source"] = params["source"] or "manual"
        session.execute(text("""
            INSERT INTO location (workspace_id, key, kind, name, city, region, address,
                                  lat, lng, place_id, geo_precision, source)
            VALUES (:ws, :key, :kind, :name, :city, :region, :address,
                    :lat, :lng, :place_id, :geo_precision, :source)
            ON CONFLICT (workspace_id, key) DO UPDATE SET
              kind = EXCLUDED.kind, name = EXCLUDED.name,
              city = COALESCE(EXCLUDED.city, location.city),
              region = COALESCE(EXCLUDED.region, location.region),
              address = COALESCE(EXCLUDED.address, location.address),
              lat = COALESCE(EXCLUDED.lat, location.lat),
              lng = COALESCE(EXCLUDED.lng, location.lng),
              geo_precision = CASE WHEN EXCLUDED.lat IS NOT NULL THEN EXCLUDED.geo_precision
                                   ELSE location.geo_precision END,
              place_id = COALESCE(EXCLUDED.place_id, location.place_id)"""),
            {"ws": workspace_id, **params})
    return len(rows)


def list_all(session, workspace_id, kind=None):
    q = ("SELECT id, key, kind, name, city, region, address, lat, lng, place_id, geo_precision, "
         "rating, review_count, rating_source, rating_at, source "
         "FROM location WHERE workspace_id = :ws")
    args = {"ws": workspace_id}
    if kind:
        q += " AND kind = :kind"
        args["kind"] = kind
    rows = session.execute(text(q + " ORDER BY city, name"), args).mappings().all()
    return [dict(r) for r in rows]


def set_geo(session, workspace_id, key, lat, lng, precision):
    session.execute(text(
        "UPDATE location SET lat = :lat, lng = :lng, geo_precision = :p "
        "WHERE workspace_id = :ws AND key = :key"),
        {"ws": workspace_id, "key": key, "lat": lat, "lng": lng, "p": precision})


def set_rating(session, workspace_id, key, rating, review_count, source, place_id=None):
    """Record a listing's overall rating / review count (either may be None)."""
    session.execute(text(
        "UPDATE location SET rating = :r, review_count = :n, rating_source = :src, "
        "rating_at = now(), place_id = COALESCE(:pid, place_id) "
        "WHERE workspace_id = :ws AND key = :key"),
        {"ws": workspace_id, "key": key, "r": rating, "n": review_count,
         "src": source, "pid": place_id})
