"""Bridge already-collected, real mentions into Care cases.

Care's own ingestion path (`POST /care/cases/ingest`) is webhook-driven --
nothing in the collection pipeline calls it, so a real comment or review
that the listening surfaces already show never shows up in an agent's
queue on its own. This turns every genuinely customer-authored, reply-able
mention (on a platform Care can actually reply to) into a real Care case
with a working `platform_ref` so the reply button targets the right
comment/review/message -- regardless of its classified category or
sentiment; an agent triages by reading the queue, not by pre-filtering it.
Idempotent -- a mention already bridged (matched by `platform_ref`) is
skipped on the next run.

Only genuinely customer-authored, reply-able items are bridged. A YouTube
*video* or a brand's own Facebook/Instagram *post* is not something a
customer said and there is nothing to reply to -- `_is_customer_authored`
excludes those even if the classifier tagged them negative/complaint (video
titles about a market crash routinely read as negative sentiment without
being a complaint about the brand at all).
"""
import json

from sqlalchemy import text as _sql

from . import cases

# item.source -> the Care channel (== ChannelBadge's Channel union in
# primitives.tsx, so the right logo renders and "All channels" filtering
# actually works -- facebook/instagram stay distinct here even though
# integrations/write/platforms.py's _ALIASES resolves both back to the one
# "meta" write client when a reply actually sends).
PLATFORM_FOR_SOURCE = {
    "youtube_v3": "youtube",
    "youtube_owned_videos": "youtube",
    "meta_facebook": "facebook",
    "meta_instagram": "instagram",
    "google_places_reviews": "google_reviews",
}

# Sources whose items carry a raw.kind ("post"/"comment"/"reply") set by the
# adapter itself -- only "comment" (top-level, from a customer) is bridged.
# "reply" is excluded everywhere: on every one of these platforms a reply
# can just as easily be *our own* past reply to a comment (author == the
# Page/channel itself) as a customer's follow-up, and there is no cheap way
# here to tell those apart -- bridging our own reply back in as a new
# "complaint" would be a real, visible mistake. Once that distinction is
# worth making, filter on the reply's author against the Page/channel name.
_KIND_TAGGED_SOURCES = ("meta_facebook", "meta_instagram", "youtube_owned_videos")


def _is_customer_authored(source, external_id, raw_json) -> bool:
    if source == "youtube_v3":
        return bool(external_id) and external_id.startswith("comment:")
    if source in _KIND_TAGGED_SOURCES:
        try:
            kind = json.loads(raw_json or "{}").get("kind")
        except ValueError:
            kind = None
        return kind == "comment"
    if source == "google_places_reviews":
        return True   # every item from this source is a review
    return False


def candidates(session, workspace_id, *, since=None, limit=50):
    """Real, customer-authored mentions on a platform Care can reply to,
    not already bridged into a case. Every one qualifies -- no category or
    sentiment gate -- an agent triages by reading the queue."""
    sources = list(PLATFORM_FOR_SOURCE)
    rows = session.execute(_sql("""
        SELECT i.id AS item_id, i.source, i.external_id, i.url, i.author, i.body,
               i.published_at, i.raw_json
        FROM mention m
        JOIN item i ON i.id = m.item_id AND i.workspace_id = m.workspace_id
        WHERE m.workspace_id = :ws AND m.excluded = 0 AND m.hidden = 0
          AND i.source = ANY(:sources)
          AND i.published_at >= :since
          AND i.external_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM case_message cm
              WHERE cm.workspace_id = :ws AND cm.platform_ref = i.external_id)
        ORDER BY i.published_at DESC
        LIMIT :limit
    """), {"ws": workspace_id, "sources": sources, "since": since or "1900-01-01",
           "limit": limit}).mappings().all()
    return [r for r in rows
            if _is_customer_authored(r["source"], r["external_id"], r["raw_json"])]


def backfill(session, workspace_id, *, since=None, limit=50, actor=None) -> dict:
    """Ingest each candidate as an inbound Care message. Returns counts, not
    the created case ids -- callers that need those should read the queue."""
    rows = candidates(session, workspace_id, since=since, limit=limit)
    created = 0
    for row in rows:
        platform = PLATFORM_FOR_SOURCE.get(row["source"])
        if not platform:
            continue
        cases.ingest_message(
            session, workspace_id, platform=platform,
            handle=row["author"] or f"{platform}-unknown",
            display_name=row["author"], body=row["body"] or "",
            platform_ref=row["external_id"], permalink=row["url"],
            sent_at=row["published_at"], actor=actor)
        created += 1
    return {"scanned": len(rows), "created": created}
