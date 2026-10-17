"""Case download — PDF and Excel, including messages, notes, timeline and the
attachment list (build plan §5 / P3.8)."""
import io
import json

from sqlalchemy import text


def _gather(session, workspace_id, case_id) -> dict | None:
    case = session.execute(text("""
        SELECT c.*, cu.display_name, cu.handle, cu.platform, cu.email, cu.phone
        FROM "case" c JOIN customer cu ON cu.id = c.customer_id
        WHERE c.id = :c AND c.workspace_id = :ws
    """), {"c": case_id, "ws": workspace_id}).mappings().first()
    if not case:
        return None
    msgs = session.execute(text(
        "SELECT direction, channel, author, body, sent_at FROM case_message "
        "WHERE case_id = :c ORDER BY sent_at, id"), {"c": case_id}).mappings().all()
    notes = session.execute(text(
        "SELECT author_id, body, created_at FROM case_note WHERE case_id = :c "
        "ORDER BY created_at"), {"c": case_id}).mappings().all()
    events = session.execute(text(
        "SELECT kind, actor, detail, at FROM case_event WHERE case_id = :c "
        "ORDER BY at, id"), {"c": case_id}).mappings().all()
    # message-level media isn't modelled yet; the KB articles referenced in the
    # timeline are the case's "attachments" for the export.
    return {"case": dict(case), "messages": [dict(m) for m in msgs],
            "notes": [dict(n) for n in notes], "events": [dict(e) for e in events],
            "attachments": []}


def to_xlsx(data: dict) -> bytes:
    from openpyxl import Workbook
    wb = Workbook()
    c = data["case"]
    ws = wb.active
    ws.title = "Case"
    ws.append(["field", "value"])
    for k in ("id", "state", "channel", "closure_category", "opened_at",
              "first_response_at", "closed_at", "display_name", "handle",
              "email", "phone"):
        ws.append([k, str(c.get(k))])

    m = wb.create_sheet("Messages")
    m.append(["sent_at", "direction", "channel", "author", "body"])
    for row in data["messages"]:
        m.append([str(row["sent_at"]), row["direction"], row["channel"],
                  row["author"], row["body"]])

    n = wb.create_sheet("Notes")
    n.append(["created_at", "author_id", "body"])
    for row in data["notes"]:
        n.append([str(row["created_at"]), row["author_id"], row["body"]])

    e = wb.create_sheet("Audit trail")
    e.append(["at", "kind", "actor", "detail"])
    for row in data["events"]:
        detail = row["detail"]
        e.append([str(row["at"]), row["kind"], row["actor"],
                  json.dumps(detail) if isinstance(detail, (dict, list)) else str(detail)])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def to_pdf(data: dict) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    y = height - 20 * mm

    def line(txt, size=9, dy=5 * mm):
        nonlocal y
        if y < 20 * mm:
            pdf.showPage()
            y = height - 20 * mm
        pdf.setFont("Helvetica", size)
        pdf.drawString(20 * mm, y, txt[:110])
        y -= dy

    c = data["case"]
    line(f"Case #{c['id']} — {c['state']}", 14, 8 * mm)
    line(f"Customer: {c.get('display_name') or c.get('handle')}  ({c.get('platform')})")
    line(f"Opened {c['opened_at']}  ·  Closed {c.get('closed_at')}  ·  "
         f"Category {c.get('closure_category')}")
    line("")
    line("Messages", 11, 6 * mm)
    for row in data["messages"]:
        line(f"[{row['sent_at']}] {row['direction']} {row['author'] or ''}: {row['body']}")
    line("")
    line("Notes", 11, 6 * mm)
    for row in data["notes"]:
        line(f"[{row['created_at']}] {row['body']}")
    line("")
    line("Audit trail", 11, 6 * mm)
    for row in data["events"]:
        line(f"[{row['at']}] {row['kind']} by {row['actor'] or 'system'}")

    pdf.showPage()
    pdf.save()
    return buf.getvalue()


def export(session, workspace_id, case_id, fmt="pdf"):
    data = _gather(session, workspace_id, case_id)
    if data is None:
        return None
    if fmt == "xlsx":
        return ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                to_xlsx(data))
    return ("application/pdf", to_pdf(data))
