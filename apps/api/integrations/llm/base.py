"""LLM call primitives for the Vantage AI-visibility panel.

Two routes, both plain HTTP (no SDK):

* ``call_gemini`` -- direct Google AI ``generateContent``, keyed on
  ``GOOGLE_API_KEY`` (the same key ``core/ai_assist.py`` uses for reply
  drafting). Cheaper and already configured, so it's the preferred path for
  the panel's Gemini member.
* ``call_openrouter`` -- one OpenAI-compatible endpoint that reaches everything
  else (GPT, Perplexity, Claude, Llama, ...) with a single ``OPENROUTER_API_KEY``.
  Also the fallback for Gemini if the direct call fails (quota, region, a bad
  key) -- OpenRouter proxies Gemini too.
"""
import json
import urllib.error
import urllib.request

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_TIMEOUT = 30


class LlmError(Exception):
    """A model call failed at every route tried for it."""


def call_gemini(prompt: str, *, keys: dict, model: str = "gemini-3.5-flash") -> str:
    token = (keys or {}).get("GOOGLE_API_KEY")
    if not token:
        raise LlmError("gemini: GOOGLE_API_KEY not configured")
    req = urllib.request.Request(
        GEMINI_URL.format(model=model),
        data=json.dumps({
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": 600, "temperature": 0.3},
        }).encode(),
        headers={"content-type": "application/json", "x-goog-api-key": token})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise LlmError(f"gemini direct {exc.code}: {detail[:300]}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise LlmError(f"gemini direct unreachable: {exc}") from exc

    parts = (data.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts).strip()
    if not text:
        raise LlmError(f"gemini direct: empty response ({str(data)[:200]})")
    return text


def call_openrouter(prompt: str, *, keys: dict, model: str) -> str:
    token = (keys or {}).get("OPENROUTER_API_KEY")
    if not token:
        raise LlmError("openrouter: OPENROUTER_API_KEY not configured")
    req = urllib.request.Request(
        OPENROUTER_URL,
        data=json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 600, "temperature": 0.3,
        }).encode(),
        headers={"content-type": "application/json", "Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise LlmError(f"openrouter {model} {exc.code}: {detail[:300]}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise LlmError(f"openrouter {model} unreachable: {exc}") from exc

    choices = data.get("choices") or []
    text = (choices[0].get("message", {}).get("content", "") if choices else "").strip()
    if not text:
        raise LlmError(f"openrouter {model}: empty response ({str(data)[:200]})")
    return text
