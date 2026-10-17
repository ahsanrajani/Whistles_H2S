"""Scheduled report distribution (build plan §6 / P4.9).

A ``report_schedule`` row binds one report (kind + format + params) to a cron
and a recipient list. ``upsert`` also registers a ``scheduled_task``
(``report:<id>``, kind ``report_email``); the worker calls ``run`` which builds
the report (P4.2–P4.7), renders it (P4.8 export engine) and mails it
(``integrations/email``). ``build_report`` is the single dispatch table shared
with ``GET /reports/export``.
"""
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from core import (care_reports, export_engine, metrics, mis, sla_reports,
                  social_reports, surveys)
from integrations import email
from jobs import runner

REPORT_KINDS = ("metrics", "sla", "csat", "complaints", "care_agents", "social",
                "mis_daily", "mis_closed")
_FORMATS = ("pdf", "xlsx", "csv")


class DeliveryError(ValueError):
    pass


def build_report(session, ws, kind, d0, d1, *, source=None, metric=None) -> dict:
    if kind == "metrics":
        if not source or not metric:
            raise DeliveryError("metrics report needs source and metric")
        return metrics.report(session, ws, source=source, metric=metric,
                              start=d0.isoformat(), end=d1.isoformat())
    if kind == "sla":
        return sla_reports.sla_report(session, ws, d0, d1)
    if kind == "csat":
        return surveys.csat_report(session, ws, d0, d1)
    if kind == "complaints":
        return surveys.complaint_report(session, ws, d0, d1)
    if kind == "care_agents":
        return care_reports.agent_report(session, ws, d0, d1)
    if kind == "social":
        if not source:
            raise DeliveryError("social report needs source")
        return social_reports.report(session, ws, source=source, start=d0, end=d1)
    if kind == "mis_daily":
        return mis.daily_case_counts(session, ws, d0, d1)
    if kind == "mis_closed":
        return mis.closed_case_report(session, ws, d0, d1)
    raise DeliveryError(f"unknown report kind {kind!r}")


# --- schedule CRUD ---------------------------------------------
def _validate(kind, fmt, recipients):
    if kind not in REPORT_KINDS:
        raise DeliveryError(f"kind must be one of {REPORT_KINDS}")
    if fmt not in _FORMATS:
        raise DeliveryError(f"format must be one of {_FORMATS}")
    if not isinstance(recipients, list) or not any((r or "").strip() for r in recipients):
        raise DeliveryError("at least one recipient is required")


def upsert(session, workspace_id, *, name, kind, cron, recipients, fmt="pdf",
           params=None, active=True, schedule_id=None, actor=None) -> int:
    _validate(kind, fmt, recipients)
    params = params or {}
    if schedule_id is None:
        sid = session.execute(text("""
            INSERT INTO report_schedule
                (workspace_id, name, kind, format, params, cron, recipients,
                 active, created_by)
            VALUES (:ws, :n, :k, :f, CAST(:p AS jsonb), :cr, CAST(:r AS jsonb),
                    :a, :by)
            RETURNING id
        """), {"ws": workspace_id, "n": name, "k": kind, "f": fmt,
               "p": json.dumps(params), "cr": cron,
               "r": json.dumps(recipients), "a": active, "by": actor}).scalar_one()
    else:
        n = session.execute(text("""
            UPDATE report_schedule SET
                name = :n, kind = :k, format = :f, params = CAST(:p AS jsonb),
                cron = :cr, recipients = CAST(:r AS jsonb), active = :a,
                updated_at = now()
            WHERE id = :id AND workspace_id = :ws
        """), {"id": schedule_id, "ws": workspace_id, "n": name, "k": kind,
               "f": fmt, "p": json.dumps(params), "cr": cron,
               "r": json.dumps(recipients), "a": active}).rowcount
        if not n:
            raise DeliveryError("schedule not found")
        sid = schedule_id

    runner.schedule(session, name=f"report:{sid}", cron_expr=cron,
                    kind="report_email",
                    payload={"ws": workspace_id, "schedule_id": int(sid)},
                    tenant_id=workspace_id)
    return int(sid)


def list_schedules(session, workspace_id) -> list[dict]:
    rows = session.execute(text("""
        SELECT id, name, kind, format, params, cron, recipients, active,
               last_run_at, last_status
        FROM report_schedule WHERE workspace_id = :ws ORDER BY id
    """), {"ws": workspace_id}).mappings().all()
    return [dict(r) for r in rows]


def delete(session, workspace_id, schedule_id) -> None:
    n = session.execute(text(
        "DELETE FROM report_schedule WHERE id = :id AND workspace_id = :ws"),
        {"id": schedule_id, "ws": workspace_id}).rowcount
    if not n:
        raise DeliveryError("schedule not found")
    session.execute(text(
        "UPDATE scheduled_task SET enabled = 0 WHERE name = :n"),
        {"n": f"report:{schedule_id}"})


# --- run ----------------------------------------------------
def run(session, workspace_id, schedule_id, *, now=None, keys=None,
        transport=None) -> dict:
    from core import features
    if not features.enabled(session, workspace_id, "cap.report_email"):
        raise DeliveryError("scheduled report email is turned off for this workspace")
    row = session.execute(text(
        "SELECT * FROM report_schedule WHERE id = :id AND workspace_id = :ws"),
        {"id": schedule_id, "ws": workspace_id}).mappings().first()
    if not row:
        raise DeliveryError("schedule not found")

    now = now or datetime.now(timezone.utc)
    params = row["params"] or {}
    window_days = int(params.get("window_days", 30))
    d1 = (now - timedelta(days=1)).date()
    d0 = d1 - timedelta(days=window_days - 1)

    payload = build_report(session, workspace_id, row["kind"], d0, d1,
                           source=params.get("source"), metric=params.get("metric"))
    media, ext, blob = export_engine.render(
        payload, row["format"], title=f"{row['name']} · {d0}..{d1}")

    result = email.send(
        to=list(row["recipients"] or []),
        subject=f"[Guru] {row['name']} ({d0} – {d1})",
        body=f"Automated {row['kind']} report for {d0} to {d1}. "
             f"See the attached {ext.upper()}.",
        attachments=[(f"{row['kind']}-report.{ext}", blob, media)],
        keys=keys, transport=transport)

    status = "delivered" if result.get("delivered") else "queued(mock)"
    session.execute(text(
        "UPDATE report_schedule SET last_run_at = :t, last_status = :s "
        "WHERE id = :id"), {"t": now, "s": status, "id": schedule_id})
    return {"schedule_id": schedule_id, "status": status,
            "window": {"start": d0.isoformat(), "end": d1.isoformat()},
            "recipients": list(row["recipients"] or []), "bytes": len(blob)}
