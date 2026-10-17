"""``brand`` table access — the editable match-rule set per workspace."""
import json

from sqlalchemy import select

from ..models import Brand


def rows(session, workspace_id):
    """The /admin brand list: parsed pattern JSON, focus first then name."""
    result = session.execute(
        select(Brand.id, Brand.name, Brand.is_focus, Brand.safe_patterns,
               Brand.gated_patterns, Brand.context_patterns, Brand.exclude_patterns,
               Brand.active)
        .where(Brand.workspace_id == workspace_id)
        .order_by(Brand.is_focus.desc(), Brand.name)).all()
    out = []
    for bid, name, is_focus, safe, gated, context, exclude, active in result:
        out.append({
            "id": bid, "name": name, "is_focus": bool(is_focus), "active": bool(active),
            "safe_patterns": json.loads(safe or "[]"),
            "gated_patterns": json.loads(gated or "{}"),
            "context_patterns": json.loads(context or "[]"),
            "exclude_patterns": json.loads(exclude or "[]"),
        })
    return out


def focus_id_name(session, workspace_id):
    """(id, name) of the active focus brand, or None."""
    row = session.execute(
        select(Brand.id, Brand.name)
        .where(Brand.workspace_id == workspace_id, Brand.is_focus == 1, Brand.active == 1)
        .limit(1)).first()
    return tuple(row) if row else None


def competitor_names(session, workspace_id):
    """Active competitor brand names, alphabetical."""
    return [r[0] for r in session.execute(
        select(Brand.name)
        .where(Brand.workspace_id == workspace_id, Brand.is_focus == 0, Brand.active == 1)
        .order_by(Brand.name))]


def name_focus_all(session, workspace_id):
    """[(name, is_focus), …] for every active brand (no ordering guarantee)."""
    return [tuple(r) for r in session.execute(
        select(Brand.name, Brand.is_focus)
        .where(Brand.workspace_id == workspace_id, Brand.active == 1))]


def match_rules(session, workspace_id):
    """The entity-matcher's brand shape: pattern JSON parsed."""
    out = []
    for r in session.execute(
            select(Brand.id, Brand.name, Brand.is_focus, Brand.safe_patterns,
                   Brand.gated_patterns, Brand.context_patterns, Brand.exclude_patterns)
            .where(Brand.workspace_id == workspace_id, Brand.active == 1)):
        out.append({
            "id": r[0], "name": r[1], "is_focus": r[2],
            "safe": json.loads(r[3]), "gated": json.loads(r[4]),
            "context": json.loads(r[5]), "exclude": json.loads(r[6]),
        })
    return out


def active_id_name(session, workspace_id):
    """[(id, name), …] for active brands, focus first then name."""
    result = session.execute(
        select(Brand.id, Brand.name)
        .where(Brand.workspace_id == workspace_id, Brand.active == 1)
        .order_by(Brand.is_focus.desc(), Brand.name)).all()
    return [tuple(r) for r in result]


def name_focus_pairs(session, workspace_id):
    """[(name, is_focus), …] focus first."""
    result = session.execute(
        select(Brand.name, Brand.is_focus)
        .where(Brand.workspace_id == workspace_id)
        .order_by(Brand.is_focus.desc())).all()
    return [tuple(r) for r in result]


def focus_patterns(session, workspace_id):
    """(context_patterns, exclude_patterns) raw JSON strings for the focus brand, or None."""
    row = session.execute(
        select(Brand.context_patterns, Brand.exclude_patterns)
        .where(Brand.workspace_id == workspace_id, Brand.is_focus == 1)).first()
    return tuple(row) if row else None


def upsert(session, *, brand_id, workspace_id, name, is_focus, safe, gated, context,
           exclude, active):
    """Update an existing brand (by id + workspace) or insert a new one
    (no-op on the (workspace_id, name) unique conflict)."""
    values = dict(name=name, is_focus=is_focus, safe_patterns=safe, gated_patterns=gated,
                  context_patterns=context, exclude_patterns=exclude, active=active)
    if brand_id:
        session.execute(
            Brand.__table__.update()
            .where(Brand.id == int(brand_id), Brand.workspace_id == workspace_id)
            .values(**values))
        return
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    session.execute(
        pg_insert(Brand.__table__)
        .values(workspace_id=workspace_id, **values)
        .on_conflict_do_nothing())


def replace_all(session, workspace_id, brands):
    """Delete every brand for the workspace and insert `brands`
    (list of dicts: name, is_focus, safe, gated, context, exclude — JSON strings)."""
    session.execute(Brand.__table__.delete().where(Brand.workspace_id == workspace_id))
    for b in brands:
        session.add(Brand(workspace_id=workspace_id, name=b["name"], is_focus=b["is_focus"],
                          safe_patterns=b["safe"], gated_patterns=b["gated"],
                          context_patterns=b["context"], exclude_patterns=b["exclude"]))
    session.flush()


def set_context(session, workspace_id, context_json):
    session.execute(
        Brand.__table__.update().where(Brand.workspace_id == workspace_id)
        .values(context_patterns=context_json))


def set_focus_excludes(session, workspace_id, exclude_json):
    session.execute(
        Brand.__table__.update()
        .where(Brand.workspace_id == workspace_id, Brand.is_focus == 1)
        .values(exclude_patterns=exclude_json))
