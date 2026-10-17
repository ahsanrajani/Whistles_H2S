"""Repository layer — session-scoped data access for the CRUD-shaped tables.

Each function takes a SQLAlchemy ``Session`` and returns plain values / tuples /
dicts (not ORM entities) so callers stay decoupled from the mapping. The
analytical aggregation queries live in ``db/analytics/`` instead.
"""
from . import (agent_activity, ai_suggestion_cache, audit, brands, feature_flags,
               gold, identity, keys, llm_panel, mentions, metric_fact, outbound,
               projects, rbac, retention, runs, scheduled_task, seo_suggestion,
               source_state, users, workspaces)

__all__ = ["users", "workspaces", "brands", "keys", "runs", "gold", "mentions",
           "audit", "identity", "metric_fact", "outbound", "projects", "rbac",
           "retention", "scheduled_task", "source_state", "agent_activity",
           "feature_flags", "llm_panel", "seo_suggestion", "ai_suggestion_cache"]
