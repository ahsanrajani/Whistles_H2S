"""Every review / mention attributed to one branch — the drilldown behind a
Branch & ATM card. Same attribution and issue lexicon as ``branch_perf.scan``,
so an issue filter returns exactly the rows behind that card's issue count."""
from . import branch_perf, branch_resolver, vertical
from db import repositories as repo
from db.analytics import scanners

from .insights import _age_days

MAX_LIMIT = 100


def items(db, ws, key, *, days=None, issue=None, offset=0, limit=25):
    """Newest-first page of a branch's items, optionally one issue theme only."""
    kind = vertical.of(db, ws)
    resolver = branch_resolver.for_workspace(db, ws)
    branch = next(({"key": k, "name": n, "code": c or k, "city": city}
                   for k, n, c, city, _a in resolver.entries if k == key), None)
    limit = max(1, min(int(limit), MAX_LIMIT))
    offset = max(0, int(offset))
    base = {"branch": branch, "issue": issue, "policy": branch_perf.policy(kind),
            "total": 0, "offset": offset, "limit": limit, "items": []}
    focus = repo.brands.focus_id_name(db.session, ws)
    if branch is None or not focus:
        return base

    matched = []
    for (iid, surface, source, outlet, published_at, url, text, rating,
         raw_json, sentiment, category) in scanners.branch_perf_rows(db.session, focus[0]):
        if days is not None:
            age = _age_days(published_at)
            if age is None or not 0 <= age < days:
                continue
        if not (text or "").strip():
            continue
        row_key, _by_text = branch_perf.row_branch_key(raw_json, text, resolver)
        if row_key != key:
            continue
        issues = (branch_perf._issue_hits(text, kind)
                  if branch_perf.is_bad(rating, sentiment, category) else [])
        if issue and issue not in issues:
            continue
        matched.append({
            "id": iid, "surface": surface, "source": source, "outlet": outlet,
            "url": url, "published_at": published_at, "rating": rating,
            "sentiment": sentiment, "category": category, "issues": issues,
            "text": " ".join(text.split()),
        })

    matched.sort(key=lambda r: (r["published_at"] or "", r["id"]), reverse=True)
    base["total"] = len(matched)
    base["items"] = matched[offset:offset + limit]
    return base
