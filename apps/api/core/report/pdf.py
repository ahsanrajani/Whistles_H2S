"""The designed two-page executive PDF, rendered from ``highlights(...)``.

reportlab only, guarded by ``PDF_OK`` so the rest of the API works without it.
The layout and palette match the portal's Studio Duotone look
(`apps/web/styles/globals.css`, light).
"""
import os

try:  # PDF is optional — the JSON highlights work regardless.
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate,
                                    Paragraph, Spacer, Table, TableStyle)
    from reportlab.graphics.charts.barcharts import HorizontalBarChart
    from reportlab.graphics.charts.piecharts import Pie
    from reportlab.graphics.shapes import Drawing, Rect, String
    PDF_OK = True
except Exception:  # pragma: no cover - env without reportlab
    PDF_OK = False

# ---- Studio Duotone palette (apps/web/styles/globals.css, light) ----
if PDF_OK:
    C_CARD = colors.HexColor("#ffffff")
    C_INK = colors.HexColor("#18181b")
    C_MUTE = colors.HexColor("#71717a")
    C_BORDER = colors.HexColor("#e4e4e7")
    C_PRIMARY = colors.HexColor("#6d5ef6")      # --primary (violet)
    C_HIGHLIGHT = colors.HexColor("#0891b2")    # --highlight (cyan) — the portal's other half
    C_SUCCESS = colors.HexColor("#059669")
    C_WARNING = colors.HexColor("#d97706")
    C_DANGER = colors.HexColor("#e11d48")
    C_NEUTRAL = colors.HexColor("#a1a1aa")
    # Competitor line palette, exactly as the Overview topic chart uses it
    # (core/insights/trends.py::_TREND_COLORS) — keeps the report's brand colours
    # identical to the dashboard's instead of inventing a purple-only scale.
    C_RIVALS = [colors.HexColor(c) for c in ("#2f6f8f", "#5b5f97", "#7d7a52", "#8a5a6d")]


def _esc(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_pdf(data):
    """Render `highlights(...)` to a designed two-page PDF. reportlab only."""
    if not PDF_OK:
        raise RuntimeError("reportlab is not installed")
    from io import BytesIO

    buf = BytesIO()
    w, h = A4
    lm = 16 * mm
    content_w = w - 2 * lm
    styles = _styles()
    # Same file the app-shell sidebar logo uses (apps/web/next.config.ts rewrites
    # /brand/:path* to the Flask static server's /static/brand/:path*).
    logo = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "static", "brand", "mark.png")
    has_logo = os.path.exists(logo)

    def _paint(canv, doc):
        first = doc.page == 1
        band_h = 26 * mm if first else 13 * mm
        canv.saveState()

        # White page, a slim duotone (violet → cyan) strip up top — the
        # dashboard itself is white/off-white with the brand colours kept to
        # thin accents, not a full-bleed colour block.
        canv.setFillColor(C_CARD)
        canv.rect(0, 0, w, h, fill=1, stroke=0)
        canv.saveState()
        path = canv.beginPath()
        path.rect(0, h - band_h, w, band_h)
        canv.clipPath(path, stroke=0, fill=0)
        try:
            canv.linearGradient(0, h, w, h, (C_PRIMARY, C_HIGHLIGHT), extend=True)
        except Exception:
            canv.setFillColor(C_PRIMARY)
            canv.rect(0, h - band_h, w, band_h, fill=1, stroke=0)
        canv.restoreState()

        if first:
            if has_logo:
                try:
                    canv.drawImage(logo, lm, h - 19 * mm, width=11 * mm, height=11 * mm,
                                   mask="auto", preserveAspectRatio=True)
                except Exception:
                    pass
            tx = lm + (15 * mm if has_logo else 0)
            canv.setFillColor(colors.Color(1, 1, 1, 0.78))
            canv.setFont("Helvetica-Bold", 7.5)
            canv.drawString(tx, h - 9.5 * mm, "G U R U   E A R S")
            canv.setFillColor(colors.white)
            canv.setFont("Helvetica-Bold", 16)
            canv.drawString(tx, h - 16.5 * mm, "Executive Highlights")
            canv.setFillColor(colors.Color(1, 1, 1, 0.85))
            canv.setFont("Helvetica", 8.5)
            canv.drawString(tx, h - 22 * mm,
                            f"{data['focus_brand'] or 'Focus brand'}   ·   "
                            f"generated {data['generated_at']}")
        else:
            if has_logo:
                try:
                    canv.drawImage(logo, lm, h - 10.5 * mm, width=7 * mm, height=7 * mm,
                                   mask="auto", preserveAspectRatio=True)
                except Exception:
                    pass
            canv.setFillColor(colors.white)
            canv.setFont("Helvetica-Bold", 10)
            canv.drawString(lm + (9 * mm if has_logo else 0), h - 8.5 * mm,
                            "Executive Highlights  ·  continued")

        canv.setStrokeColor(C_BORDER)
        canv.setLineWidth(0.6)
        canv.line(lm, 14 * mm, w - lm, 14 * mm)
        canv.setFillColor(C_MUTE)
        canv.setFont("Helvetica", 7)
        canv.drawString(lm, 10 * mm,
                        f"Guru Ears   ·   {data['generated_at']}   ·   Confidential")
        canv.drawRightString(w - lm, 10 * mm, f"Page {doc.page}")
        canv.restoreState()

    first_frame = Frame(lm, 16 * mm, content_w, h - 26 * mm - 18 * mm, id="body")
    rest_frame = Frame(lm, 16 * mm, content_w, h - 13 * mm - 18 * mm, id="body2")
    doc = BaseDocTemplate(buf, pagesize=A4, leftMargin=lm, rightMargin=lm,
                          topMargin=0, bottomMargin=16 * mm)
    doc.addPageTemplates([
        PageTemplate(id="first", frames=[first_frame], onPage=_paint),
        PageTemplate(id="rest", frames=[rest_frame], onPage=_paint),
    ])

    story = [Spacer(1, 4 * mm)]
    story += _kpi_row(data["numbers"], content_w, styles)
    story += [Spacer(1, 6 * mm)]
    story += _priorities_block(data["priorities"], content_w, styles)
    story += [Spacer(1, 6 * mm)]
    story += _charts_row(data, content_w, styles)
    story += [Spacer(1, 6 * mm)]
    story += _branch_block(data["worst_branches"], content_w, styles)
    if data["switch_samples"]:
        story += [Spacer(1, 6 * mm)]
        story += _quotes_block(data["switch_samples"], content_w, styles)

    doc.build(story)
    return buf.getvalue()


def _styles():
    base = ParagraphStyle("base", fontName="Helvetica", fontSize=9.5, leading=13,
                          textColor=C_INK, alignment=TA_LEFT)
    return {
        "kpi_label": ParagraphStyle("kl", parent=base, fontSize=6.5, leading=8,
                                    textColor=C_MUTE, fontName="Helvetica-Bold"),
        "kpi_value": ParagraphStyle("kv", parent=base, fontSize=15, leading=17,
                                    fontName="Helvetica-Bold"),
        "section": ParagraphStyle("sec", parent=base, fontSize=8, leading=10,
                                  textColor=C_PRIMARY, fontName="Helvetica-Bold",
                                  spaceAfter=4),
        "pri_title": ParagraphStyle("pt", parent=base, fontSize=9.5, leading=12,
                                    fontName="Helvetica-Bold"),
        "chip": ParagraphStyle("ch", parent=base, fontSize=7.5, leading=9,
                               textColor=C_MUTE, alignment=2),
        "cell": ParagraphStyle("cl", parent=base, fontSize=8.5, leading=11),
        "cell_mute": ParagraphStyle("cm", parent=base, fontSize=7.5, leading=9,
                                    textColor=C_MUTE),
        "th": ParagraphStyle("th", parent=base, fontSize=7, leading=9,
                             fontName="Helvetica-Bold", textColor=C_INK),
        "quote": ParagraphStyle("q", parent=base, fontSize=9, leading=13,
                                fontName="Helvetica-Oblique", textColor=C_INK),
        "quote_meta": ParagraphStyle("qm", parent=base, fontSize=7, leading=9,
                                     textColor=C_MUTE),
        "legend": ParagraphStyle("lg", parent=base, fontSize=8, leading=11),
        "muted": ParagraphStyle("mt", parent=base, fontSize=8, leading=11, textColor=C_MUTE),
    }


def _section(text, styles):
    return Paragraph(text.upper(), styles["section"])


def _swatch(colour, width=3.2, height=13):
    d = Drawing(width, height)
    d.add(Rect(0, 1, width, height - 2, rx=1.4, ry=1.4, fillColor=colour, strokeColor=None))
    return d


def _kpi_row(n, width, styles):
    tiles = [
        ("MENTIONS", f"{n['mentions']:,}"),
        ("NEGATIVE SHARE", f"{n['negative_share_pct']}%" if n["negative_share_pct"] is not None else "—"),
        ("LIKELY TO SWITCH", str(n["switch_at_risk"])),
        ("COMPLAINTS C / H", f"{n['triage_critical']} / {n['triage_high']}"),
        ("BRANCHES", str(n["branches_flagged"])),
        ("SCAM FLAG RATE", f"{n['scam_flag_rate_pct']}%"),
    ]
    cells = [[Paragraph(lbl, styles["kpi_label"]), Spacer(1, 3),
              Paragraph(val, styles["kpi_value"])] for lbl, val in tiles]
    col = width / 6.0
    t = Table([cells], colWidths=[col] * 6, rowHeights=[21 * mm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (-1, -1), C_CARD),
        ("BOX", (0, 0), (-1, -1), 0.6, C_BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.6, C_BORDER),
        ("LINEABOVE", (0, 0), (-1, 0), 2, C_PRIMARY),
    ]))
    return [t]


def _priorities_block(prios, width, styles):
    out = [_section("Priorities — act on these", styles)]
    if not prios:
        out.append(Paragraph("Nothing is firing. All monitored surfaces are within threshold.",
                             styles["muted"]))
        return out
    rows, style = [], [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (0, -1), 0),
        ("LEFTPADDING", (1, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]
    for i, pr in enumerate(prios):
        swatch = C_DANGER if pr["severity"] == "critical" else C_WARNING if pr["severity"] == "warning" else C_NEUTRAL
        rows.append([
            _swatch(swatch),
            Paragraph(f"<b>{_esc(pr['title'])}</b><br/>"
                      f"<font size=8 color='#71717a'>{_esc(pr['detail'])}</font>",
                      styles["pri_title"]),
            Paragraph(pr["when"] or "", styles["chip"]),
        ])
        if i:
            style.append(("LINEABOVE", (0, i), (-1, i), 0.6, C_BORDER))
    t = Table(rows, colWidths=[5 * mm, width - 5 * mm - 26 * mm, 26 * mm])
    t.setStyle(TableStyle(style))
    out.append(t)
    return out


def _charts_row(data, width, styles):
    half = (width - 8 * mm) / 2.0
    left = [_section("Sentiment split", styles), _sentiment_donut(data["sentiment"]),
            _sentiment_legend(data["sentiment"], styles)]
    right = [_section("Share of voice", styles), _sov_chart(data["share_of_voice"], half, styles)]
    t = Table([[left, right]], colWidths=[half, half])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (0, 0), 0), ("RIGHTPADDING", (0, 0), (0, 0), 8),
        ("LEFTPADDING", (1, 0), (1, 0), 8), ("RIGHTPADDING", (1, 0), (1, 0), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return [t]


def _sentiment_donut(s):
    total = (s["pos"] + s["neu"] + s["neg"]) or 1
    d = Drawing(150, 116)
    pie = Pie()
    pie.x, pie.y, pie.width, pie.height = 22, 4, 106, 106
    pie.data = [max(s["pos"], 0.0001), max(s["neu"], 0.0001), max(s["neg"], 0.0001)]
    pie.innerRadiusFraction = 0.62
    pie.slices.strokeWidth = 0.5
    pie.slices.strokeColor = colors.white
    pie.slices[0].fillColor = C_SUCCESS
    pie.slices[1].fillColor = C_NEUTRAL
    pie.slices[2].fillColor = C_DANGER
    d.add(pie)
    pct = round(100 * s["pos"] / total)
    d.add(String(75, 58, f"{pct}%", fontName="Helvetica-Bold", fontSize=17,
                 fillColor=C_INK, textAnchor="middle"))
    d.add(String(75, 46, "positive", fontName="Helvetica", fontSize=7.5,
                 fillColor=C_MUTE, textAnchor="middle"))
    return d


def _sentiment_legend(s, styles):
    return Paragraph(
        f"<font color='#059669'>●</font> Positive {s['pos']}&nbsp;&nbsp;&nbsp;"
        f"<font color='#a1a1aa'>●</font> Neutral {s['neu']}&nbsp;&nbsp;&nbsp;"
        f"<font color='#e11d48'>●</font> Negative {s['neg']}",
        styles["legend"])


def _sov_chart(sov, width, styles):
    if not sov:
        return Paragraph("No brand mentions yet.", styles["muted"])
    names = [b["name"] for b in sov]
    d = Drawing(width, 20 * len(names) + 18)
    bc = HorizontalBarChart()
    bc.x, bc.y = 58, 8
    bc.width = max(60, width - 58 - 40)
    bc.height = 20 * len(names)
    bc.data = [[b["pct"] for b in sov]]
    bc.strokeColor = None
    bc.bars.strokeWidth = 0
    bc.barSpacing = 5
    bc.valueAxis.valueMin = 0
    bc.valueAxis.valueMax = max(10, min(100, max(b["pct"] for b in sov) * 1.15))
    bc.valueAxis.visible = False
    bc.categoryAxis.categoryNames = names
    bc.categoryAxis.labels.fontName = "Helvetica"
    bc.categoryAxis.labels.fontSize = 7.5
    bc.categoryAxis.labels.fillColor = C_INK
    bc.categoryAxis.labels.boxAnchor = "e"
    bc.categoryAxis.labels.dx = -4
    bc.categoryAxis.strokeColor = C_BORDER
    bc.categoryAxis.reverseDirection = 1
    bc.barLabels.fontName = "Helvetica-Bold"
    bc.barLabels.fontSize = 7.5
    bc.barLabels.fillColor = C_MUTE
    bc.barLabels.boxAnchor = "w"
    bc.barLabelFormat = "%0.1f%%"
    bc.barLabels.dx = 4
    rival = 0
    for i, b in enumerate(sov):
        if b["focus"]:
            bc.bars[(0, i)].fillColor = C_PRIMARY
        else:
            bc.bars[(0, i)].fillColor = C_RIVALS[rival % len(C_RIVALS)]
            rival += 1
    d.add(bc)
    return d


_ISSUE_LABEL = {
    "queue": "Queue / wait", "staff": "Staff behaviour", "atm_cash": "ATM / cash",
    "biometric": "Biometric", "system_down": "System down",
    "account_block": "Account blocked", "cheque": "Cheque / clearing",
    "mis_selling": "Mis-selling",
}


def _branch_block(branches, width, styles):
    out = [_section("Branches needing attention", styles)]
    if not branches:
        out.append(Paragraph("No branch is flagged in the current window.", styles["muted"]))
        return out
    head = [Paragraph(t, styles["th"]) for t in
            ("BRANCH", "RATING", "COMPLAINTS", "TOP ISSUE", "SCORE")]
    rows = [head]
    for b in branches:
        crit = (f"  <font color='#e11d48'>· {b['critical']} critical</font>"
                if b["critical"] else "")
        rows.append([
            Paragraph(f"<b>{_esc(b['name'])}</b><br/><font size=7 color='#71717a'>"
                      f"{_esc(b['city'])} · last flagged {b['when']}</font>", styles["cell"]),
            _rating_bar(b["mean_rating"]),
            Paragraph(f"{b['complaints']}{crit}", styles["cell"]),
            Paragraph(_ISSUE_LABEL.get(b["top_issue"], b["top_issue"] or "—"),
                      styles["cell_mute"]),
            _score_badge(b["score"], b["band"]),
        ])
    col1 = width - (30 * mm + 24 * mm + 26 * mm + 15 * mm)
    t = Table(rows, colWidths=[col1, 30 * mm, 24 * mm, 26 * mm, 15 * mm], repeatRows=1)
    # Plain white rows with hairline dividers — the same look the dashboard's own
    # tables use (see e.g. apps/web/components/branches-view.tsx), not a tinted card.
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, C_INK),
        ("LINEBELOW", (0, 1), (-1, -2), 0.5, C_BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    out.append(t)
    return out


def _rating_bar(rating):
    d = Drawing(64, 14)
    if rating is None:
        d.add(String(0, 4, "n/a", fontName="Helvetica", fontSize=7.5, fillColor=C_MUTE))
        return d
    fill = C_DANGER if rating <= 2.5 else C_WARNING if rating <= 3.5 else C_SUCCESS
    for i in range(5):
        d.add(Rect(i * 8, 4, 6, 6, rx=1, ry=1, strokeColor=None, fillColor=C_BORDER))
    for i in range(min(int(round(rating)), 5)):
        d.add(Rect(i * 8, 4, 6, 6, rx=1, ry=1, strokeColor=None, fillColor=fill))
    d.add(String(44, 3.5, f"{rating}", fontName="Helvetica-Bold", fontSize=8, fillColor=C_INK))
    return d


def _score_badge(score, band):
    colour = C_DANGER if band == "high" else C_WARNING if band == "elevated" else C_MUTE
    d = Drawing(26, 15)
    d.add(Rect(0, 1, 24, 13, rx=6, ry=6, strokeColor=None,
               fillColor=colors.Color(colour.red, colour.green, colour.blue, 0.14)))
    d.add(String(12, 4.5, str(score), fontName="Helvetica-Bold", fontSize=8.5,
                 fillColor=colour, textAnchor="middle"))
    return d


def _quotes_block(samples, width, styles):
    out = [_section("Likely to switch — in their words", styles)]
    for s in samples:
        cell = [Paragraph(f"“{_esc(s['text'])}”", styles["quote"]), Spacer(1, 2),
                Paragraph(f"{s['band']} · {s['when']}", styles["quote_meta"])]
        t = Table([[cell]], colWidths=[width])
        t.setStyle(TableStyle([
            ("LINEBEFORE", (0, 0), (0, 0), 2.5, C_PRIMARY),
            ("LEFTPADDING", (0, 0), (0, 0), 9), ("RIGHTPADDING", (0, 0), (0, 0), 6),
            ("TOPPADDING", (0, 0), (0, 0), 4), ("BOTTOMPADDING", (0, 0), (0, 0), 8),
        ]))
        out.append(t)
    return out
