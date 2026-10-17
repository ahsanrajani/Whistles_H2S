"""Knowledge base + template library (build plan §5 / P3.6).

Articles: CRUD + full-text search + attachment metadata (``templates:view`` to
read, ``templates:edit`` to write). Templates: a role-restricted library —
``templates:create`` / ``:edit`` / ``:delete`` gate each mutation, so an agent
(who holds only ``templates:view``) cannot create one via the API.
"""
from fastapi import APIRouter, Body, Depends
from sqlalchemy import text

from core import care_audit

from .deps import ApiError, Ctx, guard

router = APIRouter(prefix="/api/v1", tags=["knowledge"])


# --- knowledge base --------------------------------------------------
@router.get("/kb/articles")
def list_articles(q: str = "", limit: int = 50, drafts: bool = False,
                  ctx: Ctx = Depends(guard("templates", "view"))):
    params = {"ws": ctx.ws_id, "lim": min(limit, 200)}
    where = "workspace_id = :ws"
    if not drafts:
        where += " AND published"
    if q.strip():
        where += (" AND to_tsvector('english', title || ' ' || body || ' ' || tags) "
                  "@@ plainto_tsquery('english', :q)")
        params["q"] = q.strip()
    rows = ctx.db.session.execute(text(f"""
        SELECT id, title, tags, published, created_by, updated_at,
               (SELECT count(*) FROM kb_attachment a WHERE a.article_id = kb_article.id) AS attachments
        FROM kb_article WHERE {where} ORDER BY updated_at DESC LIMIT :lim
    """), params).mappings().all()
    ctx.close()
    return {"articles": [dict(r) for r in rows]}


@router.get("/kb/articles/{article_id}")
def get_article(article_id: int, ctx: Ctx = Depends(guard("templates", "view"))):
    s = ctx.db.session
    art = s.execute(text(
        "SELECT * FROM kb_article WHERE id = :i AND workspace_id = :ws"),
        {"i": article_id, "ws": ctx.ws_id}).mappings().first()
    if not art:
        ctx.close()
        raise ApiError(404, "article not found")
    atts = [dict(a) for a in s.execute(text(
        "SELECT id, filename, url, created_at FROM kb_attachment "
        "WHERE article_id = :i ORDER BY id"), {"i": article_id}).mappings().all()]
    ctx.close()
    return {"article": dict(art), "attachments": atts}


@router.post("/kb/articles")
def create_article(body: dict | None = Body(default=None),
                   ctx: Ctx = Depends(guard("templates", "edit"))):
    b = body or {}
    if not (b.get("title") or "").strip():
        ctx.close()
        raise ApiError(400, "title is required")
    aid = ctx.db.session.execute(text("""
        INSERT INTO kb_article (workspace_id, title, body, tags, published, created_by)
        VALUES (:ws, :t, :b, :tags, :pub, :by) RETURNING id
    """), {"ws": ctx.ws_id, "t": b["title"].strip(), "b": b.get("body") or "",
           "tags": b.get("tags") or "", "pub": bool(b.get("published", True)),
           "by": ctx.session.get("user_id")}).scalar_one()
    ctx.db.commit()
    actor, ws = ctx.session.get("user_id"), ctx.ws_id
    ctx.close()
    care_audit.emit("care.template_change", actor=actor, ws=ws, target=aid,
                    after={"entity": "kb_article", "op": "create"})
    return {"ok": True, "id": aid}


@router.put("/kb/articles/{article_id}")
def update_article(article_id: int, body: dict | None = Body(default=None),
                   ctx: Ctx = Depends(guard("templates", "edit"))):
    b = body or {}
    n = ctx.db.session.execute(text("""
        UPDATE kb_article SET
            title = COALESCE(:t, title), body = COALESCE(:b, body),
            tags = COALESCE(:tags, tags), published = COALESCE(:pub, published),
            updated_at = now()
        WHERE id = :i AND workspace_id = :ws
    """), {"i": article_id, "ws": ctx.ws_id, "t": b.get("title"),
           "b": b.get("body"), "tags": b.get("tags"),
           "pub": b.get("published")}).rowcount
    ctx.db.commit()
    actor, ws = ctx.session.get("user_id"), ctx.ws_id
    ctx.close()
    if not n:
        raise ApiError(404, "article not found")
    care_audit.emit("care.template_change", actor=actor, ws=ws, target=article_id,
                    after={"entity": "kb_article", "op": "update"})
    return {"ok": True}


@router.delete("/kb/articles/{article_id}")
def delete_article(article_id: int, ctx: Ctx = Depends(guard("templates", "delete"))):
    n = ctx.db.session.execute(text(
        "DELETE FROM kb_article WHERE id = :i AND workspace_id = :ws"),
        {"i": article_id, "ws": ctx.ws_id}).rowcount
    ctx.db.commit()
    actor, ws = ctx.session.get("user_id"), ctx.ws_id
    ctx.close()
    if not n:
        raise ApiError(404, "article not found")
    care_audit.emit("care.template_change", actor=actor, ws=ws, target=article_id,
                    after={"entity": "kb_article", "op": "delete"})
    return {"ok": True}


@router.post("/kb/articles/{article_id}/attachments")
def add_attachment(article_id: int, body: dict | None = Body(default=None),
                   ctx: Ctx = Depends(guard("templates", "edit"))):
    b = body or {}
    if not b.get("filename") or not b.get("url"):
        ctx.close()
        raise ApiError(400, "filename and url are required")
    owned = ctx.db.session.execute(text(
        "SELECT 1 FROM kb_article WHERE id = :i AND workspace_id = :ws"),
        {"i": article_id, "ws": ctx.ws_id}).first()
    if not owned:
        ctx.close()
        raise ApiError(404, "article not found")
    aid = ctx.db.session.execute(text(
        "INSERT INTO kb_attachment (article_id, filename, url) "
        "VALUES (:a, :f, :u) RETURNING id"),
        {"a": article_id, "f": b["filename"], "u": b["url"]}).scalar_one()
    ctx.db.commit()
    actor, ws = ctx.session.get("user_id"), ctx.ws_id
    ctx.close()
    care_audit.emit("care.template_change", actor=actor, ws=ws, target=article_id,
                    after={"entity": "kb_attachment", "op": "create", "id": aid})
    return {"ok": True, "id": aid}


# --- templates -----------------------------------------------------
@router.get("/templates")
def list_templates(category: str = "", ctx: Ctx = Depends(guard("templates", "view"))):
    params = {"ws": ctx.ws_id}
    where = "workspace_id = :ws"
    if category:
        where += " AND category = :cat"
        params["cat"] = category
    rows = ctx.db.session.execute(text(
        f"SELECT id, name, category, body, updated_at FROM care_template "
        f"WHERE {where} ORDER BY category, name"), params).mappings().all()
    ctx.close()
    return {"templates": [dict(r) for r in rows]}


@router.post("/templates")
def create_template(body: dict | None = Body(default=None),
                    ctx: Ctx = Depends(guard("templates", "create"))):
    b = body or {}
    if not (b.get("name") or "").strip() or not (b.get("body") or "").strip():
        ctx.close()
        raise ApiError(400, "name and body are required")
    tid = ctx.db.session.execute(text("""
        INSERT INTO care_template (workspace_id, name, category, body, created_by)
        VALUES (:ws, :n, :c, :b, :by) RETURNING id
    """), {"ws": ctx.ws_id, "n": b["name"].strip(), "c": b.get("category") or "general",
           "b": b["body"], "by": ctx.session.get("user_id")}).scalar_one()
    ctx.db.commit()
    actor, ws = ctx.session.get("user_id"), ctx.ws_id
    ctx.close()
    care_audit.emit("care.template_change", actor=actor, ws=ws, target=tid,
                    after={"entity": "care_template", "op": "create",
                           "name": b["name"].strip()})
    return {"ok": True, "id": tid}


@router.put("/templates/{template_id}")
def update_template(template_id: int, body: dict | None = Body(default=None),
                    ctx: Ctx = Depends(guard("templates", "edit"))):
    b = body or {}
    n = ctx.db.session.execute(text("""
        UPDATE care_template SET
            name = COALESCE(:n, name), category = COALESCE(:c, category),
            body = COALESCE(:b, body), updated_at = now()
        WHERE id = :i AND workspace_id = :ws
    """), {"i": template_id, "ws": ctx.ws_id, "n": b.get("name"),
           "c": b.get("category"), "b": b.get("body")}).rowcount
    ctx.db.commit()
    actor, ws = ctx.session.get("user_id"), ctx.ws_id
    ctx.close()
    if not n:
        raise ApiError(404, "template not found")
    care_audit.emit("care.template_change", actor=actor, ws=ws, target=template_id,
                    after={"entity": "care_template", "op": "update"})
    return {"ok": True}


@router.delete("/templates/{template_id}")
def delete_template(template_id: int, ctx: Ctx = Depends(guard("templates", "delete"))):
    n = ctx.db.session.execute(text(
        "DELETE FROM care_template WHERE id = :i AND workspace_id = :ws"),
        {"i": template_id, "ws": ctx.ws_id}).rowcount
    ctx.db.commit()
    actor, ws = ctx.session.get("user_id"), ctx.ws_id
    ctx.close()
    if not n:
        raise ApiError(404, "template not found")
    care_audit.emit("care.template_change", actor=actor, ws=ws, target=template_id,
                    after={"entity": "care_template", "op": "delete"})
    return {"ok": True}
