"""The guided 5-step onboarding wizard. FastAPI port of
api/v1/routers/onboarding.py — gated by the ``admin`` permission."""
import json
import re
import uuid

from fastapi import APIRouter, Body, Depends, Request

import app as _app
from core import entity, sources
from db import repositories as repo
from db.analytics import dashboards as dq
from jobs import runner

from .deps import ApiError, Ctx, guard, update_session

router = APIRouter(prefix="/api/v1", tags=["onboarding"])


def _unregex(pattern):
    text = re.sub(r"\\[sb]\+?", " ", pattern or "")
    text = re.sub(r"\\(.)", r"\1", text)
    return text.strip()


def _wizard_workspace(connection, session):
    ws_id = session.get("ws_id")
    if not ws_id:
        return None
    return repo.workspaces.wizard_row(connection.session, ws_id)


@router.get("/onboarding/state")
def onboarding_state(ctx: Ctx = Depends(guard("admin", "view", operator=True))):
    connection = ctx.db
    workspace = _wizard_workspace(connection, ctx.session)
    safe_sources = [
        {"id": sid, "label": meta["label"], "surface": meta["surface"],
         "needs": meta["needs"]}
        for sid, meta in sources.SOURCES.items() if meta.get("client_safe")]
    payload = {
        "step": workspace[5] if workspace else 1,
        "workspace": ({"id": workspace[0], "name": workspace[1], "market": workspace[2],
                       "volume_scenario": workspace[3], "sentiment_langs": workspace[4]}
                      if workspace else None),
        "steps": ["Workspace", "Brands", "Listening query", "Connect sources", "Review"],
        "key_labels": [{"var": var, "label": label} for var, label in sources.KEYS],
        "sources": {
            "auto": [source for source in safe_sources if not source["needs"]],
            "connect": [source for source in safe_sources if source["needs"]],
        },
    }
    if workspace:
        ws_id = workspace[0]
        brand_rows = repo.brands.name_focus_pairs(connection.session, ws_id)
        focus_row = repo.brands.focus_patterns(connection.session, ws_id)
        context = json.loads(focus_row[0] or "[]") if focus_row and focus_row[0] else \
            list(_app.STARTER_CONTEXT)
        excludes = json.loads(focus_row[1] or "[]") if focus_row and focus_row[1] else []
        have = repo.keys.configured_vars(connection.session, ws_id)
        payload.update({
            "brands": {"focus": next((name for name, is_focus in brand_rows if is_focus), ""),
                       "competitors": [name for name, is_focus in brand_rows if not is_focus]},
            "query": {"context_text": "\n".join(_unregex(term) for term in context),
                      "exclude_text": "\n".join(f"{_unregex(pair[0])} — {pair[1]}" for pair in excludes)},
            "connected": sorted(have),
        })
    ctx.close()
    return payload


@router.get("/onboarding/preview")
def onboarding_preview(name: str = "", ctx: Ctx = Depends(guard("admin", "view"))):
    """Sample corpus matches for the rules ``brand_patterns()`` would generate."""
    name = (name or "").strip()
    connection, workspace_id = ctx.db, ctx.ws_id
    if not name:
        ctx.close()
        return {"name": name, "match_count": 0, "sample_size": 0, "matched": []}
    generated = _app.brand_patterns(name)
    brand = {"id": 0, "name": name, "safe": generated["safe"], "gated": generated["gated"],
             "context": generated["context"], "exclude": generated["exclude"]}
    rows = dq.preview_items(connection.session, workspace_id, 4000)
    matched, match_count = [], 0
    for iid, title, item_body, outlet, surface in rows:
        text = " ".join(filter(None, [title, item_body]))
        if not entity.classify(text, [brand]):
            continue
        match_count += 1
        if len(matched) < 12:
            matched.append({"id": iid, "text": text.strip().replace("\n", " ")[:200],
                            "outlet": outlet, "surface": surface})
    ctx.close()
    return {"name": name, "safe_patterns": generated["safe"],
            "match_count": match_count, "sample_size": len(rows), "matched": matched}


@router.patch("/onboarding/{step}")
def onboarding_step(step: int, request: Request,
                    body: dict | None = Body(default=None),
                    ctx: Ctx = Depends(guard("admin", "edit", operator=True))):
    body = body or {}
    connection = ctx.db
    s = connection.session
    if step == 1:
        name = (body.get("name") or "").strip()
        if not name:
            ctx.close()
            raise ApiError(400, "Give the workspace a name.")
        existing_id = repo.workspaces.id_by_name(s, name)
        if existing_id and existing_id != ctx.session.get("ws_id"):
            ctx.close()
            raise ApiError(409, "A workspace with that name already exists.")
        if existing_id:
            repo.workspaces.update_settings(
                s, existing_id, market=body.get("market", "PK"),
                volume_scenario=body.get("volume_scenario", "mid"),
                sentiment_langs=body.get("sentiment_langs", "en"))
            ws_id = existing_id
        else:
            ws_id = repo.workspaces.create(
                s, name=name, slug=_app.slugify(name, connection),
                market=body.get("market", "PK"),
                volume_scenario=body.get("volume_scenario", "mid"),
                sentiment_langs=body.get("sentiment_langs", "en"),
                onboarding_step=2, created_at=_app.now())
        repo.workspaces.bump_onboarding_step(s, ws_id, 2)
        connection.commit()
        ctx.close()
        update_session(request, ws_id=ws_id)
        return {"ok": True, "ws_id": ws_id, "step": 2}

    workspace = _wizard_workspace(connection, ctx.session)
    if not workspace:
        ctx.close()
        raise ApiError(409, "Start at step 1.")
    ws_id = workspace[0]

    if step == 2:
        focus = (body.get("focus") or "").strip()
        competitors = [name.strip() for name in (body.get("competitors") or []) if name.strip()]
        if not focus:
            ctx.close()
            raise ApiError(400, "Name the focus brand.")
        new_brands = []
        for name, is_focus in [(focus, 1)] + [(name, 0) for name in competitors[:5]]:
            p = _app.brand_patterns(name)
            new_brands.append({
                "name": name, "is_focus": is_focus,
                "safe": json.dumps(p["safe"]), "gated": json.dumps(p["gated"]),
                "context": json.dumps(p["context"]), "exclude": json.dumps(p["exclude"]),
            })
        repo.brands.replace_all(s, ws_id, new_brands)
        repo.workspaces.bump_onboarding_step(s, ws_id, 3)
    elif step == 3:
        terms = [line.strip() for line in (body.get("context_text") or "").splitlines()
                 if line.strip()]
        context = [term if term.startswith("\\b") else _app.phrase_regex(term)
                   for term in terms if term]
        excludes = []
        for line in (body.get("exclude_text") or "").splitlines():
            line = line.strip()
            if not line:
                continue
            term, _, reason = line.partition("—")
            if not reason:
                term, _, reason = line.partition(" - ")
            pattern = _app.phrase_regex(term)
            if pattern:
                excludes.append([pattern, reason.strip() or "excluded"])
        repo.brands.set_context(s, ws_id, json.dumps(context))
        repo.brands.set_focus_excludes(s, ws_id, json.dumps(excludes))
        repo.workspaces.bump_onboarding_step(s, ws_id, 4)
    elif step == 4:
        for var, _label in sources.KEYS:
            value = (body.get(var) or "").strip()
            if value:
                _app.persist_key(ws_id, var, value)
        repo.workspaces.bump_onboarding_step(s, ws_id, 5)
    elif step == 5:
        repo.workspaces.set_onboarding_step(s, ws_id, 0)
        from collection import schedule as _sched
        _sched.ensure_workspace_tick(s, ws_id)          # P2.7: per-source collection tick
        connection.commit()
        job_id = None
        if body.get("run_now") and not repo.runs.running_id(s, ws_id):
            job_id = uuid.uuid4().hex[:12]
            repo.runs.create(s, run_id=job_id, workspace_id=ws_id,
                             started_at=_app.now())
            runner.enqueue(s, "collection", {"ws": ws_id, "run_id": job_id},
                           max_attempts=1, tenant_id=ws_id)
            connection.commit()
        ctx.close()
        if job_id:
            jobs, lock = _app._jobs, _app._lock
            with lock:
                jobs[job_id] = {"state": "queued", "lines": ["queued"]}
        return {"ok": True, "step": 0, "job_id": job_id}
    else:
        ctx.close()
        raise ApiError(404, "Unknown step")

    connection.commit()
    ctx.close()
    return {"ok": True, "step": step + 1}
