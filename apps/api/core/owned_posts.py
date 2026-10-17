"""Recent owned posts across Meta, LinkedIn, YouTube and X -- one unified,
newest-first feed of the brand's own published content (never mentions),
each with its real permalink and, where the platform actually exposes it,
the real engagement counts the adapter captured at collection time
(item.raw_json.metrics). A platform that doesn't return a metric shows
none -- nothing here is invented.
"""
import json

from sqlalchemy import text as _sql

# item.source -> (platform key, display label). Bright Data's owned-channel
# sources are config-only/dormant until Hamza sets a dataset id -- they
# appear here so this feed picks them up the moment they go live, with no
# code change needed.
PLATFORM_FOR_SOURCE = {
    "meta_facebook": ("facebook", "Facebook"),
    "brightdata_facebook_posts": ("facebook", "Facebook"),
    "meta_instagram": ("instagram", "Instagram"),
    "brightdata_instagram_posts": ("instagram", "Instagram"),
    "brightdata_linkedin_posts": ("linkedin", "LinkedIn"),
    "youtube_owned_videos": ("youtube", "YouTube"),
    "x_owned_posts": ("x", "X"),
}


def _real_comment_counts(session, workspace_id, sources) -> dict[tuple[str, str], int]:
    """{(source, post_external_id): real comment+reply count}, computed
    fresh from the comment/reply items actually collected -- item rows are
    insert-only (ON CONFLICT DO NOTHING), so a post's own metrics.comments
    field (captured once, at first fetch) never updates as more real
    comments get collected later and can go stale at 0. This counts what
    is genuinely on file right now instead."""
    rows = session.execute(_sql("""
        SELECT source, external_id, raw_json FROM item
        WHERE workspace_id = :ws AND source = ANY(:sources)
    """), {"ws": workspace_id, "sources": sources}).mappings().all()

    by_source: dict[str, dict[str, str | None]] = {}
    for r in rows:
        try:
            raw = json.loads(r["raw_json"] or "{}")
        except ValueError:
            raw = {}
        if raw.get("kind") not in ("comment", "reply"):
            continue
        by_source.setdefault(r["source"], {})[r["external_id"]] = raw.get("parent_id")

    counts: dict[tuple[str, str], int] = {}
    for source, parent_by_id in by_source.items():
        for parent_id in parent_by_id.values():
            seen, cur = set(), parent_id
            while cur and cur not in seen:
                seen.add(cur)
                nxt = parent_by_id.get(cur)
                if nxt is None:      # cur isn't itself a comment/reply -> it's the post
                    key = (source, cur)
                    counts[key] = counts.get(key, 0) + 1
                    break
                cur = nxt
    return counts


def recent(session, workspace_id, *, platform=None, limit=50) -> list[dict]:
    sources = [src for src, (key, _label) in PLATFORM_FOR_SOURCE.items()
              if platform is None or key == platform]
    if not sources:
        return []
    # over-fetch: the exact "kind == post" check (a post, never a comment on
    # one) happens in Python below, same pattern as core/care_bridge.py. The
    # LIKE only narrows the rows first: without it a busy comment section
    # (newer than the posts) fills the whole fetch window and hides every post.
    rows = session.execute(_sql("""
        SELECT source, external_id, url, author, published_at, title, body, raw_json
        FROM item
        WHERE workspace_id = :ws AND source = ANY(:sources)
          AND raw_json LIKE '%"post"%'
        ORDER BY published_at DESC NULLS LAST
        LIMIT :fetch_limit
    """), {"ws": workspace_id, "sources": sources,
           "fetch_limit": max(limit * 4, 50)}).mappings().all()

    comment_counts = _real_comment_counts(session, workspace_id, sources)
    out = []
    for r in rows:
        try:
            raw = json.loads(r["raw_json"] or "{}")
        except ValueError:
            raw = {}
        if raw.get("kind") != "post":
            continue
        key, label = PLATFORM_FOR_SOURCE[r["source"]]
        metrics = dict(raw.get("metrics") or {})
        real_comments = comment_counts.get((r["source"], r["external_id"]))
        if real_comments is not None:
            metrics["comments"] = real_comments
        out.append({
            "platform": key, "platform_label": label, "source": r["source"],
            "external_id": r["external_id"], "url": r["url"], "author": r["author"],
            "published_at": r["published_at"], "title": r["title"], "body": r["body"],
            "metrics": metrics or None, "media": raw.get("media"),
        })
        if len(out) >= limit:
            break
    return out


def comments_for(session, workspace_id: int, *, source: str, post_external_id: str,
                 limit=500) -> list[dict]:
    """Real comments + replies collected under one post, oldest first, each
    carrying its real `parent_id` (set by the Meta adapters) so the caller
    can nest replies under their comment. `source` bounds this to one
    platform's items (a post's own collection source) -- comments aren't
    looked up across platforms."""
    rows = session.execute(_sql("""
        SELECT external_id, url, author, published_at, body, raw_json
        FROM item WHERE workspace_id = :ws AND source = :source
        ORDER BY published_at ASC NULLS LAST LIMIT :limit
    """), {"ws": workspace_id, "source": source, "limit": limit}).mappings().all()

    parsed = []
    for r in rows:
        try:
            raw = json.loads(r["raw_json"] or "{}")
        except ValueError:
            raw = {}
        if raw.get("kind") not in ("comment", "reply"):
            continue
        parsed.append({
            "external_id": r["external_id"], "url": r["url"], "author": r["author"],
            "published_at": r["published_at"], "body": r["body"],
            "kind": raw.get("kind"), "parent_id": raw.get("parent_id"),
        })
    by_id = {p["external_id"]: p for p in parsed}

    def under_post(p) -> bool:
        seen, cur = set(), p
        while cur and cur.get("parent_id") and cur["parent_id"] not in seen:
            if cur["parent_id"] == post_external_id:
                return True
            seen.add(cur["parent_id"])
            cur = by_id.get(cur["parent_id"])
        return False

    return [p for p in parsed if under_post(p)]
