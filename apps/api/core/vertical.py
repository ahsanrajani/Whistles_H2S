"""Which industry vocabulary a workspace's analytics should use.

A plain rule, returned to the caller so it is auditable: a focus brand whose name
says insurance / takaful / assurance is ``insurance``; everything else is
``banking`` (the original vocabulary). No model, no per-tenant setting to drift.
"""
import re

from db.analytics import dashboards as dq

_INSURANCE = re.compile(r"\b(insurance|takaful|assurance|life)\b", re.I)


def of_name(focus_name):
    return "insurance" if _INSURANCE.search(focus_name or "") else "banking"


def of(db, ws):
    return of_name(dq.focus_brand_name(db.session, ws))
