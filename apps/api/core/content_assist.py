"""AI caption + hashtag suggestions for the content calendar (Hamza: "ai
caption suggestion, ai hashtag suggestion"). Real, costed OpenRouter call,
same roster as core/seo_suggestions.py -- never auto-applied, the agent
pastes what they like into the title/body fields. Mock mode (no
OPENROUTER_API_KEY/GOOGLE_API_KEY) returns a deterministic canned suggestion
so the flow and its tests work offline.
"""
from db.repositories import brands as brands_repo
from integrations.llm import panel

MODEL_ID = "claude-haiku"


class ContentAssistError(Exception):
    pass


def _focus_name(session, workspace_id: int) -> str | None:
    focus = next((b for b in brands_repo.match_rules(session, workspace_id)
                 if b.get("is_focus")), None)
    return focus["name"] if focus else None


def _mock(topic: str, draft: str, channel: str, brand: str | None) -> tuple[str, list[str]]:
    base = (draft or topic or "our latest update").strip()
    who = brand or "us"
    caption = (f"{base[:160]}{'…' if len(base) > 160 else ''} "
              f"Learn more or reach out to {who} today.")
    hashtags = [f"#{(brand or 'OurBrand').replace(' ', '')}", "#Pakistan", "#Investing"]
    if channel:
        hashtags.append(f"#{channel.capitalize()}")
    return caption, hashtags


def _parse(text: str) -> tuple[str, list[str]]:
    lines = text.strip().splitlines()
    idx = next((i for i, ln in enumerate(lines)
               if ln.strip().upper().startswith("HASHTAGS:")), None)
    if idx is None:
        return text.strip(), []
    caption = "\n".join(lines[:idx]).strip()
    tail = lines[idx].split(":", 1)[1] if ":" in lines[idx] else ""
    hashtags = [t for t in tail.replace(",", " ").split() if t.startswith("#")]
    return caption, hashtags


def suggest(session, workspace_id: int, *, topic: str = "", draft: str = "",
           channel: str = "", keys: dict | None = None) -> dict:
    keys = keys or {}
    if not (topic or draft):
        raise ContentAssistError("topic or draft is required")
    brand = _focus_name(session, workspace_id)

    if not keys.get("OPENROUTER_API_KEY") and not keys.get("GOOGLE_API_KEY"):
        caption, hashtags = _mock(topic, draft, channel, brand)
        return {"caption": caption, "hashtags": hashtags, "mock": True}

    prompt = "\n".join([
        f"You are a social media copywriter for {brand or 'a financial brokerage in Pakistan'}.",
        f"Write a short, engaging {channel or 'social media'} caption"
        + (f" about: {topic}." if topic else "")
        + (f" Polish this draft: {draft}." if draft else ""),
        "Then on a new line starting with exactly \"HASHTAGS:\", give 5-8 relevant "
        "hashtags space-separated, each starting with #.",
        "No markdown, no preamble, no quotation marks around the caption.",
    ])
    try:
        _provider, _model, text = panel.ask(MODEL_ID, prompt, keys=keys)
    except Exception as exc:                                          # noqa: BLE001
        raise ContentAssistError(str(exc)) from exc

    caption, hashtags = _parse(text)
    return {"caption": caption, "hashtags": hashtags, "mock": False}
