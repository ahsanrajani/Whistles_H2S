"""Backfill ``parent_id`` onto Facebook/Instagram comment/reply item rows
collected before nested-reply parent tracking existed (added earlier this
session). ``item`` is insert-only, so those rows can never pick a missing
field up from a normal re-collection -- ``core/owned_posts.py``'s
``comments_for()`` chain-walk can never find a comment with no parent_id at
all, no matter how many times the source is re-collected. Found live: a real
post's own comments_count was accurate but its comment rows, already on
file, had no parent_id -- "most comments/comment replies not showing".

Re-runs the real adapter fetch() (same pagination, same Graph calls a normal
collection already makes) and patches any existing row missing parent_id
using what that fresh fetch now knows. Human-triggered -- never scheduled.
"""
import json

from sqlalchemy import text

from integrations.adapters import MetaFacebook, MetaInstagram

_ADAPTERS = {"meta_facebook": MetaFacebook, "meta_instagram": MetaInstagram}


def backfill(session, workspace_id: int, keys: dict, *, log=None) -> dict:
    log = log or (lambda *_a: None)
    checked = updated = 0

    for source, adapter_cls in _ADAPTERS.items():
        adapter = adapter_cls(keys, log, lambda *_a, **_k: None)
        try:
            rows = list(adapter.fetch([]))
        except Exception as e:                                        # noqa: BLE001
            log(f"{source} · fetch failed ({e})")
            continue

        for row in rows:
            if row["raw"].get("kind") not in ("comment", "reply"):
                continue
            parent_id = row["raw"].get("parent_id")
            if not parent_id:
                continue
            checked += 1
            existing = session.execute(text("""
                SELECT id, raw_json FROM item
                WHERE workspace_id = :ws AND source = :src AND external_id = :ext
            """), {"ws": workspace_id, "src": source, "ext": row["external_id"]}).mappings().first()
            if not existing:
                continue   # not on file at all -- a normal collection run handles that
            raw = json.loads(existing["raw_json"] or "{}")
            if raw.get("parent_id"):
                continue   # already has one -- nothing to fix
            raw["parent_id"] = parent_id
            session.execute(text("UPDATE item SET raw_json = :raw WHERE id = :id"),
                            {"raw": json.dumps(raw), "id": existing["id"]})
            updated += 1
        log(f"{source} · {len(rows)} comments/replies seen this pass")

    return {"checked": checked, "updated": updated}
