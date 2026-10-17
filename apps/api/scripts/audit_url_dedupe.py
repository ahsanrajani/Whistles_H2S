#!/usr/bin/env python3
"""P2.1 backfill audit — how many historic items were folded by URL alone.

    python scripts/audit_url_dedupe.py            # report only
    python scripts/audit_url_dedupe.py --unfold   # also un-fold the wrong ones

Before P2.1 ``collection/dedupe.py`` folded any two items that shared a ``url``.
Those folds live in ``dupe_edge`` with ``method = 'exact_url'``. This reports,
per workspace, how many exist and how many are *not* also duplicates by
``content_hash`` or normalised title (i.e. were wrongly folded). ``--unfold``
deletes those wrong edges so the items reappear in triage / sentiment /
branch_perf.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, os.pardir)))

from sqlalchemy import text  # noqa: E402

from db.session import operator_engine  # noqa: E402

# exact_url edges whose folded item is NOT a genuine duplicate of its canonical
# by content_hash or normalised (outlet, title)
_WRONG = text("""
    SELECT d.workspace_id, count(*) AS wrong
    FROM dupe_edge d
    JOIN item f ON f.id = d.item_id
    JOIN item c ON c.id = d.canonical_id
    WHERE d.method = 'exact_url'
      AND NOT (f.content_hash IS NOT NULL AND f.content_hash <> ''
               AND f.content_hash = c.content_hash)
      AND NOT (f.title IS NOT NULL AND trim(f.title) <> ''
               AND lower(trim(f.title)) = lower(trim(c.title))
               AND f.outlet IS NOT DISTINCT FROM c.outlet)
    GROUP BY d.workspace_id
    ORDER BY d.workspace_id
""")

_TOTAL = text("SELECT workspace_id, count(*) FROM dupe_edge "
              "WHERE method = 'exact_url' GROUP BY workspace_id ORDER BY workspace_id")

_UNFOLD = text("""
    DELETE FROM dupe_edge d
    USING item f, item c
    WHERE d.item_id = f.id AND d.canonical_id = c.id AND d.method = 'exact_url'
      AND NOT (f.content_hash IS NOT NULL AND f.content_hash <> ''
               AND f.content_hash = c.content_hash)
      AND NOT (f.title IS NOT NULL AND trim(f.title) <> ''
               AND lower(trim(f.title)) = lower(trim(c.title))
               AND f.outlet IS NOT DISTINCT FROM c.outlet)
""")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--unfold", action="store_true",
                    help="delete the wrongly-folded exact_url edges")
    args = ap.parse_args()

    with operator_engine.begin() as conn:
        total = dict(conn.execute(_TOTAL).all())
        wrong = dict(conn.execute(_WRONG).all())
        all_ws = sorted(set(total) | set(wrong))
        print(f"{'workspace':>10}  {'exact_url edges':>16}  {'wrongly folded':>14}")
        for ws in all_ws:
            print(f"{ws:>10}  {total.get(ws, 0):>16}  {wrong.get(ws, 0):>14}")
        print(f"{'TOTAL':>10}  {sum(total.values()):>16}  {sum(wrong.values()):>14}")
        if args.unfold:
            removed = conn.execute(_UNFOLD).rowcount
            print(f"\nun-folded {removed} wrongly-folded edge(s).")
        elif sum(wrong.values()):
            print("\nre-run with --unfold to remove the wrongly-folded edges.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
