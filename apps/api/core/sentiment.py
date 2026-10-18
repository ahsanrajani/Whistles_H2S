"""Sentiment scoring: star ratings and a lexicon first, a hosted model only for
the ambiguous rest.

Rules that override convenience:

- App-store reviews carry a 1–5 star rating: that *is* the sentiment
  (1–2 neg, 3 neu, 4–5 pos), recorded with ``model_id='rating'``. No model call.
- For other English text a small lexicon decides the clear cases
  (``model_id='lexicon'``); only genuinely mixed/faint text reaches the model.
- Non-English is written ``label='not_scored'`` with the reason, never guessed.
- Every row records how it was decided in ``model_id``. A cold model (HTTP 503)
  is retried once; anything else stops the pass and it stays visibly partial.

    python -m core.sentiment          # score the default workspace
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

MODEL_DEFAULT = "cardiffnlp/twitter-roberta-base-sentiment-latest"
# The current router endpoint first, the legacy host as a fallback — HF has
# served text-classification from both during the Inference Providers migration.
API_ROOTS = ("https://router.huggingface.co/hf-inference/models/",
             "https://api-inference.huggingface.co/models/")
BATCH = 10
MODEL_BUDGET_S = 75          # wall-clock ceiling for HF calls in one pass
UA = "whistles-ears/0.2"

# The two label vocabularies this family of models emits.
LABELS = {
    "positive": "pos", "neutral": "neu", "negative": "neg",
    "label_2": "pos", "label_1": "neu", "label_0": "neg",
}

_POS = re.compile(r"""
    \blove(d|s|ly)?\b | \bgreat\b | \bexcellent\b | \bamazing\b | \bawesome\b | \bperfect\b
  | \bbrilliant\b | \bwonderful\b | \bfantastic\b | \bsuperb\b | \boutstanding\b | \bflawless\b
  | \bbest\b | \bgood\b | \bnice\b | \bhelpful\b | \bsmooth\b | \bfast\b | \bquick\b | \beasy\b
  | \bconvenient\b | \breliable\b | \bseamless\b | \bhassle[\s-]?free\b | \buser[\s-]?friendly\b
  | \bthank(s| you)?\b | \bappreciate\b | \brecommend\w* | \bhappy\b | \bsatisf\w+ | \bimpress\w+
  | \bworks?\s+(great|well|fine|perfectly|smoothly)\b | \bwell\s+done\b | \bkeep\s+it\s+up\b
  | \b5\s*star | \bfive\s+star
""", re.I | re.X)
_NEG = re.compile(r"""
    \bcrash(ed|es|ing)?\b | \bkeeps?\s+clos\w+ | \bforce\s*clos\w* | \bnot\s+responding\b
  | \bbug(s|gy)?\b | \berror(s)?\b | \bglitch\w* | \bfreez\w+ | \bhang(s|ing|ed)?\b | \bstuck\b
  | \bslow\b | \blag(gy|s|ging)?\b | \bwo(n['’]?t|nt)\s+(open|load|work) | \bdoes\s?n['’]?t\s+work
  | \bnot\s+work(ing)?\b | \bstopped\s+working\b | \bunable\b | \bcan['’]?t\s+(log\s?in|login|open|access)
  | \bworst\b | \buseless\b | \bpathetic\b | \bterrible\b | \bhorrible\b | \bawful\b | \bpoor\b | \bbad\b
  | \brubbish\b | \bgarbage\b | \btrash\b | \bwaste\b | \bdisappoint\w* | \bfrustrat\w* | \bannoying\b
  | \bridiculous\b | \bhate[sd]?\b | \bangry\b | \bnonsense\b | \bscam\w* | \bfraud\w* | \bbroken\b
  | \bproblem(s|atic)?\b | \bissue(s)?\b | \bcomplain\w* | \bnever\s+works?\b | \bnetwork\s+error\b
  | \bserver\s+(down|error)\b | \b1\s*star | \bone\s+star | \bzero\s+star | \buninstall\w*
""", re.I | re.X)
_NEGATORS = re.compile(r"\b(not|no|never|can['’]?t|cannot|won['’]?t|do(?:es)?n['’]?t|did\s?n['’]?t|is\s?n['’]?t|are\s?n['’]?t|wasn['’]?t)\b", re.I)


def now():
    return datetime.now(timezone.utc).isoformat()


def _rating_label(rating):
    """A star rating is the sentiment. 1–2 neg · 3 neu · 4–5 pos."""
    try:
        stars = int(rating)
    except (TypeError, ValueError):
        return None
    if stars <= 0 or stars > 5:
        return None
    return "neg" if stars <= 2 else "neu" if stars == 3 else "pos"


# Wire-copy surfaces: an absence of sentiment cues is genuinely neutral
# (a filing, an announcement), so don't spend a model call deciding that.
_NEUTRAL_WHEN_FAINT = {"news", "web"}


def _lexicon_label(text, surface=None):
    """Clear-cut lexical sentiment, or ``None`` when the text is too faint/mixed
    to call without the model. Handles a leading negator before a positive cue
    ("not good", "doesn't work well")."""
    body = (text or "").lower()
    if not body.strip():
        return None
    pos = len(_POS.findall(body))
    neg = len(_NEG.findall(body))
    # "not <good>" / "no <good>" within a short window flips a positive cue.
    for match in _POS.finditer(body):
        window = body[max(0, match.start() - 24):match.start()]
        if _NEGATORS.search(window):
            pos -= 1
            neg += 1
    if neg > pos and neg >= 1:
        return "neg"
    if pos > neg and pos >= 1:
        return "pos"
    if pos == 0 and neg == 0:
        return "neu" if surface in _NEUTRAL_WHEN_FAINT else None
    return "neu"                          # balanced signal


def _normalise(out, n):
    """The hf-inference router is inconsistent for a batch of ``n`` inputs: it
    may return ``n`` per-input label lists, or a single list holding the ``n``
    per-input top-1 dicts. Return a list of ``n`` predictions, each a list of
    ``{label, score}`` — or ``None`` if the shape can't be reconciled."""
    if not isinstance(out, list) or not out:
        return None
    if isinstance(out[0], dict):                       # one un-nested prediction
        out = [out]
    if (n > 1 and len(out) == 1 and isinstance(out[0], list)
            and len(out[0]) == n and all(isinstance(x, dict) for x in out[0])):
        return [[x] for x in out[0]]                   # router flattened the batch
    if len(out) != n:
        return None
    return [p if isinstance(p, list) else [p] for p in out]


def _resolve_model(keys):
    return (keys.get("SENTIMENT_MODEL_ID")
            or os.environ.get("SENTIMENT_MODEL_ID")
            or MODEL_DEFAULT)


def _post(model_id, token, texts, timeout=60):
    body = json.dumps({"inputs": texts,
                       "options": {"wait_for_model": True}}).encode()
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


def _label_of(prediction):
    """A text-classification prediction is a list of {label, score}."""
    if not prediction:
        return None
    top = max(prediction, key=lambda d: d.get("score", 0))
    return LABELS.get(str(top.get("label", "")).strip().lower())


def _put(db, ws, mid, label, model_id, lang, note):
    _p.upsert_sentiment(db.session, workspace_id=ws, mention_id=mid, label=label, model_id=model_id,
                        scored_lang=lang, scored_at=now(), note=note)


def score_pending(db, ws, keys, log, limit=400, reset=False):
    """Score every unscored client-safe mention in one workspace.

    Order: star rating → lexicon → model. With ``reset=True`` the workspace's
    existing sentiment rows are cleared first (use after a scorer change).
    Returns {"scored", "by_rating", "by_lexicon", "by_model", "skipped",
    "model_id", "ok"}.
    """
    model_id = _resolve_model(keys)
    token = keys.get("HF_TOKEN") or os.environ.get("HF_TOKEN")
    unit_cost = sources.SOURCES.get("huggingface_sentiment", {}).get("unit_cost", 0.0)

    if reset:
        n = _p.clear_sentiment(db.session, ws)
        db.commit()
        log(f"sentiment · reset {n} existing rows")

    rows = _p.pending_sentiment(db.session, ws, limit)

    skipped = by_rating = by_lexicon = 0
    english = []
    for mid, lang, surface, rating, text in rows:
        text = (text or "").strip()
        rating_label = _rating_label(rating) if surface == "app_reviews" else None
        if rating_label:
            _put(db, ws, mid, rating_label, "rating", lang or "en",
                 f"derived from {int(rating)}-star rating")
            by_rating += 1
        elif lang != "en":
            _put(db, ws, mid, "not_scored", model_id, lang or "unknown",
                 f"lang {lang or 'unknown'}: only en is scored")
            skipped += 1
        elif not text:
            _put(db, ws, mid, "not_scored", model_id, "en", "no text to score")
            skipped += 1
        else:
            lex = _lexicon_label(text, surface)
            if lex is not None and not token:
                _put(db, ws, mid, lex, "lexicon", "en", "lexicon (no model configured)")
                by_lexicon += 1
            elif lex is not None:
                _put(db, ws, mid, lex, "lexicon", "en", None)
                by_lexicon += 1
            else:
                english.append((mid, text))
    db.commit()

    if not english:
        log(f"sentiment · {by_rating} by rating · {by_lexicon} by lexicon · "
            f"{skipped} not_scored · nothing for the model")
        return {"scored": by_rating + by_lexicon, "by_rating": by_rating,
                "by_lexicon": by_lexicon, "by_model": 0, "skipped": skipped,
                "model_id": model_id, "ok": True}

    if not token:
        for mid, text in english:                      # faint text, no model: neutral
            _put(db, ws, mid, "neu", "lexicon", "en", "lexicon fallback (no model, no cue)")
        db.commit()
        log(f"sentiment · {by_rating} by rating · {by_lexicon + len(english)} by lexicon · "
            f"HF_TOKEN missing")
        return {"scored": by_rating + by_lexicon + len(english), "by_rating": by_rating,
                "by_lexicon": by_lexicon + len(english), "by_model": 0,
                "skipped": skipped, "model_id": model_id, "ok": False}

    log(f"sentiment · {by_rating} by rating · {by_lexicon} by lexicon · "
        f"model {model_id} · {len(english)} for the model")
    scored = 0
    ok = True
    deadline = time.monotonic() + MODEL_BUDGET_S
    for start in range(0, len(english), BATCH):
        chunk = english[start:start + BATCH]
        texts = [t[:1600] for _mid, t in chunk]
        if time.monotonic() > deadline:
            # Out of model budget — lexicon-fill the remainder so the run
            # completes bounded; the neutral defaults stay re-scorable.
            rest = english[start:]
            for mid, text in rest:
                _put(db, ws, mid, _lexicon_label(text) or "neu", "lexicon", "en",
                     "lexicon (model budget exhausted)")
                by_lexicon += 1
            log(f"sentiment · model budget hit, lexicon-filled {len(rest)}")
            ok = False
            break
        try:
            out = _post(model_id, token, texts)
        except urllib.error.HTTPError as e:
            if e.code == 503:                       # model still loading — one retry
                log("sentiment · model cold (503), waiting 15s")
                time.sleep(15)
                try:
                    out = _post(model_id, token, texts)
                except Exception as retry_err:
                    log(f"sentiment · stopped: {retry_err}")
                    ok = False
                    break
            else:
                log(f"sentiment · stopped: HTTP {e.code} {e.reason}")
                ok = False
                break
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            # A slow/cold model shouldn't kill the pass — the rating and lexicon
            # layers already carried most rows. Skip this batch (lexicon-fill it)
            # and keep going; the row stays re-scorable on the next run.
            log(f"sentiment · batch skipped ({e}); lexicon-filling {len(chunk)}")
            for mid, text in chunk:
                _put(db, ws, mid, _lexicon_label(text) or "neu", "lexicon", "en",
                     "lexicon (model unreachable)")
                scored += 1
            ok = False
            continue
        except Exception as e:
            log(f"sentiment · stopped: {e}")
            ok = False
            break

        if isinstance(out, dict) and out.get("error"):
            log(f"sentiment · stopped: {out.get('error')}")
            ok = False
            break
        predictions = _normalise(out, len(chunk))
        if predictions is None:
            log(f"sentiment · stopped: unexpected response shape {str(out)[:120]}")
            ok = False
            break
        for (mid, text), prediction in zip(chunk, predictions):
            label = _label_of(prediction) or _lexicon_label(text) or "neu"
            _put(db, ws, mid, label, model_id, "en", None)
            scored += 1
        db.commit()
        time.sleep(0.3)

    _p.insert_call_log(
        db.session, workspace_id=ws,
        run_id=f"score-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        source="huggingface_sentiment", calls=(len(english) + BATCH - 1) // BATCH,
        units=scored, unit_cost=unit_cost, ok=ok, at=now())
    db.commit()
    log(f"sentiment · {by_rating} by rating · {by_lexicon} by lexicon · "
        f"{scored} by model · {skipped} not_scored" + ("" if ok else " · run incomplete"))
    return {"scored": by_rating + by_lexicon + scored, "by_rating": by_rating,
            "by_lexicon": by_lexicon, "by_model": scored, "skipped": skipped,
            "model_id": model_id, "ok": ok}
