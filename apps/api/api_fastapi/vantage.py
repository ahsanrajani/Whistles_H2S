"""Vantage AI-visibility panel (build plan §7). Reading the panel (prompts,
insights) only needs reporting:view, same as any other report — configuring
prompts and triggering a run (real, costed LLM calls) needs admin:edit and is
always an explicit action, never scheduled."""
import uuid

from fastapi import APIRouter, Body, Depends

import app as _app
from core import seo, seo_crawl, seo_report, seo_suggestions, vantage_panel
from db import repositories as repo
from jobs import runner
from jobs import vantage_panel as panel_job

from .deps import ApiError, Ctx, guard

router = APIRouter(prefix="/api/v1", tags=["vantage"])


@router.get("/vantage/prompts")
def vantage_prompts(ctx: Ctx = Depends(guard("reporting", "view"))):
    added = vantage_panel.ensure_starter_prompts(ctx.db.session, ctx.ws_id)
    if added:
        ctx.db.commit()
    rows = repo.llm_panel.list_prompts(ctx.db.session, ctx.ws_id)
    ctx.close()
    return {"prompts": [
        {"id": r["id"], "prompt_text": r["prompt_text"], "active": r["active"],
         "created_at": r["created_at"].isoformat()} for r in rows]}


@router.post("/vantage/prompts")
def vantage_add_prompt(body: dict | None = Body(default=None),
                       ctx: Ctx = Depends(guard("admin", "edit", operator=True))):
    text = ((body or {}).get("prompt_text") or "").strip()
    if not text:
        ctx.close()
        raise ApiError(400, "prompt_text is required")
    pid = repo.llm_panel.add_prompt(ctx.db.session, ctx.ws_id, text)
    ctx.db.commit()
    actor, ws = ctx.session.get("user_id"), ctx.ws_id
    ctx.close()
    _app.audit(actor=actor, tenant_id=ws, action="vantage.prompt_add", target=str(pid))
    return {"ok": True, "id": pid}


@router.patch("/vantage/prompts/{prompt_id}")
def vantage_set_prompt(prompt_id: int, body: dict | None = Body(default=None),
                       ctx: Ctx = Depends(guard("admin", "edit", operator=True))):
    active = bool((body or {}).get("active", True))
    repo.llm_panel.set_prompt_active(ctx.db.session, ctx.ws_id, prompt_id, active)
    ctx.db.commit()
    actor, ws = ctx.session.get("user_id"), ctx.ws_id
    ctx.close()
    _app.audit(actor=actor, tenant_id=ws, action="vantage.prompt_set",
               target=str(prompt_id), after={"active": active})
    return {"ok": True, "id": prompt_id, "active": active}


@router.delete("/vantage/prompts/{prompt_id}")
def vantage_delete_prompt(prompt_id: int,
                          ctx: Ctx = Depends(guard("admin", "edit", operator=True))):
    repo.llm_panel.delete_prompt(ctx.db.session, ctx.ws_id, prompt_id)
    ctx.db.commit()
    actor, ws = ctx.session.get("user_id"), ctx.ws_id
    ctx.close()
    _app.audit(actor=actor, tenant_id=ws, action="vantage.prompt_delete", target=str(prompt_id))
    return {"ok": True}


@router.post("/vantage/panel/run")
def vantage_run_panel(ctx: Ctx = Depends(guard("admin", "edit", operator=True))):
    """Enqueue one panel run: every active prompt to every panel model. Real,
    costed LLM calls — never triggered automatically. Runs on the background
    worker (jobs/vantage_panel.py): a run is minutes of sequential calls, and
    on the request thread it outlived the proxy. At most one run per workspace
    is in flight; a repeat click returns the running job instead of paying twice."""
    prefix = panel_job.job_prefix(ctx.ws_id)
    jobs, lock = _app._jobs, _app._lock
    with lock:
        running = next((key for key, value in jobs.items()
                        if key.startswith(prefix) and value.get("state") in ("queued", "running")),
                       None)
    if running:
        ctx.close()
        return {"ok": True, "job_id": running, "already": True}
    job_id = prefix + uuid.uuid4().hex[:10]
    runner.enqueue(ctx.db.session, "vantage_panel",
                   {"ws": ctx.ws_id, "job_id": job_id, "actor": ctx.session.get("user_id")},
                   max_attempts=1, tenant_id=ctx.ws_id)
    ctx.db.commit()
    ctx.close()
    with lock:
        jobs[job_id] = {"state": "queued", "lines": ["queued"]}
    return {"ok": True, "job_id": job_id, "already": False}


@router.get("/vantage/insights")
def vantage_insights(since: str = "", ctx: Ctx = Depends(guard("reporting", "view"))):
    """Wilson-scored mention rates, visibility gaps, plus a deterministic
    headline/improvements narrative over the same numbers (core/vantage_panel
    .py::report) — every sentence traces back to a real count, nothing here
    is model-generated."""
    payload = vantage_panel.report(ctx.db.session, ctx.ws_id, since=since or None)
    ctx.close()
    return payload


@router.get("/vantage/seo")
def vantage_seo(ctx: Ctx = Depends(guard("reporting", "view"))):
    """Real, already-collected DataForSEO brand-SERP results reshaped into
    "who shows up when someone searches each tracked brand's name" -- no new
    adapter or API call, see core/seo.py."""
    brands = repo.brands.match_rules(ctx.db.session, ctx.ws_id)
    payload = seo.domain_visibility(ctx.db.session, ctx.ws_id, brands=brands)
    ctx.close()
    return payload


@router.get("/vantage/seo/report")
def vantage_seo_report(ctx: Ctx = Depends(guard("reporting", "view"))):
    """The latest real keyword-ranking + backlink snapshot on file per brand
    (core/seo_report.py) — empty until an admin runs it at least once."""
    payload = seo_report.report(ctx.db.session, ctx.ws_id)
    ctx.close()
    return payload


@router.post("/vantage/seo/run")
def vantage_seo_run(ctx: Ctx = Depends(guard("admin", "edit", operator=True))):
    """Pull real keyword rankings + a backlink summary for the focus brand,
    right now. Real, costed DataForSEO calls — never scheduled, same posture
    as the AI-visibility panel run. Competitors are deliberately excluded
    here (Hamza, 2026-09-12): resolve_domains() still resolves all tracked
    brands' domains for other callers (e.g. core/seo.py's own-domain
    attribution), but nothing about competitors should cost a paid SEO run."""
    keys = _app.keys(ctx.ws_id)
    brands = [b for b in seo_report.resolve_domains(ctx.db.session, ctx.ws_id, keys)
             if b["is_focus"]]
    lines: list[str] = []
    out = seo_report.run(ctx.db.session, ctx.ws_id, keys, brands, log=lines.append)
    ctx.db.commit()
    actor, ws = ctx.session.get("user_id"), ctx.ws_id
    ctx.close()
    _app.audit(actor=actor, tenant_id=ws, action="vantage.seo_run", after=out)
    return {"ok": True, **out, "log": lines[-50:]}


@router.get("/vantage/seo/crawl")
def vantage_seo_crawl_report(ctx: Ctx = Depends(guard("reporting", "view"))):
    """The latest real site-crawl + Core Web Vitals snapshot on file per
    brand (core/seo_crawl.py) — empty until an admin runs it."""
    payload = seo_crawl.report(ctx.db.session, ctx.ws_id)
    ctx.close()
    return payload


def _running_seo_crawl(ws_id: int) -> str | None:
    prefix = f"seocrawl-{ws_id}-"
    jobs, lock = _app._jobs, _app._lock
    with lock:
        return next((key for key, value in jobs.items()
                     if key.startswith(prefix) and value.get("state") in ("queued", "running")),
                    None)


@router.post("/vantage/seo/crawl/run")
def vantage_seo_crawl_run(body: dict | None = Body(default=None),
                          ctx: Ctx = Depends(guard("admin", "edit", operator=True))):
    """Enqueues the real crawl (up to max_pages) + a real Lighthouse Core Web
    Vitals run against the homepage, for the focus brand only (see
    vantage_seo_run's docstring on why competitors are excluded). Real,
    costed DataForSEO calls. Runs on the background worker, not the request
    thread (2026-09-12): a full crawl + Lighthouse poll can take several
    minutes, longer than the browser's connection to the backend survives —
    every synchronous attempt was hitting ECONNRESET on the proxy in front of
    it, even though the crawl itself kept running server-side and committed
    real data regardless. The frontend polls GET /jobs/{job_id}, same as
    collection/scoring runs."""
    running = _running_seo_crawl(ctx.ws_id)
    if running:
        ctx.close()
        return {"ok": True, "job_id": running, "already": True}
    max_pages = min(max(int((body or {}).get("max_pages") or 30), 5), 100)
    job_id = f"seocrawl-{ctx.ws_id}-" + uuid.uuid4().hex[:10]
    actor = ctx.session.get("user_id")
    runner.enqueue(ctx.db.session, "seo_crawl",
                   {"ws": ctx.ws_id, "job_id": job_id, "max_pages": max_pages, "actor": actor},
                   max_attempts=1, tenant_id=ctx.ws_id)
    ctx.db.commit()
    ctx.close()
    jobs, lock = _app._jobs, _app._lock
    with lock:
        jobs[job_id] = {"state": "queued", "lines": ["queued"]}
    return {"ok": True, "job_id": job_id, "already": False}


@router.get("/vantage/seo/crawl/pages")
def vantage_seo_crawl_pages(task_id: str, check: str,
                            ctx: Ctx = Depends(guard("admin", "edit", operator=True))):
    """Real per-page drill-down for one on-page check (core/seo_crawl.py::
    pages_for_check) — fetched on demand when a "needs attention" row is
    clicked, not pre-fetched per check on every crawl (that would multiply
    the paid on_page/pages calls ~17x). Same real-cost, operator-only
    posture as running the crawl itself. A stale/expired task_id or an
    unrecognized check surfaces as an explicit error, never silently empty
    data."""
    keys = _app.keys(ctx.ws_id)
    try:
        pages = seo_crawl.pages_for_check(task_id, check, keys)
    except ValueError as e:
        ctx.close()
        raise ApiError(400, str(e)) from e
    except Exception as e:                                          # noqa: BLE001
        ctx.close()
        raise ApiError(502, f"could not fetch pages: {e}") from e
    actor, ws = ctx.session.get("user_id"), ctx.ws_id
    ctx.close()
    _app.audit(actor=actor, tenant_id=ws, action="vantage.seo_crawl_pages", target=check)
    return {"pages": pages}


@router.get("/vantage/seo/suggestions")
def vantage_seo_suggestions(ctx: Ctx = Depends(guard("reporting", "view"))):
    """The latest LLM-generated SEO recommendation set on file, if any — null
    until an admin generates one at least once."""
    payload = seo_suggestions.latest(ctx.db.session, ctx.ws_id)
    ctx.close()
    return {"suggestion": payload}


@router.post("/vantage/seo/suggestions/run")
def vantage_seo_suggestions_run(ctx: Ctx = Depends(guard("admin", "edit", operator=True))):
    """Ask an LLM (via OpenRouter) to turn the real, already-collected SEO
    facts on file into prioritized recommendations. One real, costed call —
    never scheduled. 400s if there is no SEO data on file yet to ground it in."""
    keys = _app.keys(ctx.ws_id)
    try:
        out = seo_suggestions.generate(ctx.db.session, ctx.ws_id, keys)
    except seo_suggestions.NoSeoDataError as exc:
        ctx.close()
        raise ApiError(400, str(exc))
    ctx.db.commit()
    actor, ws = ctx.session.get("user_id"), ctx.ws_id
    ctx.close()
    _app.audit(actor=actor, tenant_id=ws, action="vantage.seo_suggestions_run",
              after={"id": out["id"], "error": out["error"]})
    return {"suggestion": out}


@router.get("/vantage/evidence")
def vantage_evidence(since: str = "", limit: int = 100,
                     ctx: Ctx = Depends(guard("reporting", "view"))):
    """The raw prompt + model answer + brand hits behind the insights above."""
    rows = vantage_panel.evidence(ctx.db.session, ctx.ws_id, since=since or None,
                                  limit=min(max(limit, 1), 500))
    ctx.close()
    return {"responses": rows}
