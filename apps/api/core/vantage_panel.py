"""Vantage AI-visibility panel (build plan §7) -- the first Vantage surface.

A fixed prompt set per workspace is asked of every model in
``integrations.llm.panel.PANEL``; each answer is scanned for brand mentions
with the same ``core.entity.classify`` the listening pipeline uses, so
"visibility" is evidence-backed (the raw answer is kept), not a fabricated
score. Nothing runs on a schedule -- every call costs real money, so a run is
always an explicit, human-triggered action (``core/vantage_panel.py::run``,
wired to an admin route).
"""
import re
from datetime import datetime, timezone

from core import entity, stats
from db.repositories import brands as brands_repo
from db.repositories import llm_panel
from integrations import llm

# A literal "Chase Securities" hit that also talks about JPMorgan Chase /
# Chase Bank is very likely the model confusing the much larger, similarly
# -named US bank with our client -- not a real answer about the brand being
# measured. Computed at read time (not stored) so it applies retroactively
# to responses already recorded before this rule existed.
_WRONG_ENTITY_RE = re.compile(
    r"jpmorgan|j\.?\s*p\.?\s*morgan|chase\s+bank|chase\.com|chase\s*&\s*co|"
    r"chase\s+usa|\bjpmc\b", re.I)

# The model saying outright it has no information, rather than confidently
# answering (correctly or not) -- a distinct "not in training data" signal.
_UNCERTAIN_RE = re.compile(
    r"i don'?t have (access|specific|current|enough|real-time|up-to-date|"
    r"detailed)|i do not have|i'?m not aware|i am not aware|"
    r"no (specific )?information (is )?available|"
    r"cannot (find|provide) (specific )?information|"
    r"don'?t have (real-time|up-to-date|current) (data|information)", re.I)


def _response_flags(text: str, *, focus_hit: bool) -> list[str]:
    """Rule names, auditable back to the regex above -- not a model score."""
    flags = []
    if focus_hit and _WRONG_ENTITY_RE.search(text or ""):
        flags.append("possible_wrong_entity")
    if _UNCERTAIN_RE.search(text or ""):
        flags.append("uncertain")
    return flags


def starter_prompts(focus_name: str, competitor_names: list[str]) -> list[str]:
    """A generic, brand-name-driven starter set -- edit or replace via the
    admin prompt list. Not a claim about the client, just questions to ask."""
    rivals = ", ".join(competitor_names) if competitor_names else "its competitors"
    return [
        f"What do you know about {focus_name}?",
        f"Is {focus_name} a good, trustworthy choice in its market?",
        f"Who are the leading firms in {focus_name}'s industry, and where does "
        f"{focus_name} rank among them?",
        f"How does {focus_name} compare to {rivals}?",
        f"What are common complaints or concerns about {focus_name}?",
        f"If I were choosing between {focus_name} and {rivals}, which would you "
        f"recommend and why?",
    ]


def ensure_starter_prompts(session, workspace_id: int) -> int:
    """Seed the starter prompts if the workspace has none yet. Returns how many
    were added. Caller commits."""
    if llm_panel.count(session, workspace_id):
        return 0
    focus = brands_repo.focus_id_name(session, workspace_id)
    if not focus:
        return 0
    competitors = brands_repo.competitor_names(session, workspace_id)
    added = 0
    for p in starter_prompts(focus[1], competitors):
        llm_panel.add_prompt(session, workspace_id, p)
        added += 1
    return added


def run(session, workspace_id: int, keys: dict, *, day=None, log=None) -> dict:
    """Ask every active prompt to every panel model; record one evidence row
    per (prompt, model) call. Caller commits. Returns a summary dict."""
    log = log or (lambda *_a: None)
    day = day or datetime.now(timezone.utc).date()
    prompts = llm_panel.active_prompts(session, workspace_id)
    match_brands = brands_repo.match_rules(session, workspace_id)
    by_id = {b["id"]: b for b in match_brands}

    asked = failed = 0
    for prompt_row in prompts:
        for member in llm.PANEL:
            try:
                provider, model, text = llm.ask(
                    member["id"], prompt_row["prompt_text"], keys=keys)
            except llm.LlmError as exc:
                llm_panel.record_error(session, workspace_id, prompt_row["id"],
                                       model=member["id"], day=day, error=exc)
                log(f"vantage panel · {member['id']} · prompt {prompt_row['id']} "
                    f"· failed ({exc})")
                failed += 1
                continue
            hits = entity.classify(text, match_brands)
            mentions = [
                {"brand_id": bid, "name": by_id[bid]["name"],
                 "is_focus": bool(by_id[bid]["is_focus"]), "rule": rule,
                 "excluded": bool(excluded)}
                for bid, rule, _review, excluded, _reason in hits
            ]
            llm_panel.record_response(
                session, workspace_id, prompt_row["id"], provider=provider,
                model=model, day=day, response_text=text, mentions=mentions)
            log(f"vantage panel · {member['id']} · prompt {prompt_row['id']} "
                f"· {len(mentions)} brand mention(s)")
            asked += 1
    return {"prompts": len(prompts), "models": len(llm.PANEL),
            "asked": asked, "failed": failed, "day": day.isoformat()}


def _wilson(k, n):
    if not n:
        return {"rate": None, "wilson": [None, None], "n": n, "k": k}
    p, lo, hi = stats.wilson(k, n)
    return {"rate": p, "wilson": [lo, hi], "n": n, "k": k}


def insights(session, workspace_id: int, *, since=None) -> dict:
    """Wilson-scored mention rate per brand across every panel response so
    far, plus "visibility gaps" -- a response that named a competitor but
    never the focus brand. A focus-brand hit flagged `possible_wrong_entity`
    (see `_response_flags`) is excluded from the count -- the model was very
    likely describing JPMorgan Chase, not our client, and counting it would
    overstate real visibility."""
    rows = llm_panel.responses(session, workspace_id, since=since)
    answered = [r for r in rows if not r["error"]]
    total = len(answered)

    per_brand: dict[str, dict] = {}
    gaps = []
    confused_count = uncertain_count = 0
    for r in answered:
        mentions = r["mentions"] or []
        names = {m["name"] for m in mentions}
        focus_hit = any(m["is_focus"] for m in mentions)
        flags = _response_flags(r["response_text"], focus_hit=focus_hit)
        confused = "possible_wrong_entity" in flags
        if confused:
            confused_count += 1
        if "uncertain" in flags:
            uncertain_count += 1
        for m in mentions:
            if m["is_focus"] and confused:
                continue
            entry = per_brand.setdefault(
                m["name"], {"is_focus": m["is_focus"], "k": 0})
            entry["k"] += 1
        real_focus_hit = focus_hit and not confused
        if names and not real_focus_hit:
            gaps.append({"prompt_id": r["prompt_id"], "model": r["model"],
                        "day": r["day"].isoformat(),
                        "competitors_named": sorted(names)})

    brands = [
        {"name": name, "is_focus": v["is_focus"], **_wilson(v["k"], total)}
        for name, v in per_brand.items()
    ]
    brands.sort(key=lambda b: (not b["is_focus"], -(b["k"] or 0)))
    return {
        "total_responses": total, "failed_calls": len(rows) - total,
        "brands": brands, "visibility_gaps": gaps[:20],
        "confused_responses": confused_count, "uncertain_responses": uncertain_count,
    }


def evidence(session, workspace_id: int, *, since=None, limit=100) -> list[dict]:
    """The raw prompt + model answer + brand hits behind `insights()`, newest
    first -- what was actually asked and what actually came back. `flags`
    carries the same possible_wrong_entity / uncertain rules `insights()`
    scores against, so a reviewer can see exactly why a response was (or
    wasn't) counted as real visibility."""
    rows = llm_panel.responses(session, workspace_id, since=since, limit=limit)
    out = []
    for r in rows:
        mentions = r["mentions"] or []
        focus_hit = any(m["is_focus"] for m in mentions)
        flags = [] if r["error"] else _response_flags(r["response_text"], focus_hit=focus_hit)
        out.append({
            "id": r["id"], "prompt_id": r["prompt_id"], "prompt_text": r["prompt_text"],
            "provider": r["provider"], "model": r["model"], "day": r["day"].isoformat(),
            "response_text": r["response_text"], "mentions": mentions,
            "error": r["error"], "flags": flags,
        })
    return out


def report(session, workspace_id: int, *, since=None) -> dict:
    """A deterministic narrative over `insights()` -- every sentence traces to
    a real number already in the payload; nothing here is model-generated."""
    ins = insights(session, workspace_id, since=since)
    total = ins["total_responses"]
    focus = next((b for b in ins["brands"] if b["is_focus"]), None)
    rivals = sorted((b for b in ins["brands"] if not b["is_focus"]),
                    key=lambda b: -(b["k"] or 0))
    top_rival = rivals[0] if rivals else None

    headline: list[str] = []
    if not total:
        headline.append("No panel responses recorded yet — run the panel to generate a report.")
    elif focus:
        lo, hi = focus["wilson"]
        pct = round(focus["rate"] * 100)
        headline.append(
            f"{focus['name']} was mentioned in {focus['k']} of {total} panel "
            f"responses ({pct}%, 95% CI {round(lo * 100)}–{round(hi * 100)}%).")
    else:
        headline.append(
            f"The focus brand was not mentioned in any of the {total} panel responses so far.")
    if top_rival:
        headline.append(
            f"{top_rival['name']} was the most-mentioned competitor "
            f"({top_rival['k']} of {total}).")

    improvements: list[str] = []
    if ins["visibility_gaps"]:
        named = sorted({c for g in ins["visibility_gaps"] for c in g["competitors_named"]})
        improvements.append(
            f"In {len(ins['visibility_gaps'])} response(s), a model named "
            f"{', '.join(named)} without mentioning "
            f"{focus['name'] if focus else 'the focus brand'} at all — these are the "
            "prompts most worth targeted content or PR against.")
    if focus and focus["wilson"][1] is not None and focus["wilson"][1] < 0.5:
        improvements.append(
            f"Even the upper end of {focus['name']}'s mention-rate interval is under "
            "50% — visibility here isn't yet reliably established; more prompts and a "
            "repeat run would narrow the interval.")
    if focus is None and total:
        improvements.append(
            "The focus brand hasn't been named by any panel model yet — that is the "
            "single biggest visibility gap in this report.")
    if ins.get("confused_responses"):
        name = focus["name"] if focus else "the focus brand"
        improvements.append(
            f"{ins['confused_responses']} of {total} panel response(s) appear to confuse "
            f"{name} with JPMorgan Chase / Chase Bank — a different, unrelated company — "
            "rather than actually describing it. Those were excluded from the mention rate "
            "above; a prospect asking an AI assistant about the brand may be getting the "
            "wrong company's information, which is its own visibility risk worth fixing "
            "through clearer, more distinctive branding and content.")
    if ins.get("uncertain_responses"):
        improvements.append(
            f"{ins['uncertain_responses']} response(s) said outright they had no "
            f"information to answer with — brand awareness in these models' training "
            "data is low, independent of the mention-rate numbers above.")
    if not improvements:
        improvements.append("No visibility gaps found in the responses recorded so far.")

    return {**ins, "headline": headline, "improvements": improvements}
