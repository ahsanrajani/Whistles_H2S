"""Measured collection spend from the call log, next to the modelled figure."""
from db.analytics import cost as q

from .. import sources


def cost(db, ws, scenario):
    """Measured spend from the call log, next to the modelled monthly figure."""
    rows = q.measured_rows(db.session)
    measured = []
    for src, calls, units, spend, fails in rows:
        meta = sources.SOURCES.get(src, {})
        measured.append({"source": src, "label": meta.get("label", src),
                         "calls": calls, "units": units or 0,
                         "spend": spend or 0.0, "fails": fails or 0,
                         "unit_cost": meta.get("unit_cost", 0),
                         "unit": meta.get("unit", ""),
                         "note": meta.get("cost_note", "")})
    model = sources.SCENARIO_MODEL.get(scenario, sources.SCENARIO_MODEL["mid"])
    return measured, model
