"""Import hand-collected public mentions / complaints (a JSON list of
``{post_text, source, name, username, date, link}``) as ordinary items with an
explicit mention of the focus brand.

Each item lands on the surface its ``source`` belongs to (facebook, linkedin,
web, ...) so it appears in the same views as collected data. Sentiment and
category are left unset -- ``sentiment.score_pending`` / ``classify.classify_pending``
fill them, as for any collected mention. Undated rows keep ``published_at`` NULL
(never a guessed date). Branch attribution is not forced: these texts name
partner-bank branches, not the client's own, and are left unattributed unless
``branch_resolver`` finds one.

Comments on one post share that post's url, so every url gets a per-item
``#fragment`` -- ``collection/dedupe.py`` folds items with an identical url.
"""
import hashlib
import json
from datetime import datetime, timezone

from . import entity
from .collector import norm

SOURCE = "manual_mentions"
RULE = "manual_import"

# source label -> (surface, outlet)
SURFACE_BY_SOURCE = (
    ("facebook", "facebook", "Facebook"),
    ("trustpilot", "web", "Trustpilot"),
    ("linkedin", "linkedin", "LinkedIn"),
    ("reddit", "reddit", "Reddit"),
    ("psxupdates", "news", "PSXUpdates"),
    ("president of pakistan", "regulatory", "President of Pakistan"),
    ("ombudsman", "regulatory", "Federal Ombudsman of Pakistan"),
    ("case law", "regulatory", "Pakistan Case Law"),
)


def surface_for(source):
    s = (source or "").lower()
    for needle, surface, outlet in SURFACE_BY_SOURCE:
        if needle in s:
            return surface, outlet
    return "web", source or None


def import_mentions(session, workspace_id, brand_id, records, skip_links=()):
    from db import pipeline
    now_iso = datetime.now(timezone.utc).isoformat()
    out = {"inserted": 0, "duplicate": 0, "skipped": 0}
    for r in records:
        body = (r.get("post_text") or "").strip()
        link = (r.get("link") or "").strip()
        if not body or link in skip_links:
            out["skipped"] += 1
            continue
        surface, outlet = surface_for(r.get("source"))
        h = hashlib.sha256(norm(f"{link}|{r.get('name')}|{body}").encode()).hexdigest()
        ext = f"manual-{h[:24]}"
        url = f"{link}#m-{h[:8]}" if link else None
        d = (r.get("date") or "").strip()
        pub = f"{d}T00:00:00+00:00" if d else None
        raw = {"source_label": r.get("source"), "handle": r.get("username"),
               "kind": "comment" if "comment" in (r.get("source") or "").lower() else "post",
               "truncated": body.endswith("…")}
        ok = pipeline.insert_item(session, (
            workspace_id, surface, SOURCE, "public", ext, url, outlet,
            r.get("name") or None, pub, None, body, entity.guess_lang(body), None, 0,
            None, json.dumps(raw), now_iso, h[:32], 0, None, "third_party"))
        if not ok:
            out["duplicate"] += 1
            continue
        iid = pipeline.item_id_by_external(session, workspace_id, SOURCE, ext)
        pipeline.insert_mention(session, workspace_id, iid, brand_id, RULE, 0, 0, None)
        out["inserted"] += 1
    return out
