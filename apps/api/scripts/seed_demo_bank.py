#!/usr/bin/env python3
"""Seed "Lumora Bank": an enterprise-wide, fully fictional demo tenant that
populates every module of the product at once.

    cd apps/api && python scripts/seed_demo_bank.py            # create
    cd apps/api && python scripts/seed_demo_bank.py --reset    # drop it and rebuild
    cd apps/api && python scripts/seed_demo_bank.py --reset --drop-default-workspace
                                                                # also remove the stock "Bank Alfalah" tenant the
                                                                # app seeds on first boot, so the instance shows
                                                                # only fictional institutions

What it builds (all invented; nothing scraped, no real person or regulator):
  listening   ~1,500 mentions of Lumora Bank and four fictional rivals over 90 days across
              news, X, Reddit, YouTube, LinkedIn and the web, in English, Roman Urdu and Urdu,
              with sentiment and classification, plus app-store reviews and store ratings
  branches    a 24-row branch/ATM catalogue with coordinates and Google-style reviews,
              three branches in trouble
  risk        scam waves on the bank's own pages (with repeat offenders), severe complaints for
              triage, churn language, fraud reports, an app outage and a rival's breach, and
              regulator notices including one that names the bank
  social      owned posts on five platforms with engagement, comments, and 90 days of the
              engagement warehouse, a content calendar in every workflow state with signal
              origins for the closed loop
  care        ten accounts across every role, 64 customers, 190 cases with messages, events
              and notes, CSAT and NPS, knowledge base, macros, auto-rules, SLAs, agent shifts
  platform    the AI-visibility panel (5 models x 8 prompts x 4 weeks), scheduled reports,
              source health, coverage ledger and call costs

Collection is switched OFF for the tenant (every source disabled and no tick scheduled), so
the live collectors can never mix real data into the demo. Logins (password demo123):
demo.admin, farah.supervisor, kamran.lead, zainab.senior, hira.agent, lumora.viewer.

Every name here is invented: the bank and its four rivals, the regulator ("National Banking
Authority"), the ombudsman, the payment network ("InstaPay") and the branch areas. Cities are
real only so the branch map has somewhere to put its pins. Any resemblance to a real
institution is coincidental.

Idempotent only through --reset: without it the script stops if the tenant already exists.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, os.pardir)))
sys.path.insert(0, HERE)

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

import json  # noqa: E402
import random  # noqa: E402

import sqlalchemy as sa  # noqa: E402

import app as _app  # noqa: E402
from core import sources  # noqa: E402
from db.repositories import brands as brand_repo  # noqa: E402
from db.repositories import source_state as source_state_repo  # noqa: E402
from db.repositories import workspaces as ws_repo  # noqa: E402
from db.session import get_operator_session  # noqa: E402

from demo_bank import care, care_ops, content, corpus as C, intel, listening, owned, risk  # noqa: E402
from demo_bank.base import Seed  # noqa: E402

MARKET, VOLUME, LANGS = "PK", "high", "en,ur,roman_urdu"


def _brand_row(name: str, is_focus: bool) -> dict:
    p = _app.brand_patterns(name)
    return {"name": name, "is_focus": 1 if is_focus else 0, "safe": json.dumps(p["safe"]), "gated": json.dumps(p["gated"]),
            "context": json.dumps(_app.STARTER_CONTEXT), "exclude": json.dumps([])}


LEGACY_NAMES = ("Meridian Bank",)            # an earlier draft of this demo, cleaned up on --reset
DEFAULT_TENANTS = ("Bank Alfalah",)           # the stock tenant db.bootstrap.seed() creates on first boot
LEGACY_USERS = ("meridian.viewer",)


def _purge_workspace(s, ws: int) -> None:
    for table in ("scheduled_task", "job"):
        s.execute(sa.text(f"DELETE FROM {table} WHERE tenant_id = :w"), {"w": ws})
    s.execute(sa.text("DELETE FROM workspace WHERE id = :w"), {"w": ws})


def _reset(s, drop_default: bool) -> None:
    names = [u for u, _r in care.STAFF] + list(LEGACY_USERS)
    ids = [r[0] for r in s.execute(sa.text('SELECT id FROM "user" WHERE username = ANY(:n)'), {"n": names})]
    for table in ("user_role", "care_agent", "agent_activity"):
        if ids:
            s.execute(sa.text(f"DELETE FROM {table} WHERE user_id = ANY(:i)"), {"i": ids})
    targets = (C.NAME,) + LEGACY_NAMES + (DEFAULT_TENANTS if drop_default else ())
    for name in targets:
        ws = ws_repo.id_by_name(s, name)
        if ws:
            _purge_workspace(s, ws)
    if ids:
        s.execute(sa.text('DELETE FROM "user" WHERE id = ANY(:i)'), {"i": ids})
    s.commit()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="delete the demo tenant first")
    ap.add_argument("--drop-default-workspace", action="store_true",
                    help="with --reset: also delete the stock Bank Alfalah tenant (and its collected data)")
    args = ap.parse_args()
    s = get_operator_session()
    try:
        if args.reset:
            _reset(s, args.drop_default_workspace)
        elif ws_repo.id_by_name(s, C.NAME):
            print("The demo tenant already exists. Re-run with --reset to rebuild it.")
            return 0
        ws = ws_repo.create(s, name=C.NAME, slug=_app.slugify(C.NAME), market=MARKET, volume_scenario=VOLUME,
                            sentiment_langs=LANGS, onboarding_step=0, created_at=_app.now())
        brand_repo.replace_all(s, ws, [_brand_row(C.FOCUS, True)] + [_brand_row(c, False) for c in C.COMPETITORS])
        for sid in sources.SOURCES:
            source_state_repo.set_enabled(s, ws, sid, False)
        s.execute(sa.text("INSERT INTO project (workspace_id, slug, name, kind) VALUES (:w, 'listening', 'Listening', 'listening') "
                          "ON CONFLICT (workspace_id, slug) DO NOTHING"), {"w": ws})
        brand_ids = {r[0]: r[1] for r in s.execute(sa.text("SELECT name, id FROM brand WHERE workspace_id = :w"), {"w": ws})}
        sd = Seed(s, ws, brand_ids, random.Random(20261017))

        care.people(sd)
        listening.chatter(sd)
        listening.app_reviews(sd)
        listening.branches(sd)
        risk.complaints(sd)
        risk.churn(sd)
        risk.fraud_reports(sd)
        risk.incidents(sd)
        risk.regulatory(sd)
        risk.boundary_rejections(sd)
        posted = owned.posts(sd)
        owned.comments(sd, posted)
        owned.other_platform_comments(sd, posted)
        owned.engagement_warehouse(sd)
        content.calendar(sd)
        custs = care.customers(sd)
        closed = care.cases(sd, custs)
        care_ops.knowledge(sd)
        care_ops.macros(sd)
        care_ops.csat(sd, closed)
        care_ops.shifts(sd)
        intel.vantage(sd)
        intel.reports(sd)
        intel.platform_health(sd)
        intel.credentials(sd)
        risk.gold_labels(sd)
        s.execute(sa.text("""UPDATE "user" SET workspace_id = :w WHERE role = 'bank_viewer'
                              AND (workspace_id IS NULL OR workspace_id NOT IN (SELECT id FROM workspace))"""), {"w": ws})
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()

    print(f"Seeded {C.NAME!r} as workspace {ws} (slug {_app.slugify(C.NAME)}).")
    print(f"  items written: {sd.n}")
    for key in sorted(sd.counts):
        print(f"  {key:28s} {sd.counts[key]}")
    print("  logins (password demo123): demo.admin, farah.supervisor, kamran.lead, zainab.senior, hira.agent, lumora.viewer")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
