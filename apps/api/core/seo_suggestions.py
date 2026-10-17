"""LLM-generated SEO recommendations (Vantage's SEO tab). Human-triggered
only -- every call costs real money, same posture as the AI-visibility panel
and the DataForSEO crawl/keyword runs (never scheduled). Grounded only in the
real crawl/CWV/keyword/backlink/search-visibility facts already on file for
the workspace's focus brand -- the prompt hands the model those facts
explicitly and tells it not to invent any other, so a suggestion is always
traceable back to a real, already-collected number.
"""
import json
import re

from core import seo, seo_crawl, seo_report
from db.repositories import brands as brands_repo
from db.repositories import seo_suggestion as repo
from integrations.llm import panel

MODEL_ID = "claude-haiku"

_LINE_RE = re.compile(r"^(HIGH|MEDIUM|LOW):\s*(.+)$", re.I)


class NoSeoDataError(Exception):
    """No search-visibility/keyword/crawl data on file yet for this workspace."""


def _facts_for_focus(session, workspace_id: int) -> dict | None:
    brands = brands_repo.match_rules(session, workspace_id)
    visibility = seo.domain_visibility(session, workspace_id, brands=brands)
    keywords = seo_report.report(session, workspace_id)
    crawl = seo_crawl.report(session, workspace_id)

    # domain_visibility() always emits one entry per known brand, even with
    # zero real domains found for it -- an empty own_domains list is not
    # "data on file", it's "checked and found nothing yet".
    focus_vis = next(
        (b for b in visibility.get("brands", []) if b.get("is_focus") and b.get("own_domains")),
        None)
    focus_kw = next((b for b in keywords.get("brands", []) if b.get("is_focus")), None)
    focus_crawl = next((b for b in crawl.get("brands", []) if b.get("is_focus")), None)
    if not (focus_vis or focus_kw or focus_crawl):
        return None
    facts: dict = {}
    if focus_vis:
        facts["search_visibility"] = focus_vis
    if focus_kw:
        facts["keywords_and_backlinks"] = focus_kw
    if focus_crawl:
        facts["site_crawl_and_core_web_vitals"] = focus_crawl
    return facts


def _prompt(brand_name: str, facts: dict) -> str:
    return "\n".join([
        f"You are an SEO analyst. Below are REAL, measured facts about "
        f"{brand_name}'s website and how it shows up in search -- every number "
        f"came from a live DataForSEO crawl/keyword/backlink pull or a real "
        f"Google search-results check. Do not invent any fact that is not here.",
        "",
        f"FACTS (JSON):\n{json.dumps(facts, indent=2, default=str)[:6000]}",
        "",
        "Give 5-8 concrete, prioritized SEO recommendations grounded only in "
        'these facts. One per line, each starting with exactly one of "HIGH:", '
        '"MEDIUM:" or "LOW:" followed by the recommendation in one or two '
        "sentences. No preamble, no summary, no markdown -- just the lines.",
    ])


def _parse(text: str) -> list[dict]:
    out = []
    for line in text.splitlines():
        line = line.strip().lstrip("-*•").strip()
        m = _LINE_RE.match(line)
        if m:
            out.append({"priority": m.group(1).upper(), "text": m.group(2).strip()})
    return out


def generate(session, workspace_id: int, keys: dict) -> dict:
    """One real, costed LLM call. Raises NoSeoDataError if the visibility/
    keyword/crawl checks have never been run for this workspace -- there is
    nothing real to ground a suggestion in yet."""
    brands = brands_repo.match_rules(session, workspace_id)
    focus = next((b for b in brands if b.get("is_focus")), None)
    facts = _facts_for_focus(session, workspace_id)
    if not focus or not facts:
        raise NoSeoDataError(
            "No SEO data on file yet -- run search visibility, technical SEO and "
            "site health at least once first.")

    prompt = _prompt(focus["name"], facts)
    try:
        provider, model, text = panel.ask(MODEL_ID, prompt, keys=keys)
    except Exception as exc:                                          # noqa: BLE001
        return repo.record(session, workspace_id, provider="openrouter", model=MODEL_ID,
                           prompt=prompt, raw_text="", suggestions=[], error=str(exc))

    return repo.record(session, workspace_id, provider=provider, model=model,
                       prompt=prompt, raw_text=text, suggestions=_parse(text), error=None)


def latest(session, workspace_id: int) -> dict | None:
    return repo.latest(session, workspace_id)
