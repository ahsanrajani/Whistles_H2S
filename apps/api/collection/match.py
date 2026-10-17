"""Central brand matching over freshly collected items. Called by
`collector.run_collection`; re-exported as `collector.match`."""
from core import entity
from db import pipeline as p


def match(db, ws, brands, log):
    # `regulatory` items are a context feed, not brand mentions, by design
    # (see core/regulatory.py) — a notice that happens to name a bank (e.g.
    # "HBL tops the Banking Mohtasib complaint chart") must not become a
    # mention, or it silently leaks into share-of-voice/sentiment.
    s = db.session
    n = 0
    for iid, title, body in p.matchable_items(s, ws):
        for bid, rule, review, exc, reason in entity.classify(
                " ".join(filter(None, [title, body])), brands):
            n += p.insert_mention(s, ws, iid, bid, rule, review, exc, reason)
    db.commit()
    log(f"match · {n} new mentions")
