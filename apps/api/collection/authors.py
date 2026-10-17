"""Author identity + retention (build plan §4 / P2.4).

``author_hash`` is HMAC-SHA256(salt, "<ws>:<platform>:<key>") where ``key`` is
the platform id if the adapter gave one, else the normalised display name. It
is computed once and never changes, so a tenant can switch a source class to
``hashed`` — which nulls ``name`` and ``profile_url`` — without losing
repeat-author detection.

``rehash_workspace`` is the "single job": it applies the current
``tenant_retention_policy`` across every existing author. It only ever *removes*
PII; a policy flip back to ``full`` cannot recover names that were nulled and
so only affects authors seen afterwards.
"""
import hashlib
import hmac
import os
import re

from sqlalchemy import text

FULL = "full"
HASHED = "hashed"
_WS = re.compile(r"\s+")


def _salt() -> bytes:
    return (os.environ.get("AUTHOR_HASH_SALT")
            or "guru-ears-dev-author-salt").encode()


def _norm_name(name: str | None) -> str:
    return _WS.sub(" ", (name or "").strip().lower())


def author_hash(workspace_id: int, platform: str, *, platform_id=None, name=None) -> str:
    key = (platform_id or "").strip() or _norm_name(name)
    msg = f"{workspace_id}:{platform}:{key}".encode()
    return hmac.new(_salt(), msg, hashlib.sha256).hexdigest()


def upsert_author(session, workspace_id, *, platform, name=None, platform_id=None,
                  profile_url=None, source_class="third_party", retention_mode=FULL,
                  at) -> int | None:
    """Create/refresh the author row, honouring ``retention_mode``. Returns the
    ``item_author.id``, or ``None`` when there is no identifying information."""
    if not (name or platform_id):
        return None
    h = author_hash(workspace_id, platform, platform_id=platform_id, name=name)
    store_name = None if retention_mode == HASHED else (name or None)
    store_url = None if retention_mode == HASHED else (profile_url or None)
    row = session.execute(text("""
        INSERT INTO item_author (workspace_id, platform, platform_id, author_hash,
            name, profile_url, source_class, retention_mode, first_seen, last_seen)
        VALUES (:ws, :platform, :pid, :hash, :name, :url, :sclass, :mode, :at, :at)
        ON CONFLICT (workspace_id, author_hash) DO UPDATE SET
            last_seen = EXCLUDED.last_seen,
            platform_id = COALESCE(item_author.platform_id, EXCLUDED.platform_id),
            source_class = EXCLUDED.source_class,
            retention_mode = EXCLUDED.retention_mode,
            name = CASE WHEN EXCLUDED.retention_mode = 'hashed' THEN NULL
                        ELSE COALESCE(EXCLUDED.name, item_author.name) END,
            profile_url = CASE WHEN EXCLUDED.retention_mode = 'hashed' THEN NULL
                              ELSE COALESCE(EXCLUDED.profile_url, item_author.profile_url) END
        RETURNING id
    """), {"ws": workspace_id, "platform": platform, "pid": platform_id, "hash": h,
           "name": store_name, "url": store_url, "sclass": source_class,
           "mode": retention_mode, "at": at}).scalar_one()
    return int(row)


def rehash_workspace(session, workspace_id: int) -> dict:
    """Apply ``tenant_retention_policy`` across the workspace's authors. Returns
    ``{"hashed": n}`` — how many rows had PII removed on this pass."""
    hashed = session.execute(text("""
        UPDATE item_author a SET name = NULL, profile_url = NULL, retention_mode = 'hashed'
        FROM tenant_retention_policy p
        WHERE p.workspace_id = a.workspace_id
          AND p.source_class = a.source_class
          AND p.retention_mode = 'hashed'
          AND a.workspace_id = :ws
          AND (a.retention_mode <> 'hashed' OR a.name IS NOT NULL OR a.profile_url IS NOT NULL)
    """), {"ws": workspace_id}).rowcount
    # a class flipped back to 'full' only affects future authors
    session.execute(text("""
        UPDATE item_author a SET retention_mode = 'full'
        FROM tenant_retention_policy p
        WHERE p.workspace_id = a.workspace_id AND p.source_class = a.source_class
          AND p.retention_mode = 'full' AND a.workspace_id = :ws
          AND a.retention_mode <> 'full'
    """), {"ws": workspace_id})
    return {"hashed": hashed}
