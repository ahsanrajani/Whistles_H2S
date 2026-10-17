"""The AI-visibility panel roster -- a fixed set of models, each asked the
same prompt, so "AI visibility" means something (several assistants, not one).

Gemini goes direct-then-OpenRouter-fallback (see ``base.py``); every other
member has no direct key here, so it always goes through OpenRouter.
"""
from . import base, vertex

PANEL = (
    {"id": "gemini", "direct": True, "or_slug": "google/gemini-3.5-flash"},
    {"id": "gpt-4o-mini", "direct": False, "or_slug": "openai/gpt-4o-mini"},
    {"id": "perplexity-sonar", "direct": False, "or_slug": "perplexity/sonar"},
    {"id": "claude-haiku", "direct": False, "or_slug": "anthropic/claude-haiku-4.5"},
    {"id": "llama-3.1", "direct": False, "or_slug": "meta-llama/llama-3.1-8b-instruct"},
)
_BY_ID = {m["id"]: m for m in PANEL}


def ask(model_id: str, prompt: str, *, keys: dict):
    """One panel member's answer: ``(provider, model, text)``. Raises
    ``base.LlmError`` only once every route for this member has failed."""
    spec = _BY_ID.get(model_id)
    if spec is None:
        raise base.LlmError(f"unknown panel model {model_id!r}")

    if spec["direct"]:
        try:
            text = base.call_gemini(prompt, keys=keys)
            return ("vertex", vertex.model(), text) if vertex.enabled() else ("google", "gemini-3.5-flash", text)
        except base.LlmError:
            pass   # fall through to OpenRouter's copy of the same model

    text = base.call_openrouter(prompt, keys=keys, model=spec["or_slug"])
    return "openrouter", spec["or_slug"], text
