"""LinkedIn write transport for ``LinkedInWriteClient``.

``build_request`` is pure; ``call`` makes the one round-trip and pulls the
created resource id from the ``x-restli-id`` / ``x-linkedin-id`` response header
(LinkedIn returns ids there, not in the body). Needs a Marketing-API token with
``w_organization_social`` and the org URN.
"""
import json
import urllib.error
import urllib.parse
import urllib.request

from .base import WriteError

REST = "https://api.linkedin.com/rest"
_TIMEOUT = 15
DEFAULT_VERSION = "202405"


def _text(request) -> str:
    return (request.get("text") or request.get("message") or "").strip()


def build_request(action, target_ref, request, *, org_urn):
    request = request or {}

    if action == "publish":
        return "POST", f"{REST}/posts", {
            "author": org_urn,
            "commentary": _text(request),
            "visibility": "PUBLIC",
            "distribution": {"feedDistribution": "MAIN_FEED",
                             "targetEntities": [],
                             "thirdPartyDistributionChannels": []},
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }

    if action == "reply_public":
        if not target_ref:
            raise WriteError("linkedin reply_public: target_ref (the post URN) is required")
        parent = urllib.parse.quote(str(target_ref), safe="")
        return "POST", f"{REST}/socialActions/{parent}/comments", {
            "actor": org_urn, "message": {"text": _text(request)}}

    if action == "delete_reply":
        if not target_ref:
            raise WriteError("linkedin delete_reply: target_ref (the post URN) is required")
        return "DELETE", f"{REST}/posts/{urllib.parse.quote(str(target_ref), safe='')}", {}

    raise WriteError(f"linkedin: unsupported action {action!r}")


def call(method, url, payload, token, version=DEFAULT_VERSION) -> dict:
    data = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "LinkedIn-Version": version,
        "X-Restli-Protocol-Version": "2.0.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            raw = resp.read().decode() or "{}"
            new_id = (resp.headers.get("x-restli-id")
                      or resp.headers.get("x-linkedin-id"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        try:
            msg = json.loads(detail).get("message", detail[:300])
        except ValueError:
            msg = detail[:300]
        raise WriteError(f"linkedin {method} failed — {exc.code}: {msg}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise WriteError(f"linkedin {method} failed — {exc}") from exc

    body = json.loads(raw) if raw.strip() else {}
    return {"external_id": new_id or body.get("id"), "response": body or {"id": new_id}}
