"""The client-safe story feed and the fully-filtered evidence table.

The SQL lives in ``db/analytics/evidence.py``; this module keeps the
title-dedupe pass over the feed.
"""
import re

from db.analytics import evidence as q


def _title_key(text):
    """A loose fingerprint for near-duplicate headlines (same title re-posted
    across channels / re-uploads that `dupe_edge` did not catch)."""
    slug = re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()
    return slug[:70]


def feed(db, ws, limit=25, brand_id=None, only_review=False, surface=None):
    seen, out = set(), []
    for row in q.feed_rows(db.session, ws, limit, brand_id, only_review, surface):
        key = _title_key(row[6])
        if key and key in seen:
            continue
        seen.add(key)
        out.append(row)
        if len(out) >= limit:
            break
    return out


def evidence(db, ws, limit=100, brand_id=None, outlet="", surface="", rule="",
             sentiment="", since=None, q="", category="", rating="", sort="new",
             include_hidden=False):
    """Client-safe stories with sentiment, type and enough provenance to trace a
    claim. Collapsed to one row per item — a story that names several brands
    shows once (focus brand, or the filtered brand, as the representative), with
    the rest listed as `other_brands`.

    `since` is a day count; `sentiment` is pos|neu|neg; `category` is a
    mention-type key; `q` is a free-text match; `rating` is high|mid|low;
    `sort` is a key of `_EVIDENCE_SORTS`. `include_hidden` keeps admin-hidden
    mentions in the set (with the `hidden` flag set on the row)."""
    from db.analytics.evidence import evidence_query
    return evidence_query(
        db.session, ws, limit=limit, brand_id=brand_id, outlet=outlet, surface=surface,
        rule=rule, sentiment=sentiment, since=since, q=q, category=category,
        rating=rating, sort=sort, include_hidden=include_hidden)
