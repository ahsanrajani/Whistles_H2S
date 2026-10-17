"""Shared plumbing for the Lumora Bank demo seed: one ``Seed`` object holding
the session, workspace, brand ids and a deterministic RNG, plus the single
``item`` writer that every module goes through (so each item gets its mention,
sentiment and classification rows with ``workspace_id`` set -- row-level
security reads that column)."""
import json
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from core import sources

NOW = datetime.now(timezone.utc)
PKT = timedelta(hours=5)
MODEL = "demo-seed"
LANG_SCORED = {"en": "en", "roman_urdu": "roman_urdu", "ur": "ur"}


def stamp(days_ago: float, hour: int = 12, minute: int = 0) -> str:
    """ISO-8601 Z text for ``days_ago`` days back at ``hour`` Pakistan time."""
    day = (NOW - timedelta(days=days_ago)).replace(hour=0, minute=0, second=0, microsecond=0)
    return (day + timedelta(hours=hour, minutes=minute) - PKT).strftime("%Y-%m-%dT%H:%M:%SZ")


def dt(days_ago: float, hour: int = 12, minute: int = 0) -> datetime:
    day = (NOW - timedelta(days=days_ago)).replace(hour=0, minute=0, second=0, microsecond=0)
    return day + timedelta(hours=hour, minutes=minute) - PKT


class Seed:
    def __init__(self, session, ws: int, brand_ids: dict[str, int], rng: random.Random):
        self.s, self.ws, self.brand_ids, self.rng = session, ws, brand_ids, rng
        self.n = 0
        self.users: dict[str, int] = {}
        self.counts: dict[str, int] = {}

    def bump(self, key: str, by: int = 1) -> None:
        self.counts[key] = self.counts.get(key, 0) + by

    def item(self, *, source: str, body: str, when: str, brands=(), kind: str | None = None,
             title=None, rating=None, raw: dict | None = None, author=None, outlet=None,
             lang: str = "en", sentiment: str | None = None, category: str | None = None,
             needs_review: int = 0, label: str | None = None, excluded_reason: str | None = None) -> str:
        """Insert one item (+ mentions/sentiment/class). Returns its external id."""
        self.n += 1
        meta = sources.SOURCES[source]
        ext = f"demo-{source}-{self.n}"
        payload = dict(raw or {})
        if kind:
            payload["kind"] = kind
        item_id = self.s.execute(text("""
            INSERT INTO item (workspace_id, surface, source, source_kind, external_id, url, outlet,
                              author, published_at, title, body, lang_guess, rating, raw_json,
                              collected_at, content_hash)
            VALUES (:ws, :surface, :src, :sk, :ext, :url, :outlet, :author, :pub, :title, :body,
                    :lang, :rating, :raw, :now, :hash) RETURNING id
        """), {"ws": self.ws, "surface": meta["surface"], "src": source, "sk": meta["kind"],
               "ext": ext, "url": f"https://demo.invalid/lumora/{ext}", "outlet": outlet,
               "author": author, "pub": when, "title": title, "body": body, "lang": lang,
               "rating": rating, "raw": json.dumps(payload), "now": stamp(0, 12),
               "hash": f"demo-{self.n}-{abs(hash(body)) % 10**8}"}).scalar_one()
        for name in brands:
            mid = self.s.execute(text("""
                INSERT INTO mention (item_id, brand_id, workspace_id, rule, needs_review, excluded, exclude_reason)
                VALUES (:i, :b, :ws, 'demo', :nr, :ex, :why) RETURNING id
            """), {"i": item_id, "b": self.brand_ids[name], "ws": self.ws, "nr": needs_review,
                   "ex": 1 if excluded_reason else 0, "why": excluded_reason}).scalar_one()
            if sentiment:
                self.s.execute(text("""
                    INSERT INTO sentiment (mention_id, workspace_id, label, model_id, scored_lang, scored_at)
                    VALUES (:m, :ws, :l, :mod, :lang, :at)
                """), {"m": mid, "ws": self.ws, "l": sentiment, "mod": MODEL,
                       "lang": LANG_SCORED.get(lang, "en"), "at": when})
            if category:
                self.s.execute(text("""
                    INSERT INTO mention_class (mention_id, workspace_id, category, confidence, model_id, classified_at)
                    VALUES (:m, :ws, :c, :conf, :mod, :at)
                """), {"m": mid, "ws": self.ws, "c": category,
                       "conf": round(self.rng.uniform(0.62, 0.97), 2), "mod": MODEL, "at": when})
        self.bump(label or meta["surface"])
        return ext

    def handle(self) -> str:
        first = self.rng.choice(["ayesha", "bilal", "sana", "hamza", "maryam", "usman", "hira", "ali",
                                 "zara", "danish", "fatima", "kashif", "noor", "rizwan", "iqra", "talha"])
        return f"{first}_{self.rng.randint(10, 99)}"
