"""Mention-type classification: a deterministic keyword layer first, a hosted
zero-shot model only to break ties.

Discipline:

- Every row records how it was decided in ``model_class.model_id``: ``"rules"``
  for a keyword match, the resolved model id for a model call, ``"none"`` when
  nothing committed. An unpinned model silently invalidates the labelling, so
  the id is stored, never assumed.
- Only English mentions (``item.lang_guess == 'en'``) reach the model. A cold
  model (HTTP 503) is retried once; anything else stops the pass and the run
  stays visibly partial.

    python -m core.classify          # classify the default workspace
"""
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from db import pipeline as _p

from . import sources

MODEL_DEFAULT = "facebook/bart-large-mnli"
# Router endpoint first, legacy host as a fallback — same as sentiment.
API_ROOTS = ("https://router.huggingface.co/hf-inference/models/",
             "https://api-inference.huggingface.co/models/")
UA = "whistles-ears/0.2"

# (key, natural-language hypothesis for the zero-shot head, chip colour).
# The hypothesis phrasing is what the model actually scores; the key is what we
# store and filter on.
CATEGORIES = [
    ("complaint", "a customer complaint about a problem or bad service", "#a74437"),
    ("praise", "praise or a positive experience", "#247a59"),
    ("question", "a question asking for help or information", "#2f6f8f"),
    ("comparison", "comparing two or more banks or products", "#7d5a9e"),
    ("news", "a news report or company announcement", "#8a8a85"),
    ("fraud", "a report of fraud, a scam or a security concern", "#c26a1f"),
    ("feature_request", "a request for a new feature or improvement", "#5b5f97"),
    ("other", "general discussion", "#b7b7b2"),
]
HYPOTHESES = [h for _k, h, _c in CATEGORIES]
KEY_OF = {h: k for k, h, _c in CATEGORIES}
LABEL_OF = {k: k.replace("_", " ").capitalize() for k, _h, _c in CATEGORIES}
COLOUR_OF = {k: c for k, _h, c in CATEGORIES}
ORDER = {k: i for i, (k, _h, _c) in enumerate(CATEGORIES)}
# Eight candidate labels dilute a zero-shot softmax, so the model floor is
# lower than a binary task would use. The keyword layer below carries the
# confident calls; the model only decides the leftovers.
MIN_CONFIDENCE = 0.28
MODEL_BUDGET_S = 75         # wall-clock ceiling for HF calls in one pass

# Keyword rules, highest stakes first. Each value is a compiled alternation;
# the first pattern that hits wins. Phrasing is tuned for app-store reviews and
# retail-banking press in en / roman-urdu-inflected English.
_RULES = [
    ("fraud", 0.92, re.compile(r"""
        \bfraud\b | \bscam(s|med|mer|ming)?\b | \bphish\w* | \bhack(ed|ing|er)?\b
      | \bunauthori[sz]ed\b | \bunauthori[sz]ed\s+transaction\b
      | \bblackmail\w* | \bstole(n)?\b | \bcloned?\s+card\b
      | \b(otp|pin|cvv)\b.{0,30}\b(shared|leak\w*|stolen|compromis\w*)\b
      | \bmoney\b.{0,30}\b(deducted|debited|gone|missing|vanish\w*)\b.{0,20}\bwithout\b
    """, re.I | re.X)),
    ("complaint", 0.85, re.compile(r"""
        \bcrash(ed|es|ing)?\b | \bkeeps?\s+clos\w+ | \bforce\s*clos\w* | \bnot\s+responding\b
      | \bbug(s|gy)?\b | \berror(s)?\b | \bglitch\w* | \bfreez\w+ | \bhang(s|ing|ed)?\b | \bstuck\b
      | \bslow\b | \blag(gy|s|ging)?\b | \bwo(n['’]?t|nt)\s+(open|load|work) | \bcan['’]?t\s+(log\s?in|login|open|access|transfer|send)
      | \bdoes\s?n['’]?t\s+work | \bnot\s+work(ing)?\b | \bnothing\s+works?\b | \bstopped\s+working\b
      | \bunable\s+to\b | \bnot\s+able\s+to\b | \bkeeps?\s+(logging|signing)\s+(me\s+)?out\b
      | \botp\s+(not|isn['’]?t|never)\s+(received|coming|working|generat\w*) | \btransaction\s+(failed|declin\w*|not\s+process\w*)\b
      | \bmoney\s+(not|did\s?n['’]?t|has\s?n['’]?t)\s+(transfer\w*|credit\w*|receiv\w*) | \bpending\s+(for|since)\b
      | \bstill\s+(not|no|waiting|pending)\b | \bworst\b | \buseless\b | \bpathetic\b | \bterrible\b | \bhorrible\b | \bawful\b
      | \brubbish\b | \bgarbage\b | \btrash\b | \bwaste\s+of\b | \bdisappoint\w* | \bfrustrat\w* | \bannoying\b | \bridiculous\b
      | \bnonsense\b | \bfix\s+(this|it|the\s+app|asap)\b | \bpoor\s+(service|app|experience|customer)\b
      | \bnetwork\s+error\b | \bserver\s+(down|error|issue)\b | \bvery\s+(bad|poor|slow|disappointing)\b
      | \bworst\s+(app|bank|experience|service)\b | \bnot\s+user[\s-]?friendly\b
    """, re.I | re.X)),
    ("feature_request", 0.8, re.compile(r"""
        \bplease\s+add\b | \bpls\s+add\b | \bkindly\s+add\b | \bcan\s+you\s+(please\s+)?add\b
      | \badd\s+(an?\s+)?(option|feature|button|way|dark\s*mode) | \bthere\s+should\s+be\b
      | \b(would|it['’]?d)\s+be\s+(nice|great|better|helpful)\s+if\b | \bwish\s+(it|the\s+app|there|you|they)\b
      | \b(app\s+)?should\s+(have|add|include|allow|support)\b | \bhope\s+(you|they|the\s+app)\s+(add|include|will|can)\b
      | \bneeds?\s+(a|an|to\s+have|to\s+support)\b | \bsuggestion[:\s]
    """, re.I | re.X)),
    ("comparison", 0.8, re.compile(r"""
        \bbetter\s+than\b | \bworse\s+than\b | \bcompared?\s+to\b | \bcompare[sd]?\s+with\b
      | \s+vs\.?\s+ | \bversus\b | \bswitch(ed|ing)?\s+(to|from)\b | \bunlike\b | \bas\s+good\s+as\b
      | \b(hbl|meezan|ubl|mcb|allied|askari|faysal|standard\s+chartered|js\s+bank)\b.{0,40}\b(better|worse|faster|slower|smoother)\b
    """, re.I | re.X)),
    ("question", 0.72, re.compile(r"""
        \bhow\s+(do|can)\s+i\b | \bcan\s+(any)?(one|body)\s+(help|tell|explain|guide)\b
      | \bdoes\s+anyone\s+(know|have|face|else)\b | \banyone\s+(know|facing|having|else\s+facing)\b
      | \bis\s+there\s+(a\s+)?way\s+to\b | \bplease\s+(help|guide|tell|explain|assist)\b
      | \bwhat\s+should\s+i\s+do\b | \bwhy\s+is\s+(my|the|this)\b | \bhelp\s+me\s+(with|understand)\b
    """, re.I | re.X)),
    ("praise", 0.8, re.compile(r"""
        \blove(d|s|ly)?\b | \bgreat\b | \bexcellent\b | \bamazing\b | \bawesome\b | \bperfect\b | \bbrilliant\b
      | \bwonderful\b | \bfantastic\b | \bsuperb\b | \boutstanding\b | \bflawless\b
      | \bbest\s+(app|bank|banking)\b | \bgood\s+app\b | \bnice\s+app\b | \bvery\s+(good|nice|helpful|easy)\b
      | \bsmooth\b | \beasy\s+to\s+use\b | \buser[\s-]?friendly\b | \bseamless\b | \bhassle[\s-]?free\b
      | \bthank\s+you\b | \bwell\s+done\b | \bkeep\s+it\s+up\b | \bhighly\s+recommend\w*
    """, re.I | re.X)),
    ("news", 0.7, re.compile(r"""
        \bannounce[sd]?\b | \blaunch(e[sd]|ing)?\b | \bunveil\w* | \binaugurat\w* | \broll(s|ed)?\s+out\b
      | \bpartnership\b | \bpartners?\s+with\b | \bsigns?\s+(an?\s+)?(mou|agreement|deal)\b | \bmou\b
      | \bquarterly\b | \b(net\s+)?profit\b | \brevenue\b | \bdividend\b | \bearnings\b
      | \bappoint(s|ed|ment)?\b | \bnames?\s+new\b | \bnew\s+(ceo|cfo|president|chairman)\b
      | \bto\s+acquire\b | \bstake\s+in\b | \bipo\b | \bcredit\s+rating\b
      | \bhow\s+to\s+(open|create|apply|register|activate|use|get|download|unlock|update|link|transfer|generate)\b
      | \bstep[\s-]by[\s-]step\b | \btutorial\b | \bcomplete\s+guide\b | \bfull\s+(guide|details?|process|method)\b
      | \b(charges|fees|requirements?|procedure|method|process)\s+20\d\d\b | \bjobs?\s+20\d\d\b
    """, re.I | re.X)),
]
# Wire-copy and informational surfaces: the "news" cues apply here.
_NEWS_ONLY = {"news", "youtube", "web"}


def now():
    return datetime.now(timezone.utc).isoformat()


def _resolve_model(keys):
    return (keys.get("CLASSIFY_MODEL_ID")
            or os.environ.get("CLASSIFY_MODEL_ID")
            or MODEL_DEFAULT)


def _post(model_id, token, text, timeout=60):
    body = json.dumps({
        "inputs": text,
        "parameters": {"candidate_labels": HYPOTHESES, "multi_label": False},
        "options": {"wait_for_model": True},
    }).encode()
    last = None
    for root in API_ROOTS:
        req = urllib.request.Request(
            root + model_id, data=body,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                     "User-Agent": UA, "x-wait-for-model": "true"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (401, 403, 503):        # auth / cold — retrying host won't help
                raise
            # 404 / 410 → this host no longer serves the model; try the next.
    raise last


def _rule_category(text, surface=None):
    """Deterministic keyword pass. Returns (key, confidence) or (None, 0.0)."""
    body = text or ""
    for key, conf, pattern in _RULES:
        if key == "news" and surface not in _NEWS_ONLY:
            continue
        if pattern.search(body):
            return key, conf
    return None, 0.0


def _category_of(prediction):
    """Break the zero-shot response into (key, confidence).

    The hf-inference router serves this model two ways: the zero-shot pipeline
    dict ``{"labels": [...], "scores": [...]}`` (sorted desc), or a plain
    text-classification list ``[{"label","score"}, ...]``. Handle both. Below
    the confidence floor the model has not committed — return ``other``.
    """
    if isinstance(prediction, list):
        if prediction and isinstance(prediction[0], list):   # [[...]] batch-of-one
            prediction = prediction[0]
        if not prediction or not isinstance(prediction[0], dict):
            return "other", 0.0
        top = max(prediction, key=lambda d: d.get("score", 0.0))
        label, conf = str(top.get("label", "")), float(top.get("score", 0.0))
    elif isinstance(prediction, dict):
        labels = prediction.get("labels") or []
        scores = prediction.get("scores") or []
        if not labels or not scores:
            return "other", 0.0
        label, conf = str(labels[0]), float(scores[0])
    else:
        return "other", 0.0
    if conf < MIN_CONFIDENCE:
        return "other", conf
    return KEY_OF.get(label, "other"), conf


def _write(db, ws, mid, category, conf, model_id):
    _p.upsert_mention_class(db.session, workspace_id=ws, mention_id=mid, category=category,
                            confidence=round(float(conf), 4), model_id=model_id,
                            classified_at=now())


# Informational surfaces: coverage, not user feedback. Absent a keyword hit
# they are "news", not "other".
_INFO_SURFACES = {"news", "youtube", "web"}


def _fallback_category(surface, rating, sentiment):
    """A deterministic type for a row the rules did not catch, from the signals
    we always have: the surface, the star rating, the sentiment label. Returns a
    (category, confidence) with a modest confidence so a later model pass can
    still override it."""
    try:
        stars = int(rating)
    except (TypeError, ValueError):
        stars = None
    if surface == "app_reviews" and stars:
        if stars <= 2:
            return "complaint", 0.5
        if stars >= 4:
            return "praise", 0.5
        # 3★ — lean on sentiment if we have it
        return ("complaint", 0.4) if sentiment == "neg" else \
               ("praise", 0.4) if sentiment == "pos" else ("other", 0.2)
    if surface in _INFO_SURFACES:
        return "news", 0.45
    if sentiment == "neg":
        return "complaint", 0.35
    if sentiment == "pos":
        return "praise", 0.35
    return "other", 0.2


def classify_pending(db, ws, keys, log, limit=400, reset=False):
    """Classify every unclassified client-safe mention in one workspace.

    Keyword rules decide the confident cases (``model_id='rules'``); only the
    leftovers reach the zero-shot model. With ``reset=True`` the workspace's
    existing rows are cleared first. Returns {"classified", "by_rule",
    "by_model", "skipped", "model_id", "ok"}.
    """
    model_id = _resolve_model(keys)
    token = keys.get("HF_TOKEN") or os.environ.get("HF_TOKEN")
    unit_cost = sources.SOURCES.get("huggingface_classify", {}).get("unit_cost", 0.0)

    if reset:
        n = _p.clear_mention_class(db.session, ws)
        db.commit()
        log(f"classify · reset {n} existing rows")

    rows = _p.pending_mention_class(db.session, ws, limit)

    by_rule = by_fallback = 0
    pending = []
    for mid, lang, surface, rating, text, senti in rows:
        text = (text or "").strip()
        key, conf = _rule_category(text, surface) if text else (None, 0.0)
        if key:
            _write(db, ws, mid, key, conf, "rules")
            by_rule += 1
            continue
        fb_cat, fb_conf = _fallback_category(surface, rating, senti)
        if lang != "en" or not text or not token:
            _write(db, ws, mid, fb_cat, fb_conf, "fallback")
            by_fallback += 1
        else:
            pending.append((mid, text, fb_cat, fb_conf))
    db.commit()

    if not pending:
        log(f"classify · {by_rule} by rule · {by_fallback} by fallback · nothing for the model")
        return {"classified": by_rule + by_fallback, "by_rule": by_rule,
                "by_model": 0, "skipped": by_fallback, "model_id": model_id, "ok": True}

    log(f"classify · {by_rule} by rule · {by_fallback} by fallback · "
        f"model {model_id} · {len(pending)} for the model")
    done = 0
    ok = True
    deadline = time.monotonic() + MODEL_BUDGET_S
    for i, (mid, text, fb_cat, fb_conf) in enumerate(pending):
        if time.monotonic() > deadline:
            for m2, _t, c2, cf2 in pending[i:]:
                _write(db, ws, m2, c2, cf2, "fallback")
                by_fallback += 1
            log(f"classify · model budget hit, fell back on {len(pending) - i}")
            ok = False
            break
        try:
            out = _post(model_id, token, text[:1000])
        except urllib.error.HTTPError as e:
            if e.code == 503:                       # model still loading — one retry
                log("classify · model cold (503), waiting 15s")
                time.sleep(15)
                try:
                    out = _post(model_id, token, text[:1000])
                except Exception as retry_err:
                    log(f"classify · stopped: {retry_err}")
                    ok = False
                    break
            else:
                log(f"classify · stopped: HTTP {e.code} {e.reason}")
                ok = False
                break
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            # A slow model shouldn't kill the pass — fall back deterministically
            # (model_id records it), the row is still re-scorable on the next run.
            log(f"classify · fallback for one row ({e})")
            _write(db, ws, mid, fb_cat, fb_conf, "fallback")
            by_fallback += 1
            ok = False
            continue
        except Exception as e:
            log(f"classify · stopped: {e}")
            ok = False
            break

        if isinstance(out, dict) and out.get("error"):
            log(f"classify · stopped: {out.get('error')}")
            ok = False
            break
        category, conf = _category_of(out)
        if category == "other":                # model didn't commit — use the signal we have
            category, conf = fb_cat, fb_conf
            _write(db, ws, mid, category, conf, "fallback")
            by_fallback += 1
        else:
            _write(db, ws, mid, category, conf, model_id)
            done += 1
        if (done + by_fallback) % 20 == 0:
            db.commit()
        time.sleep(0.2)
    db.commit()

    _p.insert_call_log(
        db.session, workspace_id=ws,
        run_id=f"classify-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        source="huggingface_classify", calls=len(pending), units=done,
        unit_cost=unit_cost, ok=ok, at=now())
    db.commit()
    log(f"classify · {by_rule} by rule · {by_fallback} by fallback · {done} by model"
        + ("" if ok else " · run incomplete"))
    return {"classified": by_rule + by_fallback + done, "by_rule": by_rule,
            "by_fallback": by_fallback, "by_model": done, "skipped": 0,
            "model_id": model_id, "ok": ok}
