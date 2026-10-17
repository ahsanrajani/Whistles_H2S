"""A workspace's branch network, geocoded — the /branches map layer.

A workspace with rows in the ``location`` table (per-tenant catalogue, e.g.
Jubilee Life) is plotted from those -- only rows that have coordinates, each
tagged with how precise they are. A workspace with none falls back to Bank
Alfalah's published list below (the original PoC catalogue).

Bank Alfalah's list: reads ``data/branches.csv`` (Bank Alfalah's own published branch list — real
names, cities, addresses and coordinates for ~1,186 branches) once and caches
it in memory. This is deliberately *not* imported into the database as a
table: the branch-performance analysis stays keyed on
``core/branches.py``'s deterministic alias resolver, unrelated to this file.
``catalog()`` is read-only reference geodata for the map; ``with_performance``
merges it with ``branch_perf.scan()`` in memory, by branch code, so the
handful of branches we actually have review/social signal for carry their
score/band and the rest render as plain, unscored map points.

A CSV row is malformed and dropped if it lacks a parseable lat/lng or a
branch code (two of the 1,411 source rows have a stray quote in the address
that shifts their columns — not worth a bespoke parser for two rows).
"""
import csv
from pathlib import Path

_CSV = Path(__file__).resolve().parent.parent / "data" / "branches.csv"
_cache = None


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def catalog():
    """Real Bank Alfalah branches (not standalone ATMs) with valid coordinates."""
    global _cache
    if _cache is not None:
        return _cache
    rows = []
    if _CSV.exists():
        with open(_CSV, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                if row.get("isBranch") != "Branch":
                    continue
                lat, lng = _num(row.get("Latitude")), _num(row.get("Longitude"))
                code = (row.get("Branch Code") or "").strip()
                name = (row.get("Branch Name") or "").strip()
                if lat is None or lng is None or not code or not name:
                    continue
                rows.append({
                    "code": code, "name": name,
                    "city": (row.get("City") or "").strip(),
                    "address": (row.get("Address") or "").strip(),
                    "lat": lat, "lng": lng,
                    "has_atm": row.get("isATM") == "ATM",
                })
    _cache = rows
    return rows


def _location_rows(db, ws):
    """``location`` rows with coordinates, in the shape ``catalog()`` returns."""
    session = getattr(db, "session", None)
    if session is None:
        return []
    from db.repositories import locations
    return [{
        "code": r["key"], "name": r["name"], "city": r["city"] or "",
        "address": r["address"] or "", "lat": r["lat"], "lng": r["lng"],
        "has_atm": r["kind"] == "atm", "kind": r["kind"],
        "precision": r["geo_precision"],
        "google_rating": r["rating"], "google_reviews": r["review_count"],
    } for r in locations.list_all(session, ws) if r["lat"] is not None and r["lng"] is not None]


def catalog_for(db, ws):
    """The workspace's own located branches, else the Bank Alfalah PoC list."""
    return _location_rows(db, ws) or catalog()


def with_performance(db, ws):
    """``catalog()`` rows merged with the branch_perf rollup, by branch code.

    Branches outside the analysis PoC's ~20-branch alias table (see
    core/branches.py) come back with ``key: None`` and ``band: "none"`` — the
    map still plots them, just without a score.
    """
    from . import branch_perf
    perf_by_code = {b["code"]: b for b in branch_perf.scan(db, ws)["branches"]}
    out = []
    for row in catalog_for(db, ws):
        perf = perf_by_code.get(row["code"])
        out.append({
            **row,
            "key": perf["key"] if perf else None,
            "band": perf["band"] if perf else "none",
            "score": perf["score"] if perf else 0,
            "mean_rating": perf["mean_rating"] if perf else None,
            "reviews": perf["reviews"] if perf else 0,
            "complaints": perf["complaints"] if perf else 0,
            "critical": perf["critical"] if perf else 0,
            "top_issue": perf["top_issue"] if perf else None,
            "last_flag_at": perf["last_flag_at"] if perf else None,
        })
    return out
