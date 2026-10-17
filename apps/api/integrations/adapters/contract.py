"""Adapter contract v2 machinery (build plan §4 / P2.2).

Every source declares its operational parameters in ``core/sources.py``:

    cadence       how often to run it, seconds (the scheduler uses this in P2.7)
    cursor        incremental cursor kind — "timestamp" | "id" | "page" | "none"
    rate_limit    {"per_second": float, "burst": int} or None
    unit_cost     list price per call (already present)
    needs         required credential env vars (already present)
    source_class  "official" (the platform's own API) | "third_party"

This module holds the reusable pieces the base ``Adapter`` and the collection
orchestrator use: a token bucket and a circuit breaker. The breaker's state
persists per (workspace, source) in ``source_state``
(``db/repositories/source_state.py``); its clock is wall-time so ``opened_at``
survives a restart.
"""
import time

OFFICIAL = "official"
THIRD_PARTY = "third_party"
SOURCE_CLASSES = (OFFICIAL, THIRD_PARTY)

CURSOR_KINDS = ("timestamp", "id", "page", "none")

CLOSED, OPEN, HALF_OPEN = "closed", "open", "half_open"


class TokenBucket:
    """Classic token bucket. In-process, monotonic clock — one per adapter
    instance, not persisted."""

    def __init__(self, per_second: float, burst: int | None = None, *,
                 clock=time.monotonic):
        self.rate = max(0.0, float(per_second))
        self.capacity = float(burst if burst is not None else max(1.0, per_second))
        self._tokens = self.capacity
        self._clock = clock
        self._last = clock()

    def _refill(self) -> None:
        now = self._clock()
        if now > self._last:
            self._tokens = min(self.capacity,
                               self._tokens + (now - self._last) * self.rate)
            self._last = now

    def try_take(self, n: float = 1.0) -> bool:
        self._refill()
        if self._tokens + 1e-9 >= n:
            self._tokens -= n
            return True
        return False

    def take(self, n: float = 1.0, *, sleep=time.sleep) -> float:
        """Block until ``n`` tokens are free; return the seconds slept."""
        waited = 0.0
        while not self.try_take(n):
            deficit = max(n - self._tokens, 0.0)
            pause = deficit / self.rate if self.rate > 0 else 0.05
            pause = max(pause, 0.001)
            sleep(pause)
            waited += pause
        return waited


class CircuitBreaker:
    """Opens after ``fail_threshold`` consecutive failures; after
    ``cooldown_seconds`` the next ``allow()`` returns True once (half-open). A
    success there closes it; a failure re-opens it."""

    def __init__(self, *, fail_threshold: int = 5, cooldown_seconds: int = 300,
                 clock=time.time):
        self.fail_threshold = fail_threshold
        self.cooldown = cooldown_seconds
        self._clock = clock
        self.state = CLOSED
        self.failures = 0
        self.opened_at: float | None = None

    @classmethod
    def restore(cls, data: dict | None, **kw) -> "CircuitBreaker":
        cb = cls(**kw)
        if data:
            cb.state = data.get("circuit_state") or CLOSED
            cb.failures = int(data.get("consecutive_failures") or 0)
            cb.opened_at = data.get("opened_at")
        return cb

    def snapshot(self) -> dict:
        return {"circuit_state": self.state,
                "consecutive_failures": self.failures,
                "opened_at": self.opened_at}

    def allow(self) -> bool:
        if self.state == OPEN:
            if self.opened_at is not None and \
                    self._clock() - self.opened_at >= self.cooldown:
                self.state = HALF_OPEN
                return True
            return False
        return True  # closed, or half-open (one trial in flight)

    def record_success(self) -> None:
        self.state = CLOSED
        self.failures = 0
        self.opened_at = None

    def record_failure(self) -> None:
        self.failures += 1
        if self.state == HALF_OPEN or self.failures >= self.fail_threshold:
            self.state = OPEN
            self.opened_at = self._clock()


def bucket_for(rate_limit: dict | None, **kw) -> TokenBucket | None:
    if not rate_limit:
        return None
    return TokenBucket(rate_limit.get("per_second", 1.0),
                       rate_limit.get("burst"), **kw)
