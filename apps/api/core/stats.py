"""No number leaves this module without its uncertainty attached."""
import math

Z = 1.959963984540054  # 95%


def wilson(k, n, z=Z):
    """Wilson score interval for a proportion. Correct at small n and at the
    boundaries, where the normal approximation is not."""
    if n == 0:
        return (0.0, 0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / d
    return (p, max(0.0, centre - half), min(1.0, centre + half))


def count_interval(k, n_sampled, n_population=None):
    """Scale a sampled count to a population estimate with an interval.

    When the sampling fraction is unknown (X at a hard read cap against an
    unknown true volume) we return None rather than a point estimate. A count
    we cannot bound is not a count we may display.
    """
    if n_population is None or n_sampled == 0:
        return None
    p, lo, hi = wilson(k, n_sampled)
    return (p * n_population, lo * n_population, hi * n_population)


def fmt_pct(k, n):
    if n == 0:
        return "not estimable"
    p, lo, hi = wilson(k, n)
    half = max(p - lo, hi - p) * 100
    return f"{p*100:.1f}% \u00b1 {half:.1f}"


def estimable(n_independent_sources):
    """Chao-style coverage estimation needs two independent sources on a
    surface. One source is not a smaller estimate, it is no estimate."""
    return n_independent_sources >= 2


def delta_is_real(k1, n1, k2, n2):
    """A change is only reportable when the intervals do not overlap."""
    _, lo1, hi1 = wilson(k1, n1)
    _, lo2, hi2 = wilson(k2, n2)
    return hi1 < lo2 or hi2 < lo1
