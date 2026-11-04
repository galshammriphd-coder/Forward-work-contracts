"""PDF report (reportlab) with Arabic shaping, RTL layout and vector charts."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from reportlab.graphics.charts.barcharts import HorizontalBarChart, VerticalBarChart
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

import config

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
except ImportError:  # pragma: no cover
    arabic_reshaper = None

PALETTE = [colors.HexColor(c) for c in ("#1D4ED8", "#0EA5E9", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6", "#64748B")]
_FONT = "Helvetica"


def _register_font() -> str:
    global _FONT
    if _FONT != "Helvetica":
        return _FONT
    path = config.pdf_font_path()
    if path:
        try:
            pdfmetrics.registerFont(TTFont("GhalibArabic", path))
            _FONT = "GhalibArabic"
        except Exception:
            pass
    return _FONT


def ar(text) -> str:
    """Shape Arabic letters and reorder for visual display (reportlab has no bidi)."""
    s = "" if text is None else str(text)
    if arabic_reshaper is None or not any("؀" <= ch <= "ۿ" for ch in s):
        return s
    return get_display(arabic_reshaper.reshape(s))


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


_TEXT_WIDTH = A4[0] - 3.2 * cm


def _wrap_logical(text: str, font: str, size: float, width: float) -> list[str]:
    """Break text into lines in logical order (before bidi reordering), so that
    multi-line Arabic paragraphs keep their line order."""
    lines: list[str] = []
    for para in str(text).split("\n"):
        cur = ""
        for word in para.split(" "):
            cand = f"{cur} {word}".strip()
            shaped = arabic_reshaper.reshape(cand) if arabic_reshaper else cand
            if cur and pdfmetrics.stringWidth(shaped, font, size) > width:
                lines.append(cur)
                cur = word
            else:
                cur = cand
        lines.append(cur)
    return lines


def _p(text, style) -> Paragraph:
    s = "" if text is None else str(text)
    if arabic_reshaper is None or not any("\u0600" <= ch <= "\u06FF" for ch in s):
        return Paragraph(_esc(s), style)
    lines = _wrap_logical(s, style.fontName, style.fontSize, _TEXT_WIDTH - 6)
    return Paragraph("<br/>".join(_esc(ar(line)) for line in lines), style)


def _table(df: pd.DataFrame, headers: list[str], font: str, col_widths=None, max_rows: int = 20) -> Table:
    body = [[ar(h) for h in reversed(headers)]]
    for row in df.head(max_rows).itertuples(index=False):
        vals = []
        for v in row:
            if v is None or (isinstance(v, float) and pd.isna(v)):
                vals.append("—")
            elif isinstance(v, float):
                vals.append(f"{v:,.1f}")
            else:
                s = str(v)
                vals.append(ar(s[:90] + ("…" if len(s) > 90 else "")))
        body.append(list(reversed(vals)))
    t = Table(body, colWidths=list(reversed(col_widths)) if col_widths else None, repeatRows=1)
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), font, 8.5),
        ("BACKGROUND", (0, 0), (-1, 0), PALETTE[0]),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F1F5F9")]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1")),
    ]))
    return t


def _hbar(labels, values, title, font, color=PALETTE[0], width=16 * cm, height=7 * cm) -> Drawing:
    d = Drawing(width, height)
    if not values:
        return d
    labels, values = list(reversed(labels)), list(reversed(values))
    ch = HorizontalBarChart()
    ch.x, ch.y, ch.width, ch.height = 4.2 * cm, 0.6 * cm, width - 5 * cm, height - 1.6 * cm
    ch.data = [values]
    ch.categoryAxis.categoryNames = [ar(str(l))[:28] for l in labels]
    ch.categoryAxis.labels.fontName = font
    ch.categoryAxis.labels.fontSize = 7
    ch.valueAxis.labels.fontName = font
    ch.valueAxis.valueMin = 0
    ch.bars[0].fillColor = color
    d.add(ch)
    d.add(String(width / 2, height - 0.5 * cm, ar(title), fontName=font, fontSize=10, textAnchor="middle"))
    return d


def _vbar(labels, values, title, font, width=16 * cm, height=6 * cm) -> Drawing:
    d = Drawing(width, height)
    if not values:
        return d
    ch = VerticalBarChart()
    ch.x, ch.y, ch.width, ch.height = 1.2 * cm, 1.0 * cm, width - 2 * cm, height - 2 * cm
    ch.data = [values]
    ch.categoryAxis.categoryNames = [ar(str(l)) for l in labels]
    ch.categoryAxis.labels.fontName = font
    ch.categoryAxis.labels.fontSize = 7
    ch.valueAxis.valueMin = 0
    ch.bars[0].fillColor = PALETTE[3]
    d.add(ch)
    d.add(String(width / 2, height - 0.5 * cm, ar(title), fontName=font, fontSize=10, textAnchor="middle"))
    return d


def _line(tl: pd.DataFrame, title, font, width=16 * cm, height=6 * cm) -> Drawing:
    d = Drawing(width, height)
    if tl.empty:
        return d
    lp = LinePlot()
    lp.x, lp.y, lp.width, lp.height = 1.2 * cm, 1.0 * cm, width - 2 * cm, height - 2 * cm
    pts = [(i, int(v)) for i, v in enumerate(tl["posts"].tolist())]
    lp.data = [pts if len(pts) > 1 else pts + [(1, pts[0][1])]]
    lp.lines[0].strokeColor = PALETTE[0]
    lp.lines[0].strokeWidth = 1.6
    lp.xValueAxis.valueMin = 0
    lp.yValueAxis.valueMin = 0
    dates = pd.to_datetime(tl["period"]).dt.strftime("%m-%d").tolist()
    step = max(1, len(dates) // 8)
    lp.xValueAxis.valueSteps = list(range(0, len(dates), step))
    lp.xValueAxis.labelTextFormat = lambda v: dates[int(v)] if 0 <= int(v) < len(dates) else ""
    lp.xValueAxis.labels.fontSize = 7
    d.add(lp)
    d.add(String(width / 2, height - 0.5 * cm, ar(title), fontName=font, fontSize=10, textAnchor="middle"))
    return d


def _pie(labels, values, title, font, width=16 * cm, height=6.5 * cm) -> Drawing:
    d = Drawing(width, height)
    if not values or sum(values) == 0:
        return d
    pie = Pie()
    pie.x, pie.y, pie.width, pie.height = width / 2 - 2.5 * cm, 0.4 * cm, 5 * cm, 5 * cm
    pairs = [(l, v) for l, v in zip(labels, values) if v]
    pie.data = [v for _, v in pairs]
    total = sum(pie.data)
    pie.labels = [f"{ar(l)} {v / total * 100:.0f}%" for l, v in pairs]
    pie.slices.fontName = font
    pie.slices.fontSize = 8
    for i in range(len(pairs)):
        pie.slices[i].fillColor = PALETTE[i % len(PALETTE)]
    d.add(pie)
    d.add(String(width / 2, height - 0.3 * cm, ar(title), fontName=font, fontSize=10, textAnchor="middle"))
    return d


def export_report_pdf(rep: dict, folder: Path, stem: str) -> Path:
    font = _register_font()
    h1 = ParagraphStyle("h1", fontName=font, fontSize=18, leading=26, alignment=TA_CENTER, textColor=PALETTE[0])
    h2 = ParagraphStyle("h2", fontName=font, fontSize=13, leading=20, alignment=TA_RIGHT, textColor=colors.HexColor("#1E3A8A"),
                        spaceBefore=10, spaceAfter=6)
    body = ParagraphStyle("b", fontName=font, fontSize=10, leading=16, alignment=TA_RIGHT)
    small = ParagraphStyle("s", fontName=font, fontSize=8, leading=12, alignment=TA_RIGHT, textColor=colors.HexColor("#475569"))
    path = Path(folder) / f"{stem}.pdf"
    doc = SimpleDocTemplate(str(path), pagesize=A4, rightMargin=1.6 * cm, leftMargin=1.6 * cm,
                            topMargin=1.5 * cm, bottomMargin=1.5 * cm, title=rep["title"], author=config.APP_NAME)
    els = [_p(rep["title"], h1), Paragraph(_esc(f"{config.APP_NAME} — {rep['generated_at']}"), ParagraphStyle(
        "c", parent=small, alignment=TA_CENTER)), Spacer(1, 10)]

    els.append(_p("الملخص التنفيذي", h2))
    for line in rep["conclusions"]:
        els.append(_p("• " + line, body))
    els.append(_p("معلومات عملية البحث", h2))
    scope = pd.DataFrame([(k, ", ".join(v) if isinstance(v, list) else v) for k, v in rep["scope"].items()],
                         columns=["البند", "القيمة"])
    scope["البند"] = scope["البند"].map({"jobs": "العمليات", "date_from": "من تاريخ", "date_to": "إلى تاريخ",
                                         "languages": "اللغات", "keyword": "كلمة التصفية"}).fillna(scope["البند"])
    els.append(_table(scope, ["البند", "القيمة"], font, [4 * cm, 13 * cm]))
    if rep.get("jobs"):
        jobs = pd.DataFrame(rep["jobs"])[["id", "name", "type", "query", "status", "received", "new", "duplicates"]]
        els.append(Spacer(1, 6))
        els.append(_table(jobs, ["رقم", "الاسم", "النوع", "عبارة البحث", "الحالة", "المستلمة", "الجديدة", "المكررة"], font))
    if rep.get("empty"):
        doc.build(els)
        return path

    k, tot = rep["kpis"], rep["metric_totals"]
    els.append(_p("إحصائيات المنشورات", h2))
    fmt = lambda v: "غير متاح" if v is None else (f"{v:,.1f}" if isinstance(v, float) else f"{v:,}")
    kp = pd.DataFrame([
        ("إجمالي المنشورات", fmt(k["total_posts"])), ("الحسابات الفريدة", fmt(k["unique_accounts"])),
        ("الهاشتاقات الفريدة", fmt(k["unique_hashtags"])), ("آخر 24 ساعة", fmt(k["last_24h"])),
        ("آخر 7 أيام", fmt(k["last_7d"])), ("متوسط التفاعل", fmt(k["avg_engagement"])),
        ("إجمالي الإعجابات", fmt(tot.get("likes_count"))), ("إجمالي إعادة النشر", fmt(tot.get("reposts_count"))),
        ("إجمالي الردود", fmt(tot.get("replies_count"))), ("إجمالي المشاهدات", fmt(tot.get("views_count"))),
    ], columns=["المؤشر", "القيمة"])
    els.append(_table(kp, ["المؤشر", "القيمة"], font, [8 * cm, 8 * cm]))
    els.append(Spacer(1, 8))
    els.append(_line(rep["timeline"], "تطور المنشورات عبر الزمن", font))
    lang = rep["languages"]
    els.append(_pie(lang["language"].tolist()[:6], lang["posts"].tolist()[:6], "توزيع اللغات", font))
    ed = rep["engagement_dist"]
    els.append(_vbar(ed["bucket"].tolist(), ed["posts"].tolist(), "توزيع التفاعل لكل منشور", font))

    els.append(PageBreak())
    els.append(_p("أبرز الهاشتاقات", h2))
    th = rep["top_hashtags"].head(12)
    els.append(_hbar(th["hashtag"].tolist(), th["posts"].tolist(), "عدد المنشورات لكل هاشتاق", font, PALETTE[1]))
    els.append(_p("أبرز الحسابات", h2))
    ta = rep["top_accounts"].head(12)
    els.append(_table(ta[["username", "display_name", "posts", "avg_engagement", "followers"]],
                      ["الحساب", "الاسم", "المنشورات", "متوسط التفاعل", "المتابعون"], font))
    els.append(_p("الكلمات الأكثر تكراراً", h2))
    tw = rep["top_words"].head(15)
    els.append(_hbar(tw["word"].tolist(), tw["count"].tolist(), "تكرار الكلمات", font, PALETTE[2]))

    els.append(PageBreak())
    els.append(_p("تحليل المشاعر", h2))
    s = rep["sentiment"]
    els.append(_pie(s["label_ar"].tolist(), s["posts"].tolist(), "توزيع المشاعر", font))
    els.append(_p("المحرك: " + rep["sentiment_note"], small))
    els.append(_p("الموضوعات الرئيسية", h2))
    if rep["topics"].empty:
        els.append(_p(rep["topics_note"], small))
    else:
        els.append(_table(rep["topics"][["topic", "label", "keywords", "posts"]],
                          ["#", "الموضوع", "الكلمات المميزة", "المنشورات"], font, [1 * cm, 4 * cm, 9.5 * cm, 2.5 * cm]))
        els.append(_p(rep["topics_note"], small))
    if not rep["highlights"].empty:
        els.append(_p("منشورات ممثلة للنقاش (ملخص استخلاصي)", h2))
        for r in rep["highlights"].itertuples():
            els.append(_p(f"@{r.username}: {str(r.text)[:280]}", body))
            els.append(Paragraph(_esc(str(r.post_url or "")), small))
            els.append(Spacer(1, 4))
    els.append(_p("النتائج والاستنتاجات", h2))
    for line in rep["conclusions"]:
        els.append(_p("• " + line, body))
    els.append(Spacer(1, 10))
    els.append(_p("جميع الأرقام محسوبة من البيانات المجمعة في قاعدة البيانات المحلية؛ العدادات غير المتاحة من X مستبعدة من المتوسطات.", small))
    doc.build(els)
    return path
