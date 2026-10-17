"""Meta Graph API request building + HTTP for ``MetaWriteClient`` (§D.2).

``build_request`` is pure and unit-tested: ``(action, target_ref, request)`` ->
``(method, url, payload)``. ``call`` is the one urllib round-trip — the only
network code — and turns a Graph response into the ``{external_id, response}``
shape the write engine records.

Facebook covers the whole verb set. Instagram covers the comment verbs
(``reply_public`` / ``reply_dm`` / ``delete_reply``); publish / schedule /
block raise for IG in this build. The FB-vs-IG signal is ``request["channel"]``
(the reply route forwards the case channel) — absent, it's Facebook.
"""
import json
import urllib.error
import urllib.parse
import urllib.request

from .base import WriteError

GRAPH = "https://graph.facebook.com/v21.0"
# The standalone "Instagram API with Instagram Login" product -- see
# core/dm_sync.py's IG_GRAPH docstring for the root-caused read-side bug this
# also fixes on the write side (persistent 500 on the unified Conversations
# API for this account). Native host, no Page-token exchange: the token is
# already scoped to the IG account.
IG_GRAPH = "https://graph.instagram.com/v21.0"
_TIMEOUT = 15


def _instagram(request) -> bool:
    return (request or {}).get("channel") == "instagram" or \
           (request or {}).get("platform") == "instagram"


def _need(target_ref, action):
    if not target_ref:
        raise WriteError(f"meta {action}: target_ref (the comment/post id) is required")
    return str(target_ref)


def build_request(action, target_ref, request, *, page_id, ig_user_id=None):
    """The Graph call for one verb: ``(method, url, payload)``. ``url`` carries
    no token — :func:`call` adds ``Authorization: Bearer``."""
    request = request or {}
    ig = _instagram(request)
    text = (request.get("text") or request.get("message") or "").strip()

    if action == "reply_public":
        obj = _need(target_ref, action)
        edge = "replies" if ig else "comments"
        return "POST", f"{GRAPH}/{obj}/{edge}", {"message": text}

    if action == "reply_dm":
        obj = _need(target_ref, action)
        channel = request.get("channel")
        if channel in {"messenger", "instagram_dm"}:
            owner = ig_user_id if channel == "instagram_dm" else page_id
            if not owner:
                raise WriteError(f"meta {action}: account id is required for {channel}")
            payload = {"recipient": {"id": obj}, "message": {"text": text}}
            if channel == "messenger":
                payload["messaging_type"] = "RESPONSE"
            return "POST", f"{GRAPH}/{owner}/messages", payload
        # a private reply to a public comment — the supported DM path for care
        return "POST", f"{GRAPH}/{obj}/private_replies", {"message": text}

    if action == "delete_reply":
        obj = _need(target_ref, action)
        mode = request.get("mode", "hide")
        if mode == "delete":
            return "DELETE", f"{GRAPH}/{obj}", {}
        if mode == "unhide":
            return "POST", f"{GRAPH}/{obj}", {"is_hidden": False}
        return "POST", f"{GRAPH}/{obj}", {"is_hidden": True}

    if ig:
        raise WriteError(f"meta {action}: not supported for instagram in this build")

    if action == "block":
        who = _need(target_ref, action)
        return "POST", f"{GRAPH}/{page_id}/blocked", {"user": who}
    if action == "unblock":
        who = _need(target_ref, action)
        return "DELETE", f"{GRAPH}/{page_id}/blocked", {"user": who}

    if action == "publish":
        payload = {"message": text}
        if request.get("link"):
            payload["link"] = request["link"]
        return "POST", f"{GRAPH}/{page_id}/feed", payload
    if action == "schedule":
        when = request.get("at") or request.get("scheduled_publish_time")
        return "POST", f"{GRAPH}/{page_id}/feed", {
            "message": text, "published": False,
            "scheduled_publish_time": _epoch(when)}

    raise WriteError(f"meta: unknown action {action!r}")


def _epoch(value):
    """Graph wants a unix timestamp for scheduled_publish_time."""
    import datetime as _dt
    if value in (None, ""):
        raise WriteError("meta schedule: 'at' timestamp is required")
    if isinstance(value, (int, float)):
        return int(value)
    try:
        dt = _dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise WriteError(f"meta schedule: bad timestamp {value!r}") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_dt.timezone.utc)
    return int(dt.timestamp())


def build_instagram_login_dm(target_ref, request, *, ig_user_id):
    """``reply_dm`` for an Instagram DM conversation via the Instagram-Login
    route: ``graph.instagram.com/{ig_user_id}/messages`` on the account's own
    Instagram User Access Token -- no Page-token exchange, unlike the
    Facebook-Login ``reply_dm`` branch above."""
    obj = _need(target_ref, "reply_dm")
    if not ig_user_id:
        raise WriteError("meta reply_dm: META_IG_USER_ID is required for instagram_dm")
    text = (request.get("text") or request.get("message") or "").strip()
    return "POST", f"{IG_GRAPH}/{ig_user_id}/messages", {
        "recipient": {"id": obj}, "message": {"text": text}}


def resolve_page_token(keys: dict) -> str:
    """Exchange the stored user token for the Page-scoped token Graph
    requires for every Page-owned write (comment replies, DM sends, block,
    publish, ...). Root-caused 2026-09-11 (Chase C-116, Hamza): a plain
    user token gets rejected outright by the Messenger/Instagram Send API
    (and is wrong for the rest of these verbs too, not just DMs) -- reads
    already resolved a page token elsewhere (core/owned_media_backfill.py,
    core/dm_sync.py._page_token), writes never did. Kept as its own copy
    here rather than importing core.dm_sync -- that module is the
    collection/read side; this is the write transport's own dependency,
    and the two shouldn't couple."""
    page_id, token = keys.get("META_PAGE_ID"), keys.get("META_ACCESS_TOKEN")
    if not (page_id and token):
        raise WriteError("meta: META_PAGE_ID / META_ACCESS_TOKEN not configured")
    req = urllib.request.Request(
        f"{GRAPH}/me/accounts?access_token={urllib.parse.quote(token)}")
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise WriteError(f"meta: could not resolve page token — {exc.code}: {detail[:400]}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise WriteError(f"meta: could not resolve page token — {exc}") from exc
    for acct in data.get("data") or []:
        if str(acct.get("id")) == str(page_id) and acct.get("access_token"):
            return acct["access_token"]
    raise WriteError(f"meta: no page-scoped token found for META_PAGE_ID={page_id}")


def call(method, url, payload, token) -> dict:
    """One Graph round-trip. Raises :class:`WriteError` on any non-2xx."""
    data = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            body = resp.read().decode() or "{}"
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        try:
            err = json.loads(detail).get("error", {})
            msg = f"{err.get('code', exc.code)}: {err.get('message', detail)[:400]}"
        except ValueError:
            msg = f"{exc.code}: {detail[:400]}"
        raise WriteError(f"meta {method} failed — {msg}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise WriteError(f"meta {method} failed — {exc}") from exc

    parsed = json.loads(body) if body.strip() else {}
    # The Messenger/Instagram Send API replies {"recipient_id", "message_id"}
    # -- neither "id" nor "post_id" -- so a DM send always came back with
    # external_id=None. Root-caused 2026-09-12 (Chase C-117): that None
    # meant dm_sync.py's poll could never recognise a just-sent DM as
    # already seen, duplicating it in the thread on the next sync.
    return {"external_id": parsed.get("id") or parsed.get("post_id") or parsed.get("message_id"),
            "response": parsed}
