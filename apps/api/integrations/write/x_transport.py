"""X (Twitter) v2 write transport for ``XWriteClient`` (§D.2 rollout).

``build_request`` is pure: ``(action, target_ref, request)`` -> ``(method, url,
payload)``. ``call`` is the one urllib round-trip. Needs an OAuth2 user-context
token (``X_WRITE_TOKEN``) with ``tweet.write`` / ``tweet.moderate.write`` /
``dm.write`` / ``block.write`` scopes.
"""
import json
import urllib.error
import urllib.request

from .base import WriteError

API = "https://api.twitter.com/2"
_TIMEOUT = 15


def _text(request) -> str:
    return (request.get("text") or request.get("message") or "").strip()


def _need(target_ref, action):
    if not target_ref:
        raise WriteError(f"x {action}: target_ref is required")
    return str(target_ref).split(":", 1)[-1]        # strip a "dm:"/"tweet:" prefix


def build_request(action, target_ref, request, *, source_user_id=None):
    request = request or {}

    if action == "publish":
        return "POST", f"{API}/tweets", {"text": _text(request)}

    if action == "reply_public":
        tid = _need(target_ref, action)
        return "POST", f"{API}/tweets", {
            "text": _text(request), "reply": {"in_reply_to_tweet_id": tid}}

    if action == "reply_dm":
        pid = _need(target_ref, action)
        return "POST", f"{API}/dm_conversations/with/{pid}/messages", {
            "text": _text(request)}

    if action == "delete_reply":
        tid = _need(target_ref, action)
        return "DELETE", f"{API}/tweets/{tid}", {}

    if action in ("block", "unblock"):
        if not source_user_id:
            raise WriteError(f"x {action}: the authenticated user id is unknown")
        target = _need(target_ref, action)
        if action == "block":
            return "POST", f"{API}/users/{source_user_id}/blocking", {
                "target_user_id": target}
        return "DELETE", f"{API}/users/{source_user_id}/blocking/{target}", {}

    raise WriteError(f"x: unsupported action {action!r}")


def _call_raw(method, url, payload, token):
    data = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            body = resp.read().decode() or "{}"
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        try:
            j = json.loads(detail)
            msg = j.get("detail") or j.get("title") or detail[:300]
        except ValueError:
            msg = detail[:300]
        raise WriteError(f"x {method} failed — {exc.code}: {msg}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise WriteError(f"x {method} failed — {exc}") from exc
    return json.loads(body) if body.strip() else {}


def resolve_me(token) -> str:
    me = _call_raw("GET", f"{API}/users/me", None, token)
    uid = (me.get("data") or {}).get("id")
    if not uid:
        raise WriteError("x: could not resolve the authenticated user id")
    return uid


def call(method, url, payload, token) -> dict:
    parsed = _call_raw(method, url, payload, token)
    data = parsed.get("data") or {}
    return {"external_id": data.get("id"),
            "response": parsed}
