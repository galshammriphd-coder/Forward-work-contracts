"""الرئيسية — executive dashboard."""
from __future__ import annotations

import streamlit as st

from analytics import statistics as stx
from browser import session_manager as sm
from dashboard import charts, ui
from database import db


def render() -> None:
    sess = sm.current_status()
    status_html = ui.badge(f"جلسة X: {sm.STATUS_LABELS_AR.get(sess['status'], sess['status'])}"
                           + (f" (@{sess['username']})" if sess["username"] else ""),
                           ui.STATUS_KIND.get(sess["status"], "muted"))
    ui.hero("Ghalib X Data Collector", "لوحة المعلومات التنفيذية — بيانات منصة X المجمعة محلياً", status_html)
    f = ui.filters_bar("home")
    df = stx.load_posts(**f)
    if df.empty and not db.fetch_value("SELECT COUNT(*) FROM posts", default=0):
        st.info("لا توجد بيانات بعد. ابدأ من «الاتصال بمنصة X» لتسجيل الدخول، ثم «إنشاء عملية جمع».")
        c1, c2 = st.columns(2)
        if c1.button("🔐 الانتقال إلى الاتصال بمنصة X", width="stretch"):
            st.session_state["nav_request"] = "الاتصال بمنصة X"
            st.rerun()
        if c2.button("➕ إنشاء عملية جمع", width="stretch"):
            st.session_state["nav_request"] = "إنشاء عملية جمع"
            st.rerun()
        return
    k = stx.kpis(df)
    ui.kpi_cards([
        ("إجمالي المنشورات", ui.fmt_num(k["total_posts"]), "ضمن المرشحات الحالية", "#2563EB"),
        ("الحسابات الفريدة", ui.fmt_num(k["unique_accounts"]), "", "#6366F1"),
        ("الهاشتاقات", ui.fmt_num(k["unique_hashtags"]), "وسوم فريدة", "#0EA5E9"),
        ("عمليات البحث", ui.fmt_num(k["total_jobs"]), "إجمالي العمليات", "#64748B"),
        ("آخر 24 ساعة", ui.fmt_num(k["last_24h"]), "حسب تاريخ النشر", "#10B981"),
        ("آخر 7 أيام", ui.fmt_num(k["last_7d"]), "حسب تاريخ النشر", "#14B8A6"),
        ("متوسط التفاعل", ui.fmt_num(k["avg_engagement"], 1),
         f"على {ui.fmt_num(k['engagement_available'])} منشوراً توفرت عداداته", "#F59E0B"),
        ("منشورات جديدة", ui.fmt_num(k["new_posts_24h"]), "جُمعت خلال 24 ساعة", "#EF4444"),
    ])
    if df.empty:
        st.warning("لا توجد منشورات مطابقة للمرشحات.")
        return
    freq = st.radio("دقة الزمن", ["ساعة", "يوم", "أسبوع", "شهر"], index=1, horizontal=True, key="home_freq")
    fmap = {"ساعة": "h", "يوم": "D", "أسبوع": "W", "شهر": "MS"}
    st.plotly_chart(charts.timeline(stx.posts_over_time(df, fmap[freq])), width="stretch")

    c1, c2 = st.columns(2)
    c1.plotly_chart(charts.languages_pie(stx.language_distribution(df)), width="stretch")
    c2.plotly_chart(charts.bar(stx.top_hashtags(df, 12), "hashtag", "posts", "أكثر الهاشتاقات استخداماً",
                               color=charts.COLORS[1]), width="stretch")
    c3, c4 = st.columns(2)
    ta = stx.top_accounts(df, 12)
    ta["label"] = "@" + ta["username"].astype(str)
    c3.plotly_chart(charts.bar(ta, "label", "posts", "أكثر الحسابات ظهوراً", color=charts.COLORS[5]),
                    width="stretch")
    c4.plotly_chart(charts.treemap_words(stx.top_words(df, 30)), width="stretch")
    c5, c6 = st.columns(2)
    c5.plotly_chart(charts.engagement_hist(stx.engagement_distribution(df)), width="stretch")
    jobs = db.read_df("SELECT j.id, j.name, COUNT(jp.post_id) AS posts FROM search_jobs j"
                      " LEFT JOIN job_posts jp ON jp.job_id = j.id GROUP BY j.id ORDER BY j.id DESC LIMIT 12")
    jobs["label"] = "#" + jobs["id"].astype(str) + " " + jobs["name"].str.slice(0, 25)
    c6.plotly_chart(charts.bar(jobs, "label", "posts", "مقارنة نتائج عمليات البحث", color=charts.COLORS[2]),
                    width="stretch")
    st.plotly_chart(charts.account_activity(stx.account_activity(df, 8)), width="stretch")
    st.plotly_chart(charts.heatmap(stx.hourly_heatmap(df)), width="stretch")
