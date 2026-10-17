"""Measured collection spend from the call log — behind core/insights/cost.py."""
from ._util import rows


def measured_rows(session):
    return rows(session, """SELECT source, SUM(calls), SUM(units),
                                   SUM(calls*unit_cost_usd), SUM(CASE WHEN ok=0 THEN 1 ELSE 0 END)
                            FROM call_log GROUP BY source ORDER BY 4 DESC""")
