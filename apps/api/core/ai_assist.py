"""AI reply assistance (build plan §5 / P3.7).

Given a case, draft a reply (or polish a draft for grammar / tone / brand
voice) grounded in the case thread and the most relevant knowledge-base
articles. **Nothing is sent** — the caller gets text back and the agent must
explicitly use it in the reply box.

Mock mode (no ``GOOGLE_API_KEY``) returns a deterministic canned suggestion
so the flow and its tests work offline. ``call_model`` is the injectable seam;
the default implementation calls Google AI (Gemini) ``generateContent``.

A "reply" suggestion with no draft (the console auto-loads one the moment an
agent opens a case) is cached per case in ``ai_suggestion_cache``, keyed by a
cheap thread fingerprint -- reopening the same conversation, or another agent
opening it, doesn't cost a second real model call unless a new message
actually landed since. grammar/tone/brand_voice and any "reply" call made
*with* a draft (the agent explicitly asked, against their own typed text)
always go straight to the model.
"""
import re

from sqlalchemy import text

from db.repositories import ai_suggestion_cache as cache_repo
from db.repositories import brands as brands_repo

KINDS = ("reply", "grammar", "tone", "brand_voice")
_MAX_KB = 3


def _focus_brand_name(session, workspace_id) -> str | None:
    focus = next((b for b in brands_repo.match_rules(session, workspace_id)
                 if b.get("is_focus")), None)
    return focus["name"] if focus else None


def _system_prompt(kind: str, brand: str | None, first_contact: bool = True) -> str:
    who = brand or "the brand"
    # Hamza (live screenshot, C-117): "says thank you for messaging xxx again
    # and again, should do so for the first message" -- the old prompt's own
    # "e.g. Thank you for contacting X" example got used as an opener on
    # every reply regardless of thread state, even though the full
    # conversation is already in the prompt. Telling the model explicitly
    # whether this is truly the first contact (no outbound message in the
    # thread yet) or an ongoing exchange fixes it at the source rather than
    # hoping the model infers it from the transcript alone.
    greeting = (
        f"This is the customer's first message in the conversation -- you may open "
        f'with a brief greeting (e.g. "Thank you for contacting {who}").'
        if first_contact else
        f"{who} has already replied in this conversation at least once -- do NOT "
        f"greet them or thank them for contacting {who} again. Respond directly to "
        f"what they just said, as a natural continuation of the exchange."
    )
    return {
        "reply": f"You are a customer-care agent for {who}. Draft a concise, "
                f"empathetic public reply grounded in the conversation so far and the "
                f"knowledge-base excerpts. {greeting} Never invent policy.",
        "grammar": "Fix only spelling, grammar and punctuation in the draft. Keep the "
                  "meaning and tone unchanged.",
        "tone": "Rewrite the draft to be warmer and calmer without changing the facts.",
        "brand_voice": f"Rewrite the draft in a professional, reassuring voice for "
                       f"{who}. Keep it short.",
    }[kind]


_SENTENCE_END = re.compile(r'[.!?](?:["\')”]?)(?:\s|$)')


def _trim_incomplete_tail(text: str) -> str:
    """A reply cut off mid-sentence (hit maxOutputTokens, or any other real
    truncation) reads worse than a shorter, complete one -- found live: a
    real cached suggestion ended mid-word. Trim back to the last sentence
    boundary if the text doesn't already end on one; leave it alone if no
    boundary exists at all rather than blank a short reply out."""
    text = text.strip()
    if not text or text[-1] in ".!?”’)\"'":
        return text
    matches = list(_SENTENCE_END.finditer(text))
    return text[:matches[-1].end()].strip() if matches else text


def _thread(session, case_id):
    rows = session.execute(text(
        "SELECT direction, body FROM case_message WHERE case_id = :c "
        "ORDER BY sent_at, id"), {"c": case_id}).all()
    return [(d, b) for d, b in rows]


def _fingerprint(session, case_id) -> str:
    """A count + max(id) pair over case_message -- changes if and only if a
    message has been added since, cheap enough to compute on every read."""
    row = session.execute(text(
        "SELECT count(*), coalesce(max(id), 0) FROM case_message WHERE case_id = :c"),
        {"c": case_id}).first()
    return f"{row[0]}:{row[1]}"


def _kb_context(session, workspace_id, query):
    if not (query or "").strip():
        return []
    rows = session.execute(text("""
        SELECT id, title, left(body, 600) AS excerpt FROM kb_article
        WHERE workspace_id = :ws
          AND to_tsvector('english', title || ' ' || body || ' ' || tags)
              @@ plainto_tsquery('english', :q)
        LIMIT :lim
    """), {"ws": workspace_id, "q": query, "lim": _MAX_KB}).mappings().all()
    return [dict(r) for r in rows]


def _mock_suggestion(kind, thread, draft, kb, brand: str | None, first_contact: bool = True):
    if kind == "reply":
        if first_contact:
            opener = (f"Thank you for contacting {brand} — I'm sorry for the trouble. "
                     if brand else "Thanks for reaching out — I'm sorry for the trouble. ")
        else:
            opener = ""
        ref = f" (see: {kb[0]['title']})" if kb else ""
        last_in = next((b for d, b in reversed(thread) if d == "inbound"), "")
        return (opener + "Here's what we can do about "
                + (last_in[:60].strip() or "your issue") + ": our team is on it "
                "and will update you shortly." + ref)
    base = draft or (thread[-1][1] if thread else "")
    return {"grammar": base.strip().capitalize(),
            "tone": "I completely understand — " + base.strip().lower(),
            "brand_voice": (f"At {brand}, we" if brand else "We")
                          + " take this seriously. " + base.strip()
            }[kind]


def _call_gemini_direct(system, prompt, *, keys):     # pragma: no cover - network
    from integrations.llm import vertex
    if vertex.enabled():                      # service-account auth, no key
        return vertex.generate(prompt, system=system, max_tokens=1024, temperature=0.4)
    import json
    import urllib.request
    model = keys.get("GEMINI_MODEL", "gemini-3.5-flash")
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=json.dumps({
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            # 400 cut a real reply off mid-sentence live -- Gemini 3.5's
            # "thinking" tokens count against this budget too, so a short
            # visible reply can still need real headroom. _trim_incomplete_
            # tail() is the second line of defense if it still happens.
            "generationConfig": {"maxOutputTokens": 1024, "temperature": 0.4},
        }).encode(),
        headers={"content-type": "application/json",
                 "x-goog-api-key": keys["GOOGLE_API_KEY"]})
    # 8s was too tight a margin for a real generative call -- a "reply"
    # suggestion (KB context injected into the prompt) genuinely timed out
    # here for a real case, surfacing as a bare, unhelpful request failure.
    with urllib.request.urlopen(req, timeout=25) as r:
        data = json.loads(r.read())
    parts = ((data.get("candidates") or [{}])[0]
             .get("content", {}).get("parts", []))
    text = "".join(p.get("text", "") for p in parts)
    if not text:
        raise RuntimeError(f"empty response ({str(data)[:200]})")
    return text


def _default_call_model(system, prompt, *, keys):     # pragma: no cover - network
    """Direct Gemini, falling back to its OpenRouter copy on any failure --
    same posture as integrations/llm/panel.py's roster. Found live: a real
    case hit a genuine Gemini 503, and this path had no fallback at all."""
    if keys.get("GOOGLE_API_KEY"):
        try:
            return _call_gemini_direct(system, prompt, keys=keys)
        except Exception:                                              # noqa: BLE001
            pass   # fall through to OpenRouter's copy of the same model
    from integrations.llm import base
    return base.call_openrouter(f"{system}\n\n{prompt}", keys=keys,
                                model="google/gemini-3.5-flash")


def suggest(session, workspace_id, case_id, *, kind="reply", draft=None, keys=None,
            call_model=None, force=False):
    if kind not in KINDS:
        raise ValueError(f"unknown suggestion kind {kind!r}")
    keys = keys or {}

    # Only a draft-less "reply" is cacheable -- the console's auto-load on
    # opening a case, and the one case two different agents (or the same
    # agent reopening later) would otherwise both pay a real model call for
    # with nothing in the thread having changed. Anything with a draft is a
    # deliberate, input-specific ask and always goes straight to the model.
    cacheable = kind == "reply" and not draft
    fingerprint = _fingerprint(session, case_id) if cacheable else None
    if cacheable and not force:
        cached = cache_repo.get(session, case_id, kind)
        if cached and cached["fingerprint"] == fingerprint:
            return {"kind": kind, "suggestion": cached["suggestion"],
                    "sources": cached["sources"], "mock": cached["mock"],
                    "cached": True}

    thread = _thread(session, case_id)
    last_in = next((b for d, b in reversed(thread) if d == "inbound"), "")
    # No outbound message yet anywhere in the thread -> this really is the
    # first contact; anything else is an ongoing conversation.
    first_contact = not any(d == "outbound" for d, _b in thread)
    kb = _kb_context(session, workspace_id, draft or last_in) if kind == "reply" else []
    brand = _focus_brand_name(session, workspace_id)

    if not keys.get("GOOGLE_API_KEY"):
        suggestion = _mock_suggestion(kind, thread, draft, kb, brand, first_contact)
        out = {"kind": kind, "suggestion": suggestion,
              "sources": [a["id"] for a in kb], "mock": True}
    else:
        convo = "\n".join(f"[{d}] {b}" for d, b in thread[-8:])
        excerpts = "\n\n".join(f"# {a['title']}\n{a['excerpt']}" for a in kb)
        prompt = (f"Case thread:\n{convo}\n\n"
                  + (f"Draft to revise:\n{draft}\n\n" if draft else "")
                  + (f"Knowledge base:\n{excerpts}\n\n" if excerpts else "")
                  + "Produce only the suggested text.")
        fn = call_model or _default_call_model
        try:
            suggestion = fn(_system_prompt(kind, brand, first_contact), prompt, keys=keys).strip()
        except Exception as exc:                                      # noqa: BLE001
            # Surface a real, specific reason instead of an unhandled
            # exception turning into a bare 500 the caller can't act on —
            # the route already turns a ValueError into a clean 400.
            raise ValueError(f"the model didn't respond — {exc}") from exc
        suggestion = _trim_incomplete_tail(suggestion)
        out = {"kind": kind, "suggestion": suggestion,
              "sources": [a["id"] for a in kb], "mock": False}

    if cacheable:
        cache_repo.upsert(session, workspace_id, case_id, kind,
                          fingerprint=fingerprint, suggestion=out["suggestion"],
                          sources=out["sources"], mock=out["mock"])
    return {**out, "cached": False}
