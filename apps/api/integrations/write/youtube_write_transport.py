"""YouTube Data API v3 write transport for ``YouTubeWriteClient``.

``build_request`` is pure; ``call`` is the one round-trip. Needs an OAuth2 token
with the ``youtube.force-ssl`` scope (``YOUTUBE_OAUTH_TOKEN``).
"""
import json
import urllib.error
import urllib.parse
import urllib.request

from .base import WriteError

API = "https://www.googleapis.com/youtube/v3"
_TIMEOUT = 15


def _text(request) -> str:
    return (request.get("text") or request.get("message") or "").strip()


def build_request(action, target_ref, request):
    request = request or {}

    if action == "reply_public":
        if not target_ref:
            raise WriteError("youtube reply_public: target_ref (the parent comment id) is required")
        return "POST", f"{API}/comments?part=snippet", {
            "snippet": {"parentId": str(target_ref), "textOriginal": _text(request)}}

    if action == "publish":
        video_id = request.get("video_id") or target_ref
        if not video_id:
            raise WriteError("youtube publish: a video_id is required")
        return "POST", f"{API}/commentThreads?part=snippet", {
            "snippet": {"videoId": str(video_id),
                        "topLevelComment": {"snippet": {"textOriginal": _text(request)}}}}

    if action == "delete_reply":
        if not target_ref:
            raise WriteError("youtube delete_reply: target_ref (the comment id) is required")
        return "DELETE", f"{API}/comments?id={urllib.parse.quote(str(target_ref))}", {}

    raise WriteError(f"youtube: unsupported action {action!r}")


def call(method, url, payload, token) -> dict:
    data = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            raw = resp.read().decode() or "{}"
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        try:
            err = json.loads(detail).get("error", {})
            msg = err.get("message", detail[:300])
        except ValueError:
            msg = detail[:300]
        raise WriteError(f"youtube {method} failed — {exc.code}: {msg}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise WriteError(f"youtube {method} failed — {exc}") from exc

    body = json.loads(raw) if raw.strip() else {}
    ext = body.get("id")
    if not ext and isinstance(body.get("snippet"), dict):     # commentThreads
        ext = body["snippet"].get("topLevelComment", {}).get("id")
    return {"external_id": ext, "response": body}
