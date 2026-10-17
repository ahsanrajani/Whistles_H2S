"""Shared helper for the report surfaces."""
from ..insights import _age_days


def _ago(published_at):
    age = _age_days(published_at)
    if age is None:
        return "recently"
    if age <= 0:
        return "today"
    if age == 1:
        return "yesterday"
    if age < 14:
        return f"{age} days ago"
    if age < 60:
        return f"{age // 7} weeks ago"
    return f"{age // 30} months ago"
