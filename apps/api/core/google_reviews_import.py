"""Import a Google Maps reviews export (one row per review, each carrying its
listing's ``place_id`` / overall ``branch_rating`` / ``branch_review_count``)
into a workspace.

Per listing: the overall rating + count go on the mapped ``location`` row (what
the map popup shows -- the public listing's own figures, never recomputed from
the sample). Per review that has text: an ``item`` on the ``branch_review``
surface with ``raw_json.branch_key`` = the location, so ``branch_perf`` scores
it without going through the alias resolver. Rating-only rows carry no text
and are counted, not stored. Listings in ``exclude`` keep their rating but
their reviews are not imported (e.g. a promotional SEO listing whose owner
replies are boilerplate).

Every review URL gets the ``#review_id`` fragment: ``collection/dedupe.py``
folds items with an identical url, and all reviews of a listing share one
``maps_link``.
"""
import csv
import hashlib
import json
from datetime import datetime, timezone

from . import entity
from .collector import norm
from db.repositories import locations as loc_repo

SURFACE = "branch_review"
SOURCE = "google_maps_reviews"
RULE = "google_maps_review"


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _num(v, cast):
    try:
        return cast(v)
    except (TypeError, ValueError):
        return None


def listings(rows):
    """place_id -> {name, address, rating, count, link, n_rows}, first row wins."""
    out = {}
    for r in rows:
        pid = (r.get("place_id") or "").strip()
        if not pid:
            continue
        d = out.setdefault(pid, {
            "place_id": pid, "name": (r.get("branch_name") or "").strip(),
            "address": (r.get("branch_address") or "").strip(),
            "rating": _num(r.get("branch_rating"), float),
            "count": _num(r.get("branch_review_count"), int),
            "link": r.get("maps_link"), "n_rows": 0})
        d["n_rows"] += 1
    return out


def _published(r):
    d = (r.get("approx_review_date") or "").strip()
    try:
        return datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        return None


def import_reviews(session, workspace_id, brand_id, rows, place_to_key, exclude=()):
    """Write ratings + reviews. ``place_to_key`` maps place_id -> location key.
    Returns a summary dict."""
    from db import pipeline
    now_iso = datetime.now(timezone.utc).isoformat()
    stats = {"rated": 0, "reviews": 0, "duplicate": 0, "rating_only": 0,
             "excluded": 0, "unmapped": 0}

    for pid, l in listings(rows).items():
        key = place_to_key.get(pid)
        if key is None:
            continue
        loc_repo.set_rating(session, workspace_id, key, l["rating"], l["count"],
                            "google_maps", place_id=pid)
        stats["rated"] += 1

    for r in rows:
        pid = (r.get("place_id") or "").strip()
        key = place_to_key.get(pid)
        if key is None:
            stats["unmapped"] += 1
            continue
        if pid in exclude:
            stats["excluded"] += 1
            continue
        body = (r.get("review_text") or "").strip()
        if not body:
            stats["rating_only"] += 1
            continue
        rid = r.get("review_id") or ""
        rating = _num(r.get("star_rating"), int)
        ext = f"gmaps-{rid}"
        url = f"{r.get('maps_link') or ''}#{rid}" if r.get("maps_link") else None
        raw = {"branch_key": key, "place_id": pid, "kind": "review",
               "local_guide": (r.get("local_guide") or "").lower() == "yes",
               "review_likes": _num(r.get("review_likes"), int)}
        reply = (r.get("owner_reply") or "").strip()
        if reply:
            raw["owner_response"] = reply
            raw["owner_response_at"] = (r.get("owner_reply_date") or None)
        chash = hashlib.sha256(norm(f"{rid}|{body}").encode()).hexdigest()[:32]
        ok = pipeline.insert_item(session, (
            workspace_id, SURFACE, SOURCE, "licensed", ext, url,
            "Google Maps", (r.get("reviewer_name") or None), _published(r), None, body,
            entity.guess_lang(body), rating, 0,
            None, json.dumps(raw), now_iso, chash, 0, None, "third_party"))
        if not ok:
            stats["duplicate"] += 1
            continue
        iid = pipeline.item_id_by_external(session, workspace_id, SOURCE, ext)
        pipeline.insert_mention(session, workspace_id, iid, brand_id, RULE, 0, 0, None)
        stats["reviews"] += 1
    return stats
