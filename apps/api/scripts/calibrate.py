#!/usr/bin/env python3
"""Offline calibration: label a stratified sample of matches for precision.

    python scripts/calibrate.py            # default workspace
    python scripts/calibrate.py --per-rule 20

For each match it prints the brand, rule and text, then reads one key:
  y = really this brand   n = false match   s = skip   q = save and quit

Writes into the same gold_label table the web Review queue uses, so
insights.rule_precision / calibration_status pick the labels up immediately.
"""
import argparse
import os
import sqlite3
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, os.pardir)
sys.path.insert(0, os.path.abspath(ROOT))

for _stream in (sys.stdout, sys.stderr):          # console may be cp1252 on Windows
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from core import insights  # noqa: E402

DB = os.path.join(ROOT, "guru.db")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DB)
    ap.add_argument("--per-rule", type=int, default=12)
    ap.add_argument("--workspace", type=int, default=None)
    args = ap.parse_args()

    c = sqlite3.connect(args.db, timeout=30)
    c.execute("PRAGMA foreign_keys=ON")
    ws = args.workspace
    if ws is None:
        row = c.execute("SELECT id FROM workspace ORDER BY id LIMIT 1").fetchone()
        ws = row[0] if row else None
    if ws is None:
        print("no workspace")
        return

    for row in insights.calibration_status(c, ws):
        print(f"  {row['rule']:<16} {row['labelled']}/{row['target']} labelled"
              + ("  target met" if row["met"] else ""))
    print()

    batch = insights.review_batch(c, ws, per_rule=args.per_rule)
    if not batch:
        print("nothing unlabelled in the batch")
        return

    done = 0
    for name, surface, source, outlet, _pub, url, text, rule, _rev, lang, _s, mid in batch:
        print("-" * 72)
        print(f"[{rule}] {name}  ·  {surface} · {outlet or source} · {lang}")
        print((text or "").strip()[:500])
        if url:
            print(url)
        try:
            answer = input("really this brand?  [y]es / [n]o / [s]kip / [q]uit > ").strip().lower()
        except EOFError:
            answer = "q"
        if answer == "q":
            break
        if answer == "s" or answer not in ("y", "n"):
            continue
        c.execute(
            """INSERT OR REPLACE INTO gold_label(mention_id,correct,labelled_at,labelled_by)
               VALUES (?,?,?,?)""",
            (mid, 1 if answer == "y" else 0,
             datetime.now(timezone.utc).isoformat(), os.environ.get("USER") or "cli"))
        c.commit()
        done += 1

    print(f"\nsaved {done} labels")
    for row in insights.calibration_status(c, ws):
        if row["precision"] is not None:
            print(f"  {row['rule']:<16} precision {row['precision']*100:.1f}% "
                  f"(±{max(row['precision']-row['lo'], row['hi']-row['precision'])*100:.1f}) "
                  f"on {row['labelled']} labels")
    c.close()


if __name__ == "__main__":
    main()
