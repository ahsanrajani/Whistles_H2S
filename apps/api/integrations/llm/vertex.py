"""Gemini on Vertex AI, authenticated as the Cloud Run service account (no API key).

Enabled with ``GURU_LLM=vertex``. Project comes from ``GOOGLE_CLOUD_PROJECT`` (else the metadata server),
region from ``VERTEX_LOCATION`` (default ``global``), model from ``VERTEX_MODEL``. Plain HTTP like the other
routes in this package, so there is no SDK to install.

When enabled, ``app.keys()`` reports ``GOOGLE_API_KEY`` as the sentinel ``vertex`` so every feature that asks
"is a model configured?" answers yes; the call sites check ``enabled()`` before using the sentinel as a key.
"""
import json
import os
import threading
import time
import urllib.error
import urllib.request

SENTINEL = "vertex"
_METADATA = "http://metadata.google.internal/computeMetadata/v1/"
_TIMEOUT = 30
_token = {"value": None, "expires": 0.0}
_lock = threading.Lock()


class VertexError(Exception):
    """The Vertex call failed (auth, quota, region, model name)."""


def enabled() -> bool:
    return os.environ.get("GURU_LLM", "").strip().lower() == "vertex"


def model(default: str = "gemini-2.5-flash") -> str:
    return os.environ.get("VERTEX_MODEL") or default


def _metadata(path: str) -> str:
    req = urllib.request.Request(_METADATA + path, headers={"Metadata-Flavor": "Google"})
    with urllib.request.urlopen(req, timeout=3) as r:
        return r.read().decode()


def _access_token() -> str:
    with _lock:
        if _token["value"] and time.time() < _token["expires"] - 60:
            return _token["value"]
        try:
            data = json.loads(_metadata("instance/service-accounts/default/token"))
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise VertexError(f"vertex: no service-account token ({exc})") from exc
        _token.update(value=data["access_token"], expires=time.time() + int(data.get("expires_in", 300)))
        return _token["value"]


def _project() -> str:
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if project:
        return project
    try:
        return _metadata("project/project-id")
    except (urllib.error.URLError, OSError) as exc:
        raise VertexError(f"vertex: project id unknown ({exc})") from exc


def _url(model_name: str) -> str:
    loc = os.environ.get("VERTEX_LOCATION", "global")
    host = "aiplatform.googleapis.com" if loc == "global" else f"{loc}-aiplatform.googleapis.com"
    return (f"https://{host}/v1/projects/{_project()}/locations/{loc}"
            f"/publishers/google/models/{model_name}:generateContent")


def generate(prompt: str, *, system: str | None = None, max_tokens: int = 1024,
             temperature: float = 0.3, model_name: str | None = None) -> str:
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature},
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    req = urllib.request.Request(
        _url(model_name or model()), data=json.dumps(body).encode(),
        headers={"content-type": "application/json", "Authorization": f"Bearer {_access_token()}"})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as exc:
        raise VertexError(f"vertex {exc.code}: {exc.read().decode(errors='replace')[:300]}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise VertexError(f"vertex unreachable: {exc}") from exc
    parts = (data.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts).strip()
    if not text:
        raise VertexError(f"vertex: empty response ({str(data)[:200]})")
    return text
