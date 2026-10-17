#!/usr/bin/env python3
"""P2.8 gate — match precision per brand × pattern class, with Wilson intervals.

    python scripts/precision_report.py            # default (first) workspace
    python scripts/precision_report.py --ws 2

The build-plan gate: precision >= 0.95 for safe patterns, >= 0.85 for gated,
each with its interval reported, over a 200-item labelled sample. Only when
this passes should the legacy guru.db be discarded.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, os.pardir)))

from core import precision  # noqa: E402
from db.legacy import operator_conn  # noqa: E402
from db.repositories import workspaces  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ws", type=int, default=None, help="workspace id")
    args = ap.parse_args()

    conn = operator_conn()
    try:
        ws = args.ws or workspaces.first_id(conn.session)
        if ws is None:
            print("no workspace")
            return 1
        report = precision.match_precision(conn, ws)
    finally:
        conn.close()

    print(f"workspace {ws} · {report['sample_size']}/{report['sample_target']} labels\n")
    print(f"{'brand':<22} {'class':<6} {'matched':>8} {'labelled':>9} "
          f"{'precision':>10} {'95% CI':>18} {'target':>7} {'met':>5}")
    for b in report["brands"]:
        for cls in ("safe", "gated"):
            c = b[cls]
            ci = (f"[{c['ci_low']:.3f}, {c['ci_high']:.3f}]"
                  if c["ci_low"] is not None else "—")
            p = f"{c['precision']:.3f}" if c["precision"] is not None else "—"
            print(f"{b['brand']:<22} {cls:<6} {c['matched']:>8} {c['labelled']:>9} "
                  f"{p:>10} {ci:>18} {c['target']:>7.2f} "
                  f"{'yes' if c['met'] else 'no':>5}")
    print(f"\nall measured classes meet target: "
          f"{'YES' if report['all_measured_met'] else 'NO'}")
    return 0 if report["all_measured_met"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
