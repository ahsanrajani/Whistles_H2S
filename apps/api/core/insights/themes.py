"""A frequency read of the words and pairs that recur about the focus brand —
not topic modelling, a 'what is the conversation about' signal."""
import re
from collections import Counter

from db.analytics import themes as q

from .. import entity

STOPWORDS = set("""
a an the and or but if then else when while of to in on at by for with from up
down out over under again further is am are was were be been being have has had
having do does did doing this that these those i you he she it we they them his
her its our your their as not no nor so than too very can will just should now
about into after before above below off between through during over under
new latest news update updates say says said report reports according also
more most other some such only own same each few both any all get got would
one two three per via amid vs how what why who whom your via list top best
web watch video videos youtube channel subscribe click link full complete
method methods procedure procedures step steps guide review reviews explained
kaise tarika kya hai amp quot nbsp www com http https
pakistan pakistani karachi lahore islamabad rupee rupees pkr crore lakh
bank banks banking account accounts branch branches limited ltd islamic
""".split())


def themes(db, ws, brand_id, limit=14, min_count=3, surface=None):
    """The words and pairs that recur in what people say about the focus brand,
    with a sentiment lean where the mentions have been scored. Not topic
    modelling — a frequency read, useful for 'what is the conversation about'.
    """
    brands = entity.load(db, ws)
    brand_words = set(STOPWORDS)
    for b in brands:
        for w in re.findall(r"[a-z]{3,}", b["name"].lower()):
            brand_words.add(w)
        for pat in list(b.get("safe", [])) + list((b.get("gated") or {}).keys()):
            for w in re.findall(r"[a-z]{3,}", (pat or "").lower()):
                brand_words.add(w)
    brand_words.update(("alfalah", "alfa", "falah", "meezan", "hbl", "ubl",
                        "habib", "united", "bankalfalah"))

    rows = q.brand_text_rows(db.session, brand_id, surface)
    if not rows:
        return []

    freq = Counter()
    neg = Counter()
    pos = Counter()
    scored_any = False
    for text, label in rows:
        text = re.sub(r"&[a-z#0-9]+;", " ", (text or "").lower())
        toks = [t for t in re.findall(r"[a-z][a-z'’]{2,}", text)
                if t not in brand_words]
        grams = set(toks)
        grams.update(f"{a} {b}" for a, b in zip(toks, toks[1:])
                     if a not in brand_words and b not in brand_words)
        for g in grams:
            freq[g] += 1
            if label in ("neg", "pos"):
                scored_any = True
                (neg if label == "neg" else pos)[g] += 1

    ranked = [(t, n) for t, n in freq.most_common() if n >= min_count]
    # Prefer the phrase: drop a single word when a kept two-word phrase contains
    # it at a comparable frequency ("used" / "vehicles" behind "used vehicles").
    phrase_words = {}
    for term, n in ranked:
        if " " in term:
            for w in term.split():
                phrase_words[w] = max(phrase_words.get(w, 0), n)
    kept = [(t, n) for t, n in ranked
            if " " in t or phrase_words.get(t, 0) < 0.6 * n]

    out = []
    for term, n in kept:
        lean = "unscored"
        if scored_any:
            tn, tp = neg[term], pos[term]
            lean = ("negative" if tn > tp and tn else
                    "positive" if tp > tn and tp else
                    "mixed" if tn and tp else "neutral")
        out.append({"term": term, "n": n, "neg": neg[term], "pos": pos[term],
                    "lean": lean})
        if len(out) >= limit:
            break
    return out
