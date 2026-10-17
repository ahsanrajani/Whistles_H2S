"""Owned-analytics provider interface (build plan §6 / P4.1).

One provider per owned surface (Meta / Instagram / X / LinkedIn). Each declares
its platform id and the per-tenant credential keys that switch it out of mock
mode. ``fetch(workspace_id, day)`` returns a list of fact dicts shaped for
``repo.metric_fact.upsert_many``:

    {source, entity_type, entity_ref, metric, day,
     value, numerator?, denominator?, dims?}

The live HTTP pulls (Graph API Insights, X analytics, LinkedIn reporting) are a
deployment step. Mock mode is deterministic — seeded on
``(platform, workspace_id, day)`` — so a test and a demo get stable numbers and
re-ingesting a day is a no-op.
"""
import hashlib
import random
from datetime import date


class OwnedAnalyticsError(Exception):
    """A live analytics pull failed for one provider/day."""


def _rng(*parts) -> random.Random:
    seed = hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()
    return random.Random(int(seed[:16], 16))


class OwnedAnalyticsProvider:
    PLATFORM: str = "base"
    CRED_KEYS: tuple[str, ...] = ()
    # (entity_type, metric) pairs this provider emits at the account grain
    ACCOUNT_METRICS: tuple[tuple[str, str], ...] = ()
    ENTITY_TYPE: str = "account"

    def __init__(self, keys: dict | None = None, *, transport=None, live=None):
        from integrations.write.base import live_enabled
        self.k = dict(keys or {})
        self._transport = transport
        self._mock = not all(self.k.get(key) for key in self.CRED_KEYS)
        # same switch as outbound writes: GURU_WRITE_LIVE gates real API calls
        self._live_pulls = live_enabled(live, self.k)

    def is_mock(self) -> bool:
        return self._mock

    def is_live(self) -> bool:
        return not self._mock and self._live_pulls and self._transport is None

    # --- public ------------------------------------------------------
    def fetch(self, workspace_id: int, day: date) -> list[dict]:
        if self._transport is not None:
            return list(self._transport(self.PLATFORM, workspace_id, day))
        if self._mock:
            return self._mock_facts(workspace_id, day)
        if self._live_pulls:
            return list(self._live(workspace_id, day))
        # credentialled but live pulls not enabled — no data rather than raising,
        # so a partially-configured tenant still ingests its other providers.
        return []

    def _live(self, workspace_id: int, day: date) -> list[dict]:   # pragma: no cover
        return []

    # --- mock ------------------------------------------------------
    def _mock_facts(self, workspace_id: int, day: date) -> list[dict]:
        rows: list[dict] = []
        acct = _rng(self.PLATFORM, workspace_id, day)
        impressions = acct.randint(4_000, 40_000)
        engagements = int(impressions * acct.uniform(0.01, 0.06))
        base = {
            "impressions": impressions,
            "reach": int(impressions * acct.uniform(0.6, 0.9)),
            "engagements": engagements,
            "followers": acct.randint(20_000, 200_000),
            "profile_visits": acct.randint(50, 900),
        }
        for etype, metric in self.ACCOUNT_METRICS:
            rows.append({"source": self.PLATFORM, "entity_type": etype,
                         "entity_ref": "self", "metric": metric, "day": day,
                         "value": float(base[metric])})
        # one proportion carrying its raw counts, for P4.2's Wilson interval
        rows.append({"source": self.PLATFORM, "entity_type": self.ENTITY_TYPE,
                     "entity_ref": "self", "metric": "engagement_rate", "day": day,
                     "value": engagements / impressions if impressions else None,
                     "numerator": float(engagements),
                     "denominator": float(impressions)})
        rows.extend(self._mock_posts(workspace_id, day))
        return rows

    def _mock_posts(self, workspace_id: int, day: date) -> list[dict]:
        """A few post-grain rows per day so the P4.5 post/video scorecards have
        something to render. ``media_type`` is a dim, not a metric."""
        out: list[dict] = []
        media = self.POST_MEDIA_TYPES
        for i in range(3):
            pr = _rng(self.PLATFORM, workspace_id, day, "post", i)
            ref = f"{day.isoformat()}-{i}"
            mtype = media[pr.randrange(len(media))]
            impr = pr.randint(500, 12_000)
            eng = int(impr * pr.uniform(0.02, 0.12))
            for metric, val in (("impressions", impr), ("engagements", eng),
                                ("reactions", int(eng * pr.uniform(0.4, 0.8)))):
                out.append({"source": self.PLATFORM, "entity_type": "post",
                            "entity_ref": ref, "metric": metric, "day": day,
                            "value": float(val), "dims": {"media_type": mtype}})
            out.append({"source": self.PLATFORM, "entity_type": "post",
                        "entity_ref": ref, "metric": "engagement_rate", "day": day,
                        "value": eng / impr if impr else None,
                        "numerator": float(eng), "denominator": float(impr),
                        "dims": {"media_type": mtype}})
        return out

    POST_MEDIA_TYPES: tuple[str, ...] = ("image", "video", "link")
