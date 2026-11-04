"""Excel (XLSX) exports with openpyxl: data workbooks and analytical reports with native charts."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, PieChart, Reference
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

import config
from database import db
from exports.common import posts_for_export

HEADER_FILL = PatternFill("solid", fgColor="1D4ED8")
HEADER_FONT = Font(bold=True, color="FFFFFF")
TITLE_FONT = Font(bold=True, size=14, color="1E3A8A")
_ILLEGAL = {chr(i) for i in range(32) if chr(i) not in "\t\n\r"}


def _cell(v):
    if v is None:
        return None
    if isinstance(v, float) and pd.isna(v):
        return None
    if isinstance(v, pd.Timestamp):
        return v.tz_localize(None).to_pydatetime() if v.tzinfo else v.to_pydatetime()
    if isinstance(v, str):
        v = "".join(ch for ch in v if ch not in _ILLEGAL)
        if v[:1] in ("=", "+", "-", "@") and len(v) > 1:
            v = "'" + v          # neutralise formula injection from post text
        return v[:32000]
    if hasattr(v, "item"):
        return v.item()
    return v


def _write_df(ws, df: pd.DataFrame, start_row: int = 1, start_col: int = 1, rtl: bool = True) -> tuple[int, int]:
    ws.sheet_view.rightToLeft = rtl
    for j, col in enumerate(df.columns, start=start_col):
        c = ws.cell(row=start_row, column=j, value=str(col))
        c.fill, c.font = HEADER_FILL, HEADER_FONT
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for i, row in enumerate(df.itertuples(index=False), start=start_row + 1):
        for j, v in enumerate(row, start=start_col):
            ws.cell(row=i, column=j, value=_cell(v))
    for j, col in enumerate(df.columns, start=start_col):
        sample = [len(str(col))] + [len(str(v)) for v in df[col].head(200).tolist()]
        ws.column_dimensions[get_column_letter(j)].width = min(max(sample) + 2, 60)
    if len(df):
        ws.auto_filter.ref = f"{get_column_letter(start_col)}{start_row}:{get_column_letter(start_col + len(df.columns) - 1)}{start_row + len(df)}"
    ws.freeze_panes = ws.cell(row=start_row + 1, column=start_col)
    return start_row + len(df), start_col + len(df.columns) - 1


def export_excel(df: pd.DataFrame, folder: Path, stem: str, meta: dict | None = None) -> Path:
    """Data workbook: Posts, Accounts, Hashtags, Summary sheets."""
    from analytics import statistics as st

    wb = Workbook()
    ws = wb.active
    ws.title = "Posts"
    _write_df(ws, posts_for_export(df))
    for r in range(2, ws.max_row + 1):
        ws.cell(row=r, column=2).alignment = Alignment(wrap_text=True, vertical="top")
    ws.column_dimensions["B"].width = 70

    accs = df["username"].dropna().unique().tolist()
    if accs:
        ph = ",".join("?" * len(accs))
        acc_df = db.read_df(
            f"SELECT username AS 'Username', display_name AS 'Display Name', profile_url AS 'Profile URL',"
            f" description AS 'Bio', followers_count AS 'Followers', following_count AS 'Following',"
            f" statuses_count AS 'Posts (profile)', account_created_at AS 'Account Created', verified AS 'Verified',"
            f" location AS 'Location' FROM accounts WHERE username IN ({ph})", accs)
        counts = df.groupby("username").agg(collected=("post_id", "count"), avg_eng=("engagement", "mean")).reset_index()
        acc_df = acc_df.merge(counts, left_on="Username", right_on="username", how="left").drop(columns="username")
        acc_df = acc_df.rename(columns={"collected": "Collected Posts", "avg_eng": "Avg Engagement"})
        _write_df(wb.create_sheet("Accounts"), acc_df.sort_values("Collected Posts", ascending=False))
    tags = st.top_hashtags(df, 1000)
    _write_df(wb.create_sheet("Hashtags"), tags.rename(columns={"hashtag": "Hashtag", "tag": "Normalized", "posts": "Posts"}))
    summ = wb.create_sheet("Summary")
    summ.sheet_view.rightToLeft = True
    summ["A1"] = config.APP_NAME
    summ["A1"].font = TITLE_FONT
    rows = [("تاريخ التصدير", db.utcnow()), ("عدد المنشورات", len(df)),
            ("عدد الحسابات", int(df["username"].nunique()) if len(df) else 0)]
    rows += [(str(k), str(v)) for k, v in (meta or {}).items()]
    for i, (k, v) in enumerate(rows, start=3):
        summ.cell(row=i, column=1, value=k).font = Font(bold=True)
        summ.cell(row=i, column=2, value=_cell(v))
    summ.column_dimensions["A"].width = 28
    summ.column_dimensions["B"].width = 60
    path = Path(folder) / f"{stem}.xlsx"
    wb.save(path)
    return path


def _bar(ws, title, data_ref_rows, col_cat, col_val, anchor, horizontal=False, color="1D4ED8"):
    first, last = data_ref_rows
    if last <= first:
        return
    ch = BarChart()
    ch.type = "bar" if horizontal else "col"
    ch.title = title
    ch.legend = None
    ch.height, ch.width = 8, 16
    ch.add_data(Reference(ws, min_col=col_val, min_row=first, max_row=last), titles_from_data=True)
    ch.set_categories(Reference(ws, min_col=col_cat, min_row=first + 1, max_row=last))
    ch.series[0].graphicalProperties.solidFill = color
    ws.add_chart(ch, anchor)


def export_report_excel(rep: dict, folder: Path, stem: str) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "الملخص التنفيذي"
    ws.sheet_view.rightToLeft = True
    ws["A1"] = rep["title"]
    ws["A1"].font = TITLE_FONT
    ws["A2"] = f"{config.APP_NAME} — {rep['generated_at']}"
    r = 4
    ws.cell(row=r, column=1, value="النطاق").font = Font(bold=True, size=12)
    for k, v in rep["scope"].items():
        r += 1
        ws.cell(row=r, column=1, value=k)
        ws.cell(row=r, column=2, value=", ".join(v) if isinstance(v, list) else str(v))
    r += 2
    ws.cell(row=r, column=1, value="النتائج والاستنتاجات").font = Font(bold=True, size=12)
    for line in rep["conclusions"]:
        r += 1
        ws.cell(row=r, column=1, value="• " + line).alignment = Alignment(wrap_text=True)
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=6)
        ws.row_dimensions[r].height = 32
    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 50
    if rep.get("empty"):
        path = Path(folder) / f"{stem}.xlsx"
        wb.save(path)
        return path

    k = rep["kpis"]
    st = wb.create_sheet("الإحصائيات")
    kp = pd.DataFrame([
        ("إجمالي المنشورات", k["total_posts"]), ("الحسابات الفريدة", k["unique_accounts"]),
        ("الهاشتاقات الفريدة", k["unique_hashtags"]), ("منشورات آخر 24 ساعة", k["last_24h"]),
        ("منشورات آخر 7 أيام", k["last_7d"]),
        ("متوسط التفاعل", round(k["avg_engagement"], 2) if k["avg_engagement"] is not None else "غير متاح"),
        *[(f"إجمالي {c}", v if v is not None else "غير متاح") for c, v in rep["metric_totals"].items()],
    ], columns=["المؤشر", "القيمة"])
    _write_df(st, kp)
    if rep.get("jobs"):
        _write_df(st, pd.DataFrame(rep["jobs"]), start_row=len(kp) + 4)

    tl = rep["timeline"].copy()
    ws_t = wb.create_sheet("تطور المنشورات")
    tl["period"] = pd.to_datetime(tl["period"]).dt.strftime("%Y-%m-%d")
    end, _ = _write_df(ws_t, tl.rename(columns={"period": "التاريخ", "posts": "المنشورات"}))
    if end > 1:
        lc = LineChart()
        lc.title, lc.height, lc.width = "تطور المنشورات عبر الزمن", 8, 18
        lc.add_data(Reference(ws_t, min_col=2, min_row=1, max_row=end), titles_from_data=True)
        lc.set_categories(Reference(ws_t, min_col=1, min_row=2, max_row=end))
        ws_t.add_chart(lc, "D2")

    for title, df, cat, val, color in (
        ("الهاشتاقات", rep["top_hashtags"][["hashtag", "posts"]], 1, 2, "0EA5E9"),
        ("الحسابات", rep["top_accounts"][["username", "posts", "avg_engagement", "followers"]], 1, 2, "6366F1"),
        ("الكلمات", rep["top_words"], 1, 2, "10B981"),
        ("توزيع التفاعل", rep["engagement_dist"], 1, 2, "F59E0B"),
    ):
        w = wb.create_sheet(title)
        end, last_col = _write_df(w, df)
        _bar(w, title, (1, end), cat, val, f"{get_column_letter(last_col + 2)}2", horizontal=title != "توزيع التفاعل", color=color)

    ws_l = wb.create_sheet("اللغات")
    end, _ = _write_df(ws_l, rep["languages"][["language", "posts"]])
    if end > 1:
        pc = PieChart()
        pc.title = "توزيع اللغات"
        pc.add_data(Reference(ws_l, min_col=2, min_row=1, max_row=end), titles_from_data=True)
        pc.set_categories(Reference(ws_l, min_col=1, min_row=2, max_row=end))
        ws_l.add_chart(pc, "D2")

    ws_s = wb.create_sheet("المشاعر")
    s = rep["sentiment"][["label_ar", "posts"]].rename(columns={"label_ar": "التصنيف", "posts": "المنشورات"})
    end, _ = _write_df(ws_s, s)
    ws_s.cell(row=end + 2, column=1, value="المحرك: " + rep["sentiment_note"])
    if s["المنشورات"].sum():
        pc = PieChart()
        pc.title = "تحليل المشاعر"
        pc.add_data(Reference(ws_s, min_col=2, min_row=1, max_row=end), titles_from_data=True)
        pc.set_categories(Reference(ws_s, min_col=1, min_row=2, max_row=end))
        ws_s.add_chart(pc, "D2")

    ws_tp = wb.create_sheet("الموضوعات")
    end, _ = _write_df(ws_tp, rep["topics"])
    ws_tp.cell(row=end + 2, column=1, value=rep["topics_note"])
    ws_h = wb.create_sheet("منشورات ممثلة")
    _write_df(ws_h, rep["highlights"])
    ws_h.column_dimensions["C"].width = 80
    if not rep["keywords"].empty:
        _write_df(wb.create_sheet("الكلمات المفتاحية"), rep["keywords"])
    path = Path(folder) / f"{stem}.xlsx"
    wb.save(path)
    return path
