"""Per-workspace feature flags.

One flat key namespace, three kinds:

* ``surface.<slug>`` — a listening analysis surface (its nav item + view route).
* ``module.<name>`` — a whole area: ``listening`` / ``care`` / ``reporting`` /
  ``content`` / ``vantage``. Turning a module off hides its whole nav group.
* ``cap.<name>`` — a cross-cutting capability: ``ai_assist`` (care reply
  drafting), ``surveys`` (CSAT/NPS), ``alerts_dispatch`` (outbound alert
  delivery), ``export`` (report/data download), ``report_email`` (scheduled
  report distribution).

**Everything is on by default.** A ``feature_flag`` row with ``enabled = false``
turns one key off for one workspace. Unknown keys resolve to on so a stale
reference never hard-blocks.
"""

# slug matches apps/web/lib/permissions.ts NAV_PERMS (without the leading "/")
SURFACES = (
    "overview", "mentions", "sentiment", "competitors", "reviews", "themes",
    "scam", "triage", "switch-intent", "incidents", "product-lines",
    "regulatory", "branches", "alerts", "impersonation", "posts",
)
MODULES = ("listening", "care", "reporting", "content", "vantage", "seo")
CAPABILITIES = ("ai_assist", "surveys", "alerts_dispatch", "export", "report_email")

# surfaces that belong to each module — used by the frontend to hide a whole
# group and by route guards. A surface not listed is its own thing.
MODULE_SURFACES = {
    "listening": ("overview", "mentions", "sentiment", "competitors", "reviews",
                  "themes", "scam", "triage", "switch-intent", "incidents",
                  "product-lines", "regulatory", "branches", "alerts",
                  "impersonation", "posts"),
    "care": (),
    "reporting": (),
    "content": (),
    "vantage": (),
    "seo": (),
}

_LABELS = {
    "surface.switch-intent": "Switch intent",
    "surface.product-lines": "Product lines",
    "cap.ai_assist": "AI reply drafting",
    "cap.alerts_dispatch": "Alert delivery",
    "cap.report_email": "Scheduled report email",
    "module.listening": "Listening",
    "module.care": "Social care",
    "module.reporting": "Reporting",
    "module.content": "Content calendar",
    "module.seo": "SEO",
}


def _label(key: str) -> str:
    if key in _LABELS:
        return _LABELS[key]
    return key.split(".", 1)[1].replace("-", " ").replace("_", " ").capitalize()


KEYS = tuple(
    [f"surface.{s}" for s in SURFACES]
    + [f"module.{m}" for m in MODULES]
    + [f"cap.{c}" for c in CAPABILITIES]
)
_KEYSET = frozenset(KEYS)


def catalog() -> list[dict]:
    """Every known flag: ``{key, kind, label}`` in a stable order for the UI."""
    return [{"key": k, "kind": k.split(".", 1)[0], "label": _label(k)} for k in KEYS]


def _rows(session, workspace_id) -> dict:
    from db.repositories import feature_flags
    return feature_flags.all_for_workspace(session, workspace_id)


def resolve(session, workspace_id) -> dict:
    """``{key: bool}`` for every known key, rows applied over the on-by-default."""
    rows = _rows(session, workspace_id)
    return {k: rows.get(k, True) for k in KEYS}


def enabled(session, workspace_id, key: str) -> bool:
    """Is one feature on for this workspace? Unknown keys are treated as on."""
    if key not in _KEYSET:
        return True
    return _rows(session, workspace_id).get(key, True)


def is_valid(key: str) -> bool:
    return key in _KEYSET
