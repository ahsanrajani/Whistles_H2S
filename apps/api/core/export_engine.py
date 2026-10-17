"""Report export engine — CSV / Excel / PDF, with charts (build plan §6 / P4.8).

Every P4 report is a nested dict. ``document_from`` flattens one into a neutral
``Document`` — a title, a key/value ``meta`` block, and a list of ``tables``
(each optionally carrying a ``chart`` hint). ``to_csv`` / ``to_xlsx`` / ``to_pdf``
render that. Extends the reportlab / openpyxl usage already in
``core/case_export.py``; ``to_pdf`` and ``to_xlsx`` draw a bar/line chart for
any table that asks for one.
"""
import csv
import io

# key names whose value is a {label: number} or {label: {...}} map worth charting
_CHART_KEYS = {"distribution": "bar", "daily_volume": "line",
               "by_channel": "bar", "by_category": "bar",
               "series": "line", "groups": "bar", "by_media_type": "bar"}

_SCALAR = (str, int, float, bool, type(None))


def _is_row_list(v):
    return isinstance(v, list) and v and all(isinstance(x, dict) for x in v)


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _rows_from_mapping(v):
    """{k: scalar} -> [[k, scalar]]; {k: {..}} -> [[k, *inner values]]."""
    if all(isinstance(x, _SCALAR) for x in v.values()):
        return ["key", "value"], [[k, v[k]] for k in v]
    cols = ["key"]
    seen: list = []
    for inner in v.values():
        if isinstance(inner, dict):
            for ik in inner:
                if ik not in seen:
                    seen.append(ik)
    cols += seen
    rows = []
    for k, inner in v.items():
        if isinstance(inner, dict):
            rows.append([k] + [inner.get(ik) for ik in seen])
        else:
            rows.append([k] + [inner] + [None] * (len(seen) - 1))
    return cols, rows


def document_from(payload: dict, title: str) -> dict:
    meta: dict = {}
    tables: list = []

    for key, val in payload.items():
        if isinstance(val, _SCALAR):
            meta[key] = val
        elif _is_row_list(val):
            cols: list = []
            for r in val:
                for c in r:
                    if c not in cols:
                        cols.append(c)
            rows = [[r.get(c) for c in cols] for r in val]
            tables.append(_table(key, cols, rows))
        elif isinstance(val, dict):
            # a nested scalar map -> its own table; a deeper dict -> meta + table
            flat_scalars = {k: v for k, v in val.items() if isinstance(v, _SCALAR)}
            if flat_scalars and len(flat_scalars) == len(val):
                if key in _CHART_KEYS:
                    cols, rows = ["label", "value"], [[k, v] for k, v in val.items()]
                    tables.append(_table(key, cols, rows, chart=_CHART_KEYS[key]))
                else:
                    for k, v in val.items():
                        meta[f"{key}.{k}"] = v
            else:
                cols, rows = _rows_from_mapping(val)
                tables.append(_table(key, cols, rows,
                                     chart=_CHART_KEYS.get(key)))
        elif isinstance(val, list):
            tables.append(_table(key, ["value"], [[x] for x in val]))

    return {"title": title, "meta": meta, "tables": tables}


def _table(name, columns, rows, chart=None):
    t = {"name": name, "columns": list(columns), "rows": [list(r) for r in rows]}
    if chart:
        # first numeric column is the series; the first column is the category
        num_idx = next((i for i in range(1, len(columns))
                        if any(_num(r[i]) is not None for r in rows)), None)
        if num_idx is not None:
            t["chart"] = {"type": chart, "cat": 0, "val": num_idx}
    return t


# --- CSV ---------------------------------------------------------
def to_csv(doc: dict) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    if doc["meta"]:
        w.writerow(["#", doc["title"]])
        for k, v in doc["meta"].items():
            w.writerow([k, v])
        w.writerow([])
    for t in doc["tables"]:
        w.writerow([f"# {t['name']}"])
        w.writerow(t["columns"])
        w.writerows(t["rows"])
        w.writerow([])
    return buf.getvalue().encode("utf-8")


# --- XLSX --------------------------------------------------------
def to_xlsx(doc: dict) -> bytes:
    from openpyxl import Workbook
    from openpyxl.chart import BarChart, LineChart, Reference

    wb = Workbook()
    summary = wb.active
    summary.title = "Summary"
    summary.append(["report", doc["title"]])
    for k, v in doc["meta"].items():
        summary.append([k, _cell(v)])

    used = {"Summary"}
    for t in doc["tables"]:
        title = _sheet_name(t["name"], used)
        ws = wb.create_sheet(title)
        ws.append(t["columns"])
        for r in t["rows"]:
            ws.append([_cell(c) for c in r])
        ch = t.get("chart")
        if ch and len(t["rows"]) >= 1:
            chart = BarChart() if ch["type"] == "bar" else LineChart()
            chart.title = t["name"]
            data = Reference(ws, min_col=ch["val"] + 1, min_row=1,
                             max_row=len(t["rows"]) + 1)
            cats = Reference(ws, min_col=ch["cat"] + 1, min_row=2,
                             max_row=len(t["rows"]) + 1)
            chart.add_data(data, titles_from_data=True)
            chart.set_categories(cats)
            ws.add_chart(chart, f"{chr(ord('A') + len(t['columns']) + 1)}2")

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _cell(v):
    if isinstance(v, (list, dict)):
        import json
        return json.dumps(v)
    return v


def _sheet_name(name, used):
    base = "".join(c for c in name if c not in r"[]:*?/\\")[:28] or "sheet"
    title, i = base, 1
    while title in used:
        i += 1
        title = f"{base[:26]}_{i}"
    used.add(title)
    return title


# --- PDF --------------------------------------------------------
def to_pdf(doc: dict) -> bytes:
    from reportlab.graphics.charts.barcharts import VerticalBarChart
    from reportlab.graphics.charts.linecharts import HorizontalLineChart
    from reportlab.graphics.shapes import Drawing, String
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    x = 20 * mm
    y = h - 20 * mm

    def line(text, size=10, dy=6 * mm, bold=False):
        nonlocal y
        if y < 25 * mm:
            pdf.showPage()
            y = h - 20 * mm
        pdf.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        pdf.drawString(x, y, str(text)[:110])
        y -= dy

    line(doc["title"], size=16, dy=10 * mm, bold=True)
    for k, v in doc["meta"].items():
        line(f"{k}: {v}", size=9, dy=5 * mm)
    y -= 4 * mm

    for t in doc["tables"]:
        line(t["name"], size=12, dy=7 * mm, bold=True)
        line(" | ".join(str(c) for c in t["columns"]), size=8, dy=4.5 * mm)
        for r in t["rows"][:25]:
            line(" | ".join("" if c is None else str(c) for c in r),
                 size=8, dy=4.5 * mm)
        ch = t.get("chart")
        if ch:
            cats = [str(r[ch["cat"]]) for r in t["rows"][:12]]
            vals = [_num(r[ch["val"]]) or 0 for r in t["rows"][:12]]
            if any(vals):
                if y < 75 * mm:
                    pdf.showPage()
                    y = h - 20 * mm
                d = Drawing(400, 140)
                c = (VerticalBarChart() if ch["type"] == "bar"
                     else HorizontalLineChart())
                c.x, c.y, c.width, c.height = 30, 20, 340, 100
                c.data = [vals]
                c.categoryAxis.categoryNames = cats
                c.valueAxis.valueMin = 0
                d.add(c)
                d.add(String(0, 130, t["name"], fontSize=8))
                d.drawOn(pdf, x, y - 145)
                y -= 155
        y -= 3 * mm

    pdf.showPage()
    pdf.save()
    return buf.getvalue()


_RENDERERS = {"csv": (to_csv, "text/csv", "csv"),
              "xlsx": (to_xlsx,
                       "application/vnd.openxmlformats-officedocument."
                       "spreadsheetml.sheet", "xlsx"),
              "pdf": (to_pdf, "application/pdf", "pdf")}


def render(payload: dict, fmt: str, *, title: str):
    """(media_type, filename_ext, bytes) for a report payload in ``fmt``."""
    try:
        fn, media, ext = _RENDERERS[fmt]
    except KeyError:
        raise ValueError(f"unsupported export format: {fmt!r}")
    doc = document_from(payload, title)
    return media, ext, fn(doc)
