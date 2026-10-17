"""AI-visibility panel (Vantage), scheduled reports, and the platform's own
health and cost records: source health, the listening-coverage ledger and
per-source call costs. Collection is disabled for this tenant, so none of
these rows trigger a real fetch."""
import json
import uuid
from datetime import timedelta

from sqlalchemy import text

from core import sources
from integrations.llm import panel

from . import corpus as C
from .base import NOW, Seed, dt, stamp

PROMPTS = [
 "Which bank is best for a salary account in Pakistan?", "Best mobile banking app in Pakistan for everyday payments",
 "Which Pakistani bank has the highest savings profit rate?", "Most trusted bank for home financing in Pakistan",
 "Best credit card in Pakistan for cashback and rewards", "Which bank is best for sending remittances home to Pakistan?",
 "Which banks in Pakistan have good Islamic banking?", "Is Lumora Bank a good bank? Compare it with its competitors.",
]
_MODELS = {"gemini": ("google", "gemini-3.5-flash"), "gpt-4o-mini": ("openrouter", "openai/gpt-4o-mini"),
           "perplexity-sonar": ("openrouter", "perplexity/sonar"), "claude-haiku": ("openrouter", "anthropic/claude-haiku-4.5"),
           "llama-3.1": ("openrouter", "meta-llama/llama-3.1-8b-instruct")}
SCHEDULES = [
 ("Weekly social performance (board)", "social", "pdf", "0 4 * * 1", ["cmo@lumorabank.example", "head.digital@lumorabank.example"]),
 ("Daily SLA and queue health", "sla", "xlsx", "30 3 * * *", ["care.ops@lumorabank.example"]),
 ("Monthly CSAT summary", "csat", "pdf", "0 5 1 * *", ["head.cx@lumorabank.example"]),
 ("Weekly complaints digest for compliance", "complaints", "xlsx", "0 4 * * 5", ["compliance@lumorabank.example"]),
 ("Agent shift report", "care_agents", "csv", "0 2 * * *", ["workforce@lumorabank.example"]),
 ("Daily MIS: cases opened and closed", "mis_daily", "xlsx", "45 3 * * *", ["mis@lumorabank.example"]),
]
_DEGRADED: dict = {}   # every collector healthy: no standing alarm in the demo


def vantage(sd: Seed) -> None:
    rng, s, ws = sd.rng, sd.s, sd.ws
    ids = [s.execute(text("INSERT INTO llm_prompt (workspace_id, prompt_text, active) VALUES (:ws, :p, true) RETURNING id"),
                     {"ws": ws, "p": p}).scalar_one() for p in PROMPTS]
    names = list(C.BRANDS)
    for back, p_focus in ((0, 0.62), (7, 0.55), (14, 0.47), (21, 0.4)):
        day = (NOW - timedelta(days=back)).date()
        for pid, prompt in zip(ids, PROMPTS):
            for member, (provider, model) in _MODELS.items():
                picks = [b for b in rng.sample(names[1:], k=rng.randint(2, 3))]
                if rng.random() < (1.0 if "Lumora" in prompt else p_focus):
                    picks.insert(rng.randint(0, 2), C.FOCUS)
                text_ = (f"For \"{prompt.rstrip('?')}\", commonly mentioned options in Pakistan include "
                         + ", ".join(picks[:-1]) + f" and {picks[-1]}. {picks[0]} is often cited first for its overall "
                         "reputation, while others are noted for rates, digital features or branch reach. Check current terms before deciding.")
                mentions = [{"brand_id": sd.brand_ids[b], "name": b, "is_focus": b == C.FOCUS, "rule": "safe", "excluded": False}
                            for b in picks]
                s.execute(text("""INSERT INTO llm_panel_response (workspace_id, prompt_id, provider, model, day, response_text, mentions)
                                  VALUES (:ws, :p, :pr, :m, :d, :t, CAST(:mn AS jsonb))"""),
                          {"ws": ws, "p": pid, "pr": provider, "m": model, "d": day, "t": text_, "mn": json.dumps(mentions)})
    sd.bump("llm_panel_response", 4 * len(PROMPTS) * len(_MODELS))
    assert set(_MODELS) <= {m["id"] for m in panel.PANEL}


def reports(sd: Seed) -> None:
    for name, kind, fmt, cron, to in SCHEDULES:
        sd.s.execute(text("""INSERT INTO report_schedule (workspace_id, name, kind, format, params, cron, recipients, active, last_run_at, last_status, created_by)
                             VALUES (:ws, :n, :k, :f, '{}'::jsonb, :c, CAST(:r AS jsonb), true, :lr, 'ok', :u)"""),
                     {"ws": sd.ws, "n": name, "k": kind, "f": fmt, "c": cron, "r": json.dumps(to),
                      "lr": NOW - timedelta(hours=sd.rng.randint(3, 40)), "u": sd.users["demo.admin"]})
    sd.bump("report_schedule", len(SCHEDULES))


def platform_health(sd: Seed) -> None:
    """Source health, the coverage ledger for the latest run, and call costs."""
    rng, s, ws = sd.rng, sd.s, sd.ws
    run_id = uuid.uuid4().hex[:12]
    s.execute(text("""INSERT INTO run (id, workspace_id, started_at, finished_at, state, progress, new_items)
                      VALUES (:i, :ws, :a, :b, 'done', '100%', :n)"""),
              {"i": run_id, "ws": ws, "a": stamp(0.05, 6), "b": stamp(0.04, 6, 14), "n": sd.n})
    for sid, meta in sources.SOURCES.items():
        cadence = int(meta.get("cadence", 0))
        if cadence == 0:
            continue
        band, fails, err = _DEGRADED.get(sid, ("ok", 0, None))
        ok_at = None if band == "down" else NOW - timedelta(seconds=rng.randint(60, max(120, cadence)))
        s.execute(text("""
            INSERT INTO source_state (workspace_id, source, cursor_kind, circuit_state, enabled, consecutive_failures, opened_at,
                                      last_attempt_at, last_success_at, last_error, items_last_run, last_run_id, updated_at)
            VALUES (:ws, :s, 'timestamp', :cs, false, :f, :op, :la, :ls, :e, :n, :r, now())
            ON CONFLICT (workspace_id, source) DO UPDATE SET circuit_state = :cs, enabled = false, consecutive_failures = :f,
              last_attempt_at = :la, last_success_at = :ls, last_error = :e, items_last_run = :n"""),
                  {"ws": ws, "s": sid, "cs": "open" if band == "down" else "closed", "f": fails,
                   "op": NOW - timedelta(hours=6) if band == "down" else None, "la": NOW - timedelta(minutes=rng.randint(1, 50)),
                   "ls": ok_at, "e": err, "n": rng.randint(0, 40), "r": run_id})
        for back in range(30):
            if rng.random() < 0.8 and meta.get("unit_cost") is not None:
                calls = rng.randint(1, 6)
                s.execute(text("""INSERT INTO call_log (run_id, workspace_id, source, calls, units, unit_cost_usd, ok, at)
                                  VALUES (:r, :ws, :s, :c, :u, :uc, :ok, :at)"""),
                          {"r": run_id, "ws": ws, "s": sid, "c": calls, "u": calls * rng.randint(1, 20),
                           "uc": float(meta.get("unit_cost") or 0), "ok": 1 if rng.random() > 0.04 else 0, "at": stamp(back, 6)})
    by_surface: dict[str, list[dict]] = {}
    for meta in sources.SOURCES.values():
        if meta.get("client_safe") and meta["surface"] != "—":
            by_surface.setdefault(meta["surface"], []).append(meta)
    for surface, metas in by_surface.items():
        labels = [m["label"] for m in metas]
        s.execute(text("""INSERT INTO surface_status (run_id, workspace_id, surface, state, n_sources, estimable, note)
                          VALUES (:r, :ws, :sf, 'collected', :n, :e, :note)"""),
                  {"r": run_id, "ws": ws, "sf": surface, "n": len(labels), "e": 1 if len(labels) >= 2 else 0, "note": "; ".join(labels)})
    sd.bump("source_state", len(sources.SOURCES))


def credentials(sd: Seed) -> None:
    """The only credential seeded: the brand's own (fictional) domains, which the brand-abuse monitor needs to
    generate look-alikes. No collector credentials: collection is off for this tenant."""
    sd.s.execute(text("""INSERT INTO api_key (workspace_id, env_var, label, value, status)
                         VALUES (:ws, 'BRAND_DOMAINS', 'Brand domains', 'lumorabank.example lumora-digital.example', 'present')
                         ON CONFLICT (workspace_id, env_var) DO UPDATE SET value = EXCLUDED.value, status = 'present'"""),
                 {"ws": sd.ws})
