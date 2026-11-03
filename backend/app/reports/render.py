"""Renderers for the report document: HTML, DOCX, PDF, XLSX and CSV (zip)."""
from __future__ import annotations

import base64
import csv
import html
import io
import math
import zipfile

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from ..config import PDF_FONT, PDF_FONT_BOLD  # noqa: E402
from ..engine.utils import fp  # noqa: E402

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
except ImportError:  # pragma: no cover
    arabic_reshaper = None


def shape(text: str) -> str:
    """Visual-order Arabic shaping for engines without complex-script support (matplotlib, reportlab)."""
    if not text or arabic_reshaper is None or not any("؀" <= ch <= "ۿ" for ch in str(text)):
        return str(text)
    return get_display(arabic_reshaper.reshape(str(text)))


_MPL_NATIVE_SHAPING = tuple(int(x) for x in matplotlib.__version__.split(".")[:2]) >= (3, 11)


def mtxt(text) -> str:
    """matplotlib >= 3.11 shapes complex scripts itself; older versions need manual reshaping."""
    return str(text) if _MPL_NATIVE_SHAPING else shape(text)


def fmt_cell(v, f=None) -> str:
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "✓" if v else "✗"
    if isinstance(v, list):
        return " | ".join(fmt_cell(x) for x in v)
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if isinstance(v, float) and math.isnan(v):
            return "—"
        if f == "p":
            return fp(v).replace("= ", "")
        if f and f.isdigit():
            return f"{v:.{int(f)}f}"
        if isinstance(v, float):
            return f"{v:.3f}" if abs(v) < 1000 else f"{v:.1f}"
        return str(v)
    return str(v)


def table_matrix(tb: dict, lang: str) -> tuple[list[str], list[list[str]]]:
    cols = tb["columns"]
    head = [c["ar"] if lang == "ar" else c["en"] for c in cols]
    rows = []
    for r in tb["rows"]:
        row = []
        for c in cols:
            key = c["key"]
            if lang == "ar" and key.endswith("_en") and key[:-3] + "_ar" in r:
                key = key[:-3] + "_ar"
            row.append(fmt_cell(r.get(key), c.get("fmt")))
        rows.append(row)
    return head, rows


# --------------------------------------------------------------------------------------------
# Figures: Plotly JSON spec -> matplotlib PNG (bar, scatter/line, histogram, box, heatmap, pie)
# --------------------------------------------------------------------------------------------


def chart_png(chart: dict, lang: str, dpi: int = 130) -> bytes | None:
    fig_spec = chart.get("figure") or {}
    data = fig_spec.get("data") or []
    if not data:
        return None
    plt.rcParams["font.family"] = "DejaVu Sans"
    fig, ax = plt.subplots(figsize=(7, 3.8))
    try:
        layout = fig_spec.get("layout", {})
        stacked = layout.get("barmode") == "stack"
        bars = [t for t in data if t.get("type") == "bar"]
        offset = None
        for i, t in enumerate(data):
            typ = t.get("type", "scatter")
            name = mtxt(str(t.get("name", "")))
            if typ == "bar":
                horiz = t.get("orientation") == "h"
                cats = [mtxt(str(c)) for c in (t.get("y") if horiz else t.get("x")) or []]
                vals = np.array([v if v is not None else 0 for v in (t.get("x") if horiz else t.get("y")) or []], dtype=float)
                pos = np.arange(len(cats))
                if stacked:
                    base = offset if offset is not None and len(offset) == len(vals) else np.zeros(len(vals))
                    (ax.barh if horiz else ax.bar)(pos, vals, 0.7, base, label=name) if not horiz else ax.barh(pos, vals, 0.7, left=base, label=name)
                    offset = base + vals
                else:
                    w = 0.8 / max(1, len(bars))
                    k = bars.index(t)
                    if horiz:
                        ax.barh(pos + k * w - 0.4 + w / 2, vals, w, label=name)
                    else:
                        ax.bar(pos + k * w - 0.4 + w / 2, vals, w, label=name)
                if horiz:
                    ax.set_yticks(pos, cats, fontsize=7)
                    ax.invert_yaxis() if i == 0 else None
                else:
                    ax.set_xticks(pos, cats, rotation=30 if len(cats) > 5 else 0, ha="right" if len(cats) > 5 else "center", fontsize=8)
            elif typ == "histogram":
                x = [v for v in t.get("x", []) if v is not None]
                ax.hist(x, bins="auto", density=t.get("histnorm") == "probability density", alpha=0.75, label=name)
            elif typ == "scatter":
                x, y = t.get("x", []), t.get("y", [])
                mode = t.get("mode", "markers")
                if t.get("line", {}).get("shape") == "hv":
                    ax.step(x, y, where="post", label=name)
                elif "lines" in mode:
                    ax.plot(x, y, "-o" if "markers" in mode else "-", ms=3, label=name, linestyle="--" if t.get("line", {}).get("dash") else "-")
                else:
                    ax.scatter(x, y, s=10, alpha=0.6, label=name)
            elif typ in ("box", "violin"):
                y = [v for v in t.get("y", []) if v is not None]
                ax.boxplot([y], positions=[i], widths=0.6)
                ax.set_xticks(range(len(data)), [mtxt(str(tt.get("name", ""))) for tt in data])
            elif typ == "heatmap":
                z = np.array([[np.nan if v is None else v for v in row] for row in t["z"]], dtype=float)
                im = ax.imshow(z, cmap="RdBu_r", vmin=t.get("zmin", -1), vmax=t.get("zmax", 1))
                ax.set_xticks(range(len(t["x"])), [mtxt(s) for s in t["x"]], rotation=45, ha="right", fontsize=7)
                ax.set_yticks(range(len(t["y"])), [mtxt(s) for s in t["y"]], fontsize=7)
                if z.shape[0] <= 12:
                    for a in range(z.shape[0]):
                        for b in range(z.shape[1]):
                            if not np.isnan(z[a, b]):
                                ax.text(b, a, f"{z[a, b]:.2f}", ha="center", va="center", fontsize=6)
                fig.colorbar(im, ax=ax, shrink=0.8)
            elif typ == "pie":
                ax.pie(t["values"], labels=[mtxt(str(l)) for l in t["labels"]], autopct="%1.1f%%", textprops={"fontsize": 7})
                ax.axis("equal")
            elif typ == "scatterpolar":
                plt.close(fig)
                fig = plt.figure(figsize=(5, 4))
                ax = fig.add_subplot(projection="polar")
                th = np.linspace(0, 2 * np.pi, len(t["r"]))
                ax.plot(th, t["r"])
                ax.fill(th, t["r"], alpha=0.25)
                ax.set_xticks(th[:-1], [mtxt(s) for s in t["theta"][:-1]], fontsize=7)
        for axis in ("xaxis", "yaxis"):
            ttl = (layout.get(axis) or {}).get("title", {})
            if isinstance(ttl, dict) and ttl.get("text"):
                (ax.set_xlabel if axis == "xaxis" else ax.set_ylabel)(mtxt(ttl["text"]), fontsize=8)
        if len(data) > 1 and not any(t.get("type") in ("pie", "heatmap", "box", "violin") for t in data):
            ax.legend(fontsize=7)
        ax.set_title(mtxt(chart.get("title_ar" if lang == "ar" else "title_en", "")), fontsize=10)
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=dpi)
        return buf.getvalue()
    except Exception:  # noqa: BLE001 - a figure must never break a report
        return None
    finally:
        plt.close("all")


# --------------------------------------------------------------------------------------------
def render_html(doc: dict) -> bytes:
    lang = doc["lang"]
    rtl = lang == "ar"
    out = [f"""<!doctype html><html lang="{lang}" dir="{'rtl' if rtl else 'ltr'}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(doc['title'])}</title>
<style>
body{{font-family:'Noto Naskh Arabic','Amiri','Segoe UI',Tahoma,Arial,sans-serif;max-width:980px;margin:32px auto;padding:0 16px;color:#1f2937;line-height:1.7}}
h1{{color:#1e3a8a;margin-bottom:0}} h2{{color:#1e3a8a;border-bottom:2px solid #c7d2fe;padding-bottom:4px;margin-top:36px}}
.sub{{color:#475569}} .notice{{background:#fef3c7;border:1px solid #f59e0b;padding:10px 14px;border-radius:8px;font-weight:600}}
table{{border-collapse:collapse;width:100%;margin:10px 0 4px;font-size:13px}} caption{{text-align:start;font-style:italic;margin-bottom:4px;font-weight:600}}
th{{border-top:2px solid #111;border-bottom:1px solid #111;padding:4px 6px;text-align:start;background:#f8fafc}}
td{{padding:3px 6px;border-bottom:1px solid #e5e7eb}} tr:last-child td{{border-bottom:2px solid #111}}
.note{{font-size:12px;color:#475569;margin-bottom:14px}} figure{{margin:14px 0;text-align:center}} img{{max-width:100%}}
.meta{{font-size:12px;color:#64748b}}
</style></head><body>
<h1>{html.escape(doc['title'])}</h1><p class="sub">{html.escape(doc['subtitle'])}</p><p class="meta">Research Analytics AI · {doc['generated_at']}</p>"""]
    if doc.get("notice"):
        out.append(f'<p class="notice">{html.escape(doc["notice"])}</p>')
    tno = fno = 0
    for s in doc["sections"]:
        out.append(f"<h2>{html.escape(s['heading'])}</h2>")
        for b in s["blocks"]:
            if b["type"] == "p":
                out.append(f"<p>{html.escape(b['text'])}</p>")
            elif b["type"] == "bullets":
                out.append("<ul>" + "".join(f"<li>{html.escape(i)}</li>" for i in b["items"]) + "</ul>")
            elif b["type"] == "table":
                tno += 1
                tb = b["table"]
                head, rows = table_matrix(tb, lang)
                cap = ("جدول" if rtl else "Table") + f" {tno}: " + (tb.get("title_ar") if rtl else tb.get("title_en"))
                out.append(f"<table><caption>{html.escape(cap)}</caption><thead><tr>" + "".join(f"<th>{html.escape(h)}</th>" for h in head) + "</tr></thead><tbody>")
                out += ["<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in r) + "</tr>" for r in rows]
                out.append("</tbody></table>")
                note = tb.get("note_ar") if rtl else tb.get("note_en")
                if note:
                    out.append(f'<div class="note"><em>{"ملاحظة" if rtl else "Note"}.</em> {html.escape(note)}</div>')
            elif b["type"] == "figure":
                png = chart_png(b["chart"], lang)
                if png:
                    fno += 1
                    cap = ("شكل" if rtl else "Figure") + f" {fno}: " + (b["chart"].get("title_ar") if rtl else b["chart"].get("title_en"))
                    out.append(f'<figure><img alt="{html.escape(cap)}" src="data:image/png;base64,{base64.b64encode(png).decode()}"><figcaption>{html.escape(cap)}</figcaption></figure>')
    out.append("</body></html>")
    return "\n".join(out).encode("utf-8")


def render_docx(doc: dict) -> bytes:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Inches, Pt

    lang = doc["lang"]
    rtl = lang == "ar"
    d = Document()
    st = d.styles["Normal"]
    st.font.name = "Arial"
    st.font.size = Pt(11)

    def bidi(p):
        if rtl:
            pPr = p._p.get_or_add_pPr()
            el = OxmlElement("w:bidi")
            el.set(qn("w:val"), "1")
            pPr.append(el)
            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            for r in p.runs:
                rPr = r._r.get_or_add_rPr()
                e = OxmlElement("w:rtl")
                e.set(qn("w:val"), "1")
                rPr.append(e)
        return p

    bidi(d.add_heading(doc["title"], 0))
    bidi(d.add_paragraph(f"{doc['subtitle']} — {doc['generated_at']}"))
    if doc.get("notice"):
        p = d.add_paragraph()
        r = p.add_run(doc["notice"])
        r.bold = True
        bidi(p)
    tno = fno = 0
    for s in doc["sections"]:
        bidi(d.add_heading(s["heading"], 1))
        for b in s["blocks"]:
            if b["type"] == "p":
                bidi(d.add_paragraph(b["text"]))
            elif b["type"] == "bullets":
                for it in b["items"]:
                    bidi(d.add_paragraph(it, style="List Bullet"))
            elif b["type"] == "table":
                tno += 1
                tb = b["table"]
                head, rows = table_matrix(tb, lang)
                cap = d.add_paragraph()
                cap.add_run(("جدول" if rtl else "Table") + f" {tno}").bold = True
                bidi(cap)
                c2 = d.add_paragraph()
                c2.add_run(tb.get("title_ar") if rtl else tb.get("title_en")).italic = True
                bidi(c2)
                t = d.add_table(rows=1, cols=len(head))
                t.style = "Table Grid"
                if rtl:
                    tblPr = t._tbl.tblPr
                    el = OxmlElement("w:bidiVisual")
                    el.set(qn("w:val"), "1")
                    tblPr.append(el)
                for i, h in enumerate(head):
                    cell = t.rows[0].cells[i]
                    cell.text = h
                    for r in cell.paragraphs[0].runs:
                        r.bold = True
                        r.font.size = Pt(8)
                for row in rows[:400]:
                    cells = t.add_row().cells
                    for i, v in enumerate(row):
                        cells[i].text = v
                        for r in cells[i].paragraphs[0].runs:
                            r.font.size = Pt(8)
                note = tb.get("note_ar") if rtl else tb.get("note_en")
                if note:
                    np_ = d.add_paragraph()
                    np_.add_run(("ملاحظة. " if rtl else "Note. ")).italic = True
                    np_.add_run(note).font.size = Pt(9)
                    bidi(np_)
            elif b["type"] == "figure":
                png = chart_png(b["chart"], lang)
                if png:
                    fno += 1
                    d.add_picture(io.BytesIO(png), width=Inches(6))
                    bidi(d.add_paragraph(("شكل" if rtl else "Figure") + f" {fno}: " + (b["chart"].get("title_ar") if rtl else b["chart"].get("title_en"))))
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def render_pdf(doc: dict) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Image, ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    try:
        pdfmetrics.registerFont(TTFont("RA", PDF_FONT))
        pdfmetrics.registerFont(TTFont("RA-B", PDF_FONT_BOLD))
        font, bold = "RA", "RA-B"
    except Exception:  # noqa: BLE001
        font, bold = "Helvetica", "Helvetica-Bold"
    lang = doc["lang"]
    rtl = lang == "ar"
    al = TA_RIGHT if rtl else TA_LEFT
    S = {"t": ParagraphStyle("t", fontName=bold, fontSize=18, leading=24, alignment=al, textColor=colors.HexColor("#1e3a8a")),
         "h": ParagraphStyle("h", fontName=bold, fontSize=13, leading=18, alignment=al, spaceBefore=12, spaceAfter=6, textColor=colors.HexColor("#1e3a8a")),
         "p": ParagraphStyle("p", fontName=font, fontSize=9.5, leading=14, alignment=al, spaceAfter=5),
         "n": ParagraphStyle("n", fontName=font, fontSize=8, leading=11, alignment=al, textColor=colors.HexColor("#475569"), spaceAfter=8),
         "c": ParagraphStyle("c", fontName=font, fontSize=7, leading=9, alignment=al),
         "ch": ParagraphStyle("ch", fontName=bold, fontSize=7, leading=9, alignment=al)}

    def P(text, style="p"):
        return Paragraph(html.escape(shape(text)), S[style])

    story = [P(doc["title"], "t"), P(f"{doc['subtitle']} — {doc['generated_at']}", "n")]
    if doc.get("notice"):
        story.append(Table([[P(doc["notice"])]], style=[("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fef3c7")), ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#f59e0b"))]))
    tno = fno = 0
    width = A4[0] - 3 * cm
    for s in doc["sections"]:
        story.append(P(s["heading"], "h"))
        for b in s["blocks"]:
            if b["type"] == "p":
                story.append(P(b["text"]))
            elif b["type"] == "bullets":
                story.append(ListFlowable([ListItem(P(i)) for i in b["items"]], bulletType="bullet", leftIndent=12))
            elif b["type"] == "table":
                tno += 1
                tb = b["table"]
                head, rows = table_matrix(tb, lang)
                if rtl:
                    head, rows = head[::-1], [r[::-1] for r in rows]
                story.append(P(("جدول" if rtl else "Table") + f" {tno}: " + (tb.get("title_ar") if rtl else tb.get("title_en")), "ch"))
                data = [[P(h, "ch") for h in head]] + [[P(c, "c") for c in r] for r in rows[:300]]
                t = Table(data, repeatRows=1, colWidths=[width / max(1, len(head))] * len(head))
                t.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, 0), 1, colors.black), ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.black),
                                       ("LINEBELOW", (0, -1), (-1, -1), 1, colors.black), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                       ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9"))]))
                story.append(t)
                note = tb.get("note_ar") if rtl else tb.get("note_en")
                if note:
                    story.append(P(("ملاحظة. " if rtl else "Note. ") + note, "n"))
                else:
                    story.append(Spacer(1, 6))
            elif b["type"] == "figure":
                png = chart_png(b["chart"], lang)
                if png:
                    fno += 1
                    story.append(Image(io.BytesIO(png), width=15 * cm, height=8.1 * cm))
                    story.append(P(("شكل" if rtl else "Figure") + f" {fno}: " + (b["chart"].get("title_ar") if rtl else b["chart"].get("title_en")), "n"))
    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=1.5 * cm, rightMargin=1.5 * cm, topMargin=1.5 * cm, bottomMargin=1.5 * cm,
                      title=doc["title"], author="Research Analytics AI").build(story)
    return buf.getvalue()


def _sheet_name(name: str, used: set) -> str:
    base = "".join(ch for ch in name if ch not in "[]:*?/\\")[:28] or "Sheet"
    n, i = base, 1
    while n in used:
        i += 1
        n = f"{base[:25]}_{i}"
    used.add(n)
    return n


def render_xlsx(doc: dict, data_frames: dict | None = None) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    lang = doc["lang"]
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    ws.sheet_view.rightToLeft = lang == "ar"
    ws.append([doc["title"]])
    ws.append([doc["subtitle"], doc["generated_at"]])
    if doc.get("notice"):
        ws.append([doc["notice"]])
        ws.cell(ws.max_row, 1).font = Font(bold=True, color="B45309")
    ws["A1"].font = Font(bold=True, size=14)
    used = {"Summary"}
    for s in doc["sections"]:
        ws.append([])
        ws.append([s["heading"]])
        ws.cell(ws.max_row, 1).font = Font(bold=True, size=12)
        for b in s["blocks"]:
            if b["type"] == "p":
                ws.append([b["text"]])
            elif b["type"] == "bullets":
                for i in b["items"]:
                    ws.append(["• " + i])
            elif b["type"] == "table":
                tb = b["table"]
                head, rows = table_matrix(tb, lang)
                sh = wb.create_sheet(_sheet_name(tb.get("title_en") or tb["id"], used))
                sh.sheet_view.rightToLeft = lang == "ar"
                sh.append([tb.get("title_ar") if lang == "ar" else tb.get("title_en")])
                sh["A1"].font = Font(bold=True)
                sh.append(head)
                for c in sh[2]:
                    c.font = Font(bold=True)
                    c.fill = PatternFill("solid", fgColor="E0E7FF")
                for r in tb["rows"]:
                    vals = []
                    for c in tb["columns"]:
                        v = r.get(c["key"])
                        vals.append(v if isinstance(v, (int, float, str)) or v is None else fmt_cell(v))
                    sh.append(vals)
                note = tb.get("note_ar") if lang == "ar" else tb.get("note_en")
                if note:
                    sh.append([])
                    sh.append([note])
                ws.append([f"→ {sh.title}"])
    for name, df in (data_frames or {}).items():
        sh = wb.create_sheet(_sheet_name(name, used))
        sh.append(list(map(str, df.columns)))
        for row in df.itertuples(index=False):
            sh.append([None if (isinstance(v, float) and math.isnan(v)) else (v if isinstance(v, (int, float, str)) else str(v)) for v in row])
    ws.column_dimensions["A"].width = 120
    for row in ws.iter_rows():
        for c in row:
            c.alignment = Alignment(wrap_text=True, horizontal="right" if lang == "ar" else "left")
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def render_csv_zip(doc: dict, data_frames: dict | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        tno = 0
        for s in doc["sections"]:
            for b in s["blocks"]:
                if b["type"] == "table":
                    tno += 1
                    tb = b["table"]
                    sio = io.StringIO()
                    w = csv.writer(sio)
                    w.writerow([c["key"] for c in tb["columns"]])
                    for r in tb["rows"]:
                        w.writerow([r.get(c["key"]) for c in tb["columns"]])
                    z.writestr(f"tables/{tno:02d}_{tb['id']}.csv", "﻿" + sio.getvalue())
        for name, df in (data_frames or {}).items():
            z.writestr(f"data/{name}.csv", "﻿" + df.to_csv(index=True, index_label="row_id"))
        z.writestr("README.txt", f"{doc['title']}\n{doc['subtitle']}\n{doc['generated_at']}\n" + (doc.get("notice") or ""))
    return buf.getvalue()
