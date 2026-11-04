"""الهاشتاقات — hashtag database, Top Hashtags and per-hashtag analysis."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from analytics import statistics as stx
from analytics.trend_analysis import hashtag_growth
from dashboard import charts, ui
from database import db
from processing.pipeline import rebuild_hashtag_tables


def hashtag_table() -> pd.DataFrame:
    return db.read_df(
        "SELECT h.id, h.display_tag, h.tag, h.occurrences, h.post_count, h.first_seen, h.last_seen,"
        " (SELECT COUNT(DISTINCT p.username) FROM post_hashtags ph JOIN posts p ON p.post_id = ph.post_id"
        "  WHERE ph.hashtag_id = h.id) AS accounts"
        " FROM hashtags h ORDER BY h.post_count DESC")


def render() -> None:
    ui.hero("الهاشتاقات", "قاعدة بيانات الوسوم: الانتشار، الحسابات، الكلمات المرتبطة ومعدل النمو")
    t = hashtag_table()
    if t.empty:
        st.info("لا توجد هاشتاقات بعد. تُبنى هذه القاعدة تلقائياً بعد معالجة البيانات.")
        if ui.can("analyst") and st.button("إعادة بناء قاعدة الهاشتاقات"):
            rebuild_hashtag_tables()
            st.rerun()
        return
    c1, c2, c3 = st.columns(3)
    q = c1.text_input("تصفية بالاسم")
    min_posts = c2.number_input("أدنى عدد منشورات", 1, 100000, 1)
    order = c3.selectbox("الترتيب", ["عدد المنشورات", "عدد مرات الظهور", "الأحدث ظهوراً", "عدد الحسابات"])
    view = t[t["post_count"] >= min_posts]
    if q:
        view = view[view["display_tag"].str.contains(q, case=False, na=False) | view["tag"].str.contains(q, case=False, na=False)]
    col = {"عدد المنشورات": "post_count", "عدد مرات الظهور": "occurrences", "الأحدث ظهوراً": "last_seen",
           "عدد الحسابات": "accounts"}[order]
    view = view.sort_values(col, ascending=False)
    st.subheader("Top Hashtags")
    st.dataframe(view.drop(columns=["id"]), hide_index=True, width="stretch", height=380, column_config={
        "display_tag": "الهاشتاق", "tag": "الصيغة الموحدة", "occurrences": "مرات الظهور", "post_count": "المنشورات",
        "first_seen": "أول ظهور", "last_seen": "آخر ظهور", "accounts": "الحسابات"})
    st.plotly_chart(charts.bar(view.head(20).assign(h="#" + view.head(20)["display_tag"]), "h", "post_count",
                               "أكثر الهاشتاقات انتشاراً", color=charts.COLORS[1], height=520), width="stretch")
    st.divider()
    tag = st.selectbox("تحليل هاشتاق", view["tag"].tolist(),
                       format_func=lambda x: "#" + t.loc[t["tag"] == x, "display_tag"].iloc[0])
    df = stx.load_posts(hashtag=tag)
    row = t[t["tag"] == tag].iloc[0]
    ui.kpi_cards([
        ("مرات الظهور", ui.fmt_num(row["occurrences"]), "", "#2563EB"),
        ("المنشورات المرتبطة", ui.fmt_num(row["post_count"]), "", "#0EA5E9"),
        ("أول ظهور", str(row["first_seen"] or "—")[:16], "في البيانات", "#10B981"),
        ("آخر ظهور", str(row["last_seen"] or "—")[:16], "في البيانات", "#F59E0B"),
    ])
    freq = st.radio("الفترة", ["يوم", "أسبوع", "شهر"], horizontal=True, index=0, key="tag_freq")
    g = hashtag_growth(df, row["display_tag"], {"يوم": "D", "أسبوع": "W", "شهر": "MS"}[freq])
    c1, c2 = st.columns(2)
    c1.plotly_chart(charts.timeline(g[["period", "posts"]] if not g.empty else g, "معدل استخدام الهاشتاق عبر الزمن"),
                    width="stretch")
    if not g.empty:
        c1.caption("نسبة النمو بين الفترات المتتالية: " + "، ".join(
            f"{pd.Timestamp(p).date()}: {v:+.0f}%" for p, v in zip(g["period"].tail(6), g["growth_pct"].tail(6)) if pd.notna(v)))
    ta = stx.top_accounts(df, 10)
    ta["label"] = "@" + ta["username"].astype(str)
    c2.plotly_chart(charts.bar(ta, "label", "posts", "الحسابات الأكثر استخداماً له", color=charts.COLORS[5]),
                    width="stretch")
    c3, c4 = st.columns(2)
    c3.plotly_chart(charts.bar(stx.top_words(df, 15, exclude={row["display_tag"]}), "word", "count",
                               "الكلمات المرتبطة به", color=charts.COLORS[2]), width="stretch")
    co = stx.hashtag_cooccurrence(df, tag, 15)
    co["label"] = "#" + co["tag"]
    c4.plotly_chart(charts.bar(co, "label", "posts", "الهاشتاقات المرتبطة (تظهر معه)", color=charts.COLORS[0]),
                    width="stretch")
