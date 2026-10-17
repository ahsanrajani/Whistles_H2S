"""Backfill real media (pictures/video) onto owned posts already collected
before media capture shipped. ``item`` is insert-only (``ON CONFLICT DO
NOTHING`` in ``db/pipeline.py``), so a normal re-collection can never add a
field to a row that already exists -- a post collected before this feature
landed stays media-less forever without an explicit update. This is a
deliberate, one-off exception to "insert-only", the same class of gap as
``core/owned_posts.py``'s ``_real_comment_counts()`` (the read-side
equivalent: recompute at read time instead of updating on disk).

Facebook/Instagram need a real, live Graph API call per post (their own
media isn't derivable from anything already on file). YouTube needs no call
at all -- the video id is already the item's own external_id, and its
thumbnail URL follows YouTube's public, predictable CDN pattern.

Human-triggered -- never scheduled.
"""
import json
import urllib.parse

from sqlalchemy import text

from core import collector

GRAPH = "https://graph.facebook.com/v20.0"
_YOUTUBE_SOURCE = "youtube_owned_videos"
_META_SOURCES = ("meta_facebook", "meta_instagram")


def _get(url):
    return json.loads(collector._get(url, timeout=30))


def _page_token(keys: dict) -> str:
    page_id, token = keys.get("META_PAGE_ID"), keys.get("META_ACCESS_TOKEN")
    if not (page_id and token):
        raise RuntimeError("META_PAGE_ID / META_ACCESS_TOKEN not configured")
    data = _get(f"{GRAPH}/me/accounts?access_token={urllib.parse.quote(token)}")
    for acct in data.get("data") or []:
        if str(acct.get("id")) == str(page_id) and acct.get("access_token"):
            return acct["access_token"]
    raise RuntimeError(f"no page-scoped token found for META_PAGE_ID={page_id}")


def _fb_media(post_id: str, page_token: str) -> dict | None:
    data = _get(f"{GRAPH}/{post_id}?fields=full_picture,attachments{{media_type}}"
               f"&access_token={urllib.parse.quote(page_token)}")
    if not data.get("full_picture"):
        return None
    attachment_type = next(
        (a.get("media_type") for a in (data.get("attachments") or {}).get("data") or []),
        None)
    return {"type": "video" if attachment_type == "video" else "photo",
           "image": data["full_picture"]}


def _ig_media(media_id: str, token: str) -> dict | None:
    data = _get(f"{GRAPH}/{media_id}?fields=media_type,media_url,thumbnail_url"
               f"&access_token={urllib.parse.quote(token)}")
    media_type = (data.get("media_type") or "").upper()
    if media_type == "VIDEO":
        return {"type": "video", "video": data.get("media_url"),
               "image": data.get("thumbnail_url")}
    if data.get("media_url"):
        return {"type": "photo", "image": data["media_url"]}
    return None


def _rows_missing_media(session, workspace_id: int, sources, limit: int):
    """Only actual posts, filtered in SQL -- a plain ORDER BY ... LIMIT
    ignoring `kind` let comment rows (which vastly outnumber posts) eat
    almost the whole limit, so most real posts were never even examined."""
    return session.execute(text("""
        SELECT id, source, external_id, raw_json FROM item
        WHERE workspace_id = :ws AND source = ANY(:sources)
          AND (raw_json::jsonb ->> 'kind') = 'post'
          AND NOT (raw_json::jsonb ? 'media')
        ORDER BY collected_at DESC LIMIT :lim
    """), {"ws": workspace_id, "sources": list(sources), "lim": limit}).mappings().all()


def backfill(session, workspace_id: int, keys: dict, *, limit: int = 300,
            log=None) -> dict:
    log = log or (lambda *_a: None)
    updated = 0

    yt_rows = _rows_missing_media(session, workspace_id, [_YOUTUBE_SOURCE], limit)
    for r in yt_rows:
        vid = r["external_id"].split(":", 1)[1]
        raw = json.loads(r["raw_json"] or "{}")
        raw["media"] = {"type": "youtube", "video_id": vid,
                        "image": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"}
        session.execute(text("UPDATE item SET raw_json = :raw WHERE id = :id"),
                        {"raw": json.dumps(raw), "id": r["id"]})
        updated += 1
    if yt_rows:
        log(f"youtube · {len(yt_rows)} backfilled (no API call needed)")

    meta_rows = _rows_missing_media(session, workspace_id, _META_SOURCES, limit)
    page_token = None
    meta_updated = 0
    for r in meta_rows:
        raw = json.loads(r["raw_json"] or "{}")
        real_id = r["external_id"].split(":", 1)[1]
        try:
            if r["source"] == "meta_facebook":
                if page_token is None:
                    page_token = _page_token(keys)
                media = _fb_media(real_id, page_token)
            else:
                media = _ig_media(real_id, keys.get("META_ACCESS_TOKEN") or "")
        except Exception as e:                                        # noqa: BLE001
            log(f"{r['external_id']} · failed ({e})")
            continue
        if media:
            raw["media"] = media
            session.execute(text("UPDATE item SET raw_json = :raw WHERE id = :id"),
                            {"raw": json.dumps(raw), "id": r["id"]})
            meta_updated += 1
    updated += meta_updated
    log(f"facebook/instagram · {len(meta_rows)} missing media, {meta_updated} updated")

    checked = len(yt_rows) + len(meta_rows)
    return {"checked": checked, "updated": updated}
