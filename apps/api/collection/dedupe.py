"""Fold re-collected items into `dupe_edge` so downstream reads see one row per
story. Called by `collector.run_collection`; re-exported as `collector.dedupe`.

Identity is `(workspace_id, source, external_id)` — enforced at INSERT, so a
re-collection of the same record never even reaches here. What this pass folds
is the *same story arriving twice*: byte-identical text (`content_hash`), a
feed re-collected under a rotated id (`norm_title`), or a near-verbatim
re-report from a different source (`simhash`, P2.1).

It no longer folds on URL. Two items that merely share a URL — a base article
URL with distinct `#fragment`s, a shortener that resolves to one page — are
kept apart; folding them was the P2.1 bug.
"""
from collection import simhash as sh
from db import pipeline as p


def dedupe(db, ws, log):
    s = db.session
    n = 0
    for key, canon in p.dupe_groups_by_column(s, ws, "content_hash"):
        n += p.fold_column_dupes(s, ws, "content_hash", key, canon, "content_hash")
    for outlet, key, canon in p.title_dupe_groups(s, ws):
        n += p.fold_title_dupes(s, ws, canon, key, outlet)
    n += _fold_near_duplicates(s, ws)
    db.commit()
    log(f"dedupe · {n} duplicates folded")


def _fold_near_duplicates(session, ws):
    """SimHash LSH: bucket every unfolded item by hash band; fold one onto an
    earlier item within Hamming distance ``NEAR_DUP_MAX_DISTANCE``. ``simhash_rows``
    yields ``official`` items first, then id-ascending, so a Graph item wins over
    a third-party scrape of the same post (P2.5); otherwise the earliest wins."""
    buckets: dict[tuple[int, int], list[int]] = {}
    hash_of: dict[int, int] = {}
    folded = 0
    for item_id, h in p.simhash_rows(session, ws):
        match = None
        for band_idx, band_val in enumerate(sh.bands(h)):
            for cand_id in buckets.get((band_idx, band_val), ()):
                if sh.hamming(h, hash_of[cand_id]) <= sh.NEAR_DUP_MAX_DISTANCE:
                    match = cand_id
                    break
            if match is not None:
                break
        if match is not None:
            folded += p.fold_simhash_dupes(session, ws, item_id, match)
            continue
        hash_of[item_id] = h
        for band_idx, band_val in enumerate(sh.bands(h)):
            buckets.setdefault((band_idx, band_val), []).append(item_id)
    return folded
