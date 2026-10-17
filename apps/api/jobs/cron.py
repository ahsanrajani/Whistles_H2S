"""A small 5-field cron evaluator — ``minute hour day-of-month month day-of-week``.

Supports ``*``, ``*/step``, ``a-b``, ``a-b/step`` and comma lists of those.
Day-of-month 1..31, day-of-week 0..6 with ``0`` = Sunday. When *both* the DOM
and DOW fields are restricted they are OR-ed (Vixie-cron semantics).

Enough for the scheduler (P1.8); not a general cron library, so no ``@``
macros, names (``MON``), ``L``/``W``/``#`` or seconds. Dependency-free on
purpose — the schedule maths stays auditable in-repo.
"""
from datetime import timedelta

# (name, low, high) for the five fields, in order
_FIELDS = (
    ("minute", 0, 59),
    ("hour", 0, 23),
    ("dom", 1, 31),
    ("month", 1, 12),
    ("dow", 0, 6),          # 0 = Sunday .. 6 = Saturday
)
_FULL = tuple(set(range(lo, hi + 1)) for _, lo, hi in _FIELDS)
# a year of minutes — the ceiling on how far next_after() will scan
_SCAN_LIMIT = 367 * 24 * 60


def _parse_field(spec, lo, hi):
    spec = (spec or "").strip()
    if not spec:
        raise ValueError("empty cron field")
    values: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        step = 1
        if "/" in part:
            part, _, step_s = part.partition("/")
            step = int(step_s)
        if part in ("*", ""):
            start, end = lo, hi
        elif "-" in part:
            start_s, _, end_s = part.partition("-")
            start, end = int(start_s), int(end_s)
        else:
            start = end = int(part)
        if step < 1 or start < lo or end > hi or start > end:
            raise ValueError(f"cron field out of range: {spec!r}")
        values.update(range(start, end + 1, step))
    return values


class Cron:
    """A parsed cron expression. ``matches(dt)`` is a set-membership test;
    ``next_after(dt)`` scans forward minute by minute."""

    __slots__ = ("expr", "minute", "hour", "dom", "month", "dow",
                 "_dom_restricted", "_dow_restricted")

    def __init__(self, expr: str):
        parts = (expr or "").split()
        if len(parts) != 5:
            raise ValueError(f"cron needs 5 fields, got {len(parts)}: {expr!r}")
        self.expr = expr
        (self.minute, self.hour, self.dom,
         self.month, self.dow) = (_parse_field(p, lo, hi)
                                  for p, (_, lo, hi) in zip(parts, _FIELDS))
        self._dom_restricted = self.dom != _FULL[2]
        self._dow_restricted = self.dow != _FULL[4]

    def matches(self, when) -> bool:
        # cron DOW: 0=Sunday..6=Saturday; datetime.weekday(): 0=Monday..6=Sunday
        py_dow = (when.weekday() + 1) % 7
        if self._dom_restricted and self._dow_restricted:
            day_ok = when.day in self.dom or py_dow in self.dow
        elif self._dow_restricted:
            day_ok = py_dow in self.dow
        else:
            day_ok = when.day in self.dom
        return (when.minute in self.minute and when.hour in self.hour
                and when.month in self.month and day_ok)

    def next_after(self, after):
        """The first minute strictly after ``after`` that matches. Preserves
        ``after``'s tzinfo."""
        cur = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
        for _ in range(_SCAN_LIMIT):
            if self.matches(cur):
                return cur
            cur += timedelta(minutes=1)
        raise ValueError(f"cron expression never matches within a year: {self.expr!r}")


def parse(expr: str) -> Cron:
    return Cron(expr)


def matches(expr: str, when) -> bool:
    return Cron(expr).matches(when)


def next_after(expr: str, after):
    return Cron(expr).next_after(after)
