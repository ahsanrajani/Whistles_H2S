"""Per-rule precision, the labelling-progress view, the review batch and the
exclusion-reason breakdown."""
from db.analytics import calibration as q

from ..stats import wilson

CALIBRATION_TARGET = 30


def rule_precision(db, ws):
    """Per-rule counts with measured precision where a gold set exists.

    An unmeasured rule reports its count as an upper bound, not a fact.
    """
    out = []
    for rule, n, review, labelled, correct in q.rule_precision_rows(db.session, ws):
        labelled = labelled or 0
        target = min(n, CALIBRATION_TARGET)
        entry = {"rule": rule, "n": n, "review": review or 0,
                 "labelled": labelled, "target": target,
                 "met": target > 0 and labelled >= target,
                 "precision": None, "lo": None, "hi": None}
        if labelled:
            p, lo, hi = wilson(correct or 0, labelled)
            entry.update({"precision": p, "lo": lo, "hi": hi})
        out.append(entry)
    return out


def calibration_status(db, ws):
    """Per-rule labelling progress against a sample target, with the measured
    precision so far. A rule under target has an upper-bound count, not a fact.
    """
    out = []
    for rule, n, gated, labelled, correct in q.calibration_status_rows(db.session, ws):
        labelled = labelled or 0
        target = min(n, CALIBRATION_TARGET)
        p = lo = hi = None
        if labelled:
            p, lo, hi = wilson(correct or 0, labelled)
        out.append({"rule": rule, "n": n, "gated": bool(gated),
                    "labelled": labelled, "correct": correct or 0,
                    "target": target, "remaining": max(0, target - labelled),
                    "met": target > 0 and labelled >= target,
                    "precision": p, "lo": lo, "hi": hi})
    return out


def review_batch(db, ws, per_rule=12):
    """Unlabelled mentions that actually need a human eye — gated rules and a
    slice of `exact_name` for the safe-rule precision floor. Identity rules
    (`app_review`, `meta_mention`) are the brand by construction and never enter
    the queue. Returns the same row shape as `feed`.
    """
    return q.review_batch_rows(db.session, ws, per_rule)


def exclusions(db, ws):
    # plain [reason, n] pairs -- a raw DB Row is not JSON-serialisable, which 500'd
    # the admin Overview as soon as any mention had been excluded
    return [list(r) for r in q.exclusion_rows(db.session, ws)]
