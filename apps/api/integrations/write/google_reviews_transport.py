"""Google Business Profile review-reply transport for ``GoogleReviewsWriteClient``.

``build_request`` is pure; ``call`` is the one round-trip. ``target_ref`` is the
full review resource name
(``accounts/{a}/locations/{l}/reviews/{id}``). A 400 from the API is treated as
``WriteRejected`` so it surfaces as a rework, matching how Google can bounce a
reply for policy after it is submitted. Needs an OAuth2 token for the Business
Profile API (``GOOGLE_BUSINESS_TOKEN``).
"""
import json
import urllib.error
import urllib.request

from .base import WriteError, WriteRejected

API = "https://mybusiness.googleapis.com/v4"
_TIMEOUT = 15


def build_request(action, target_ref, request):
    request = request or {}
    if not target_ref:
        raise WriteError(f"google_reviews {action}: target_ref (the review name) is required")
    name = str(target_ref).strip("/")

    if action == "reply_public":
        text = (request.get("text") or request.get("message") or "").strip()
        return "PUT", f"{API}/{name}/reply", {"comment": text}
    if action == "delete_reply":
        return "DELETE", f"{API}/{name}/reply", {}
    raise WriteError(f"google_reviews: unsupported action {action!r}")


def call(method, url, payload, token, *, review_name=None) -> dict:
    data = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            raw = resp.read().decode() or "{}"
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        try:
            msg = json.loads(detail).get("error", {}).get("message", detail[:300])
        except ValueError:
            msg = detail[:300]
        if exc.code == 400:
            raise WriteRejected(f"google_reviews rejected — {msg}") from exc
        raise WriteError(f"google_reviews {method} failed — {exc.code}: {msg}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise WriteError(f"google_reviews {method} failed — {exc}") from exc

    body = json.loads(raw) if raw.strip() else {}
    return {"external_id": review_name, "response": body}
