"""Social listening corpus: brand chatter on the open web, app-store reviews,
branch reviews and the branch/ATM catalogue."""
import math
from statistics import NormalDist

from sqlalchemy import text

from db.repositories import locations as loc_repo
from db.repositories import metric_fact as mf_repo

from . import corpus as C
from datetime import timedelta

from .base import NOW, Seed, stamp

TOTAL_MENTIONS = 560
LANG_MIX = (("en", 0.91), ("roman_urdu", 0.06), ("ur", 0.03))
SURFACES = (("x", "x_recent", 0.24), ("news", "googlenews_rss", 0.30), ("news", "dataforseo_content", 0.11),
            ("reddit", "dataforseo_serp", 0.1), ("youtube", "youtube_v3", 0.1),
            ("linkedin", "brightdata_linkedin_posts", 0.08), ("web", "web_backfill", 0.11))
OUTLETS = {"news": ["Daily Ledger", "Business Wire PK", "The Finance Desk", "Metro Herald", "Market Pulse"],
           "reddit": ["r/pakistan", "r/PakistaniFinance"], "x": ["x.com"], "youtube": ["Money Matters PK", "Tech & Banking", "Urdu Finance TV"],
           "linkedin": ["linkedin.com"], "web": ["bankcompare.example", "consumerforum.example"]}
# brand -> topic -> (weight multiplier, negative-probability override)
BIAS = {"Vantora Bank": {"cards": (1.3, 0.6), "service": (1.2, 0.6)},
        "Kestrel Trust Bank": {"branch": (1.5, 0.35), "loans": (1.3, 0.3)},
        "Solenne Bank": {"deposits": (2.2, 0.08), "loans": (1.2, 0.15)},
        "Nimbus Digital Bank": {"app": (2.0, 0.12), "branch": (0.2, 0.7)}}


def _pick_day(rng) -> float:
    days = list(range(0, 90))
    weights = [(1 + 1.2 * math.exp(-d / 12)) * (0.7 if (NOW.weekday() - d) % 7 in (5, 6) else 1) for d in days]
    return rng.choices(days, weights)[0] + rng.random() * 0.8


def _tone(rng, brand, topic) -> str:
    share, pos, neu = C.BRANDS[brand]
    if brand == C.FOCUS:
        p_neg = C.FOCUS_NEG.get(topic, 0.35)
    else:
        p_neg = BIAS.get(brand, {}).get(topic, (1, 1 - pos - neu))[1]
    r = rng.random()
    if r < p_neg:
        return "neg"
    return "pos" if rng.random() < pos / max(pos + neu, 0.01) else "neu"


def _fill(rng, tpl: str, brand: str) -> str:
    rival = rng.choice([b for b in C.BRANDS if b != brand])
    return tpl.format(b=brand, c=rival, n=rng.randint(2, 9), amt=f"Rs {rng.choice([4500, 12000, 38000, 75000, 150000]):,}",
                      city=rng.choice(C.CITIES))


def _text(rng, brand, topic, tone) -> tuple[str, str, str]:
    """(text, lang, category) for one chatter item."""
    cat = {"neg": "complaint", "pos": "praise", "neu": "question"}[tone]
    r, acc = rng.random(), 0.0
    lang = "en"
    for code, p in LANG_MIX:
        acc += p
        if r < acc:
            lang = code
            break
    if lang == "roman_urdu":
        return _fill(rng, rng.choice(C.ROMAN[tone]), brand), lang, cat
    if lang == "ur":
        return _fill(rng, rng.choice(C.URDU[tone]), brand), lang, cat
    return _fill(rng, rng.choice(C.T[(topic, tone)]), brand), lang, cat


def chatter(sd: Seed) -> None:
    rng = sd.rng
    for brand, (share, _p, _n) in C.BRANDS.items():
        n = round(TOTAL_MENTIONS * share)
        topics = list(C.TOPIC_WEIGHT)
        w = [C.TOPIC_WEIGHT[t] * (C.FOCUS_TOPIC_BIAS.get(t, 1) if brand == C.FOCUS else BIAS.get(brand, {}).get(t, (1, 0))[0])
             for t in topics]
        for _ in range(n):
            surface, source, _w = rng.choices(SURFACES, [s[2] for s in SURFACES])[0]
            day = _pick_day(rng)
            when = stamp(day, rng.randint(7, 23), rng.randint(0, 59))
            topic = rng.choices(topics, w)[0]
            tone = _tone(rng, brand, topic)
            outlet = rng.choice(OUTLETS[surface])
            brands = [brand]
            if surface == "news":
                tone_pick = rng.choice([x for x in C.NEWS if x[0] == tone] or C.NEWS)
                body, lang, cat = _fill(rng, tone_pick[1], brand), "en", "news"
                tone = tone_pick[0]
            else:
                body, lang, cat = _text(rng, brand, topic, tone)
                if rng.random() < 0.07:
                    rival = rng.choice([b for b in C.BRANDS if b != brand])
                    body = f"{brand} vs {rival}: {rival} gives a better profit rate but {brand} is better on {topic}. Comparing both."
                    brands, cat, tone = [brand, rival], "comparison", "neu"
                    lang = "en"
            sd.item(source=source, body=body, when=when, brands=brands, kind="post" if surface == "news" else "mention",
                    author=sd.handle() if surface not in ("news", "web") else outlet, outlet=outlet, lang=lang,
                    sentiment=tone, category=cat, needs_review=1 if rng.random() < 0.04 else 0, label=f"chatter:{surface}")


def app_reviews(sd: Seed) -> None:
    """Focus-brand app-store reviews + the headline store figures the Reviews page shows."""
    rng = sd.rng
    apps = {"appstore_reviews": ("appstore", "id900100200", "Lumora Mobile Banking", 142),
            "playstore_reviews": ("playstore", "com.lumorabank.mobile", "Lumora Mobile Banking", 210)}
    for source, (store, app_id, app_name, _n) in apps.items():
        for _ in range(28 if store == "appstore" else 38):
            day = _pick_day(sd.rng)
            r = rng.random()
            rating = 1 if r < 0.17 else 2 if r < 0.26 else 3 if r < 0.4 else 4 if r < 0.65 else 5
            tone = "neg" if rating <= 2 else "neu" if rating == 3 else "pos"
            topic = rng.choice(["app", "app", "payments", "service", "cards"])
            body = _fill(rng, rng.choice(C.T[(topic, tone if (topic, tone) in C.T else "neg")]), C.FOCUS)
            sd.item(source=source, body=body, title=body[:60], when=stamp(day, rng.randint(8, 23)), rating=rating,
                    brands=[C.FOCUS], kind="review", outlet="App Store" if store == "appstore" else "Google Play",
                    author=sd.handle(), sentiment=tone, category={"neg": "complaint", "pos": "praise", "neu": "feature_request"}[tone],
                    raw={"app_id": app_id, "app_name": app_name, "store": store}, label="app_reviews")
    facts = []
    for store, app_id, name, count, avg, hist in (
            ("appstore", "id900100200", "Lumora Mobile Banking", 1420, 4.1, {"1": 130, "2": 80, "3": 150, "4": 420, "5": 640}),
            ("playstore", "com.lumorabank.mobile", "Lumora Mobile Banking", 5120, 3.8, {"1": 760, "2": 430, "3": 680, "4": 1250, "5": 2000})):
        for back in range(60):                       # a daily series so Reports can chart and compare periods
            day = (NOW - timedelta(days=back)).date()
            drift = back / 60
            facts += [{"source": store, "entity_type": "app", "entity_ref": app_id, "metric": "rating_avg", "day": day, "value": round(avg - 0.25 * drift, 2)},
                      {"source": store, "entity_type": "app", "entity_ref": app_id, "metric": "rating_count", "day": day, "value": int(count * (1 - 0.18 * drift))},
                      {"source": store, "entity_type": "app", "entity_ref": app_id, "metric": "rating_histogram", "day": day,
                       "dims": {k: int(v * (1 - 0.18 * drift)) for k, v in hist.items()}},
                      {"source": store, "entity_type": "app", "entity_ref": app_id, "metric": "app_meta", "day": day, "value": 1.0,
                       "dims": {"name": name, "icon": None}}]
    mf_repo.upsert_many(sd.s, sd.ws, facts)


def branches(sd: Seed) -> None:
    """The branch/ATM catalogue and Google-style reviews attributed to each branch."""
    rng = sd.rng
    rows = []
    for city, name, kind, lat, lng, mean, n in C.LOCATIONS:
        rows.append({"key": loc_repo.slugify(city, name), "kind": kind, "name": name, "city": city,
                     "region": C.CITY_REGION[city], "address": f"{name}, {city}", "lat": lat, "lng": lng,
                     "geo_precision": "supplied", "source": "demo"})
    loc_repo.upsert_many(sd.s, sd.ws, rows)
    for city, name, kind, _lat, _lng, mean, n in C.LOCATIONS:
        key = loc_repo.slugify(city, name)
        if not n:
            continue
        ratings = []
        count = max(6, n // 2)
        for q in range(count):
            rating = max(1, min(5, round(mean + 0.9 * NormalDist().inv_cdf((q + 0.5) / count))))
            ratings.append(rating)
            pool = C.BRANCH_REVIEWS["bad" if rating <= 2 else "ok"]
            near = [t for r, t in pool if abs(r - rating) <= 1] or [t for _r, t in pool]
            body = rng.choice(near)
            sd.item(source="brightdata_gmaps_reviews", body=body, when=stamp(rng.random() * 80, rng.randint(9, 21)),
                    rating=rating, brands=[C.FOCUS], kind="review", outlet=name, author=sd.handle(),
                    sentiment="neg" if rating <= 2 else "neu" if rating == 3 else "pos",
                    category="complaint" if rating <= 2 else "praise" if rating >= 4 else "other",
                    raw={"branch_key": key, "branch_name": name}, label="branch_review")
        sd.s.execute(text("""UPDATE location SET rating = :r, review_count = :n, rating_source = 'google', rating_at = now()
                             WHERE workspace_id = :ws AND key = :k"""),
                     {"r": round(sum(ratings) / len(ratings), 1), "n": n * 9, "ws": sd.ws, "k": key})
