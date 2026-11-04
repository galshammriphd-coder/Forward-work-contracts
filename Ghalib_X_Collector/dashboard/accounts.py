"""الحسابات — public account information and activity analysis."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from analytics import statistics as stx
from dashboard import charts, ui
from database import db


def accounts_table(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    g = df.groupby("username").agg(posts=("post_id", "count"), avg_engagement=("engagement", "mean"),
                                   total_engagement=("engagement", "sum"), avg_views=("views_count", "mean"),
                                   first_post=("published_date", "min"), last_post=("published_date", "max")).reset_index()
    acc = db.read_df("SELECT username, screen_name, display_name, profile_url, description, followers_count,"
                     " following_count, statuses_count, account_created_at, verified, location FROM accounts")
    out = g.merge(acc, on="username", how="left")
    topics = {}
    for u, sub in df.groupby("username"):
        tags = stx.top_hashtags(sub, 3)["hashtag"].tolist()
        words = stx.top_words(sub, 3)["word"].tolist()
        topics[u] = "، ".join(tags + words)
    out["topics"] = out["username"].map(topics)
    return out.sort_values(["posts", "total_engagement"], ascending=False)


def render() -> None:
    ui.hero("الحسابات", "المعلومات العامة المتاحة للحسابات وتحليل نشاطها في البيانات المجمعة")
    f = ui.filters_bar("acc")
    df = stx.load_posts(**f)
    if df.empty:
        st.info("لا توجد بيانات.")
        return
    t = accounts_table(df)
    st.subheader("الحسابات الأكثر ظهوراً في نتائج البحث")
    st.dataframe(
        t[["username", "display_name", "posts", "avg_engagement", "followers_count", "following_count",
           "account_created_at", "topics", "profile_url"]],
        hide_index=True, width="stretch", height=420,
        column_config={
            "username": "الحساب", "display_name": "الاسم الظاهر", "posts": "المنشورات المجمعة",
            "avg_engagement": st.column_config.NumberColumn("متوسط التفاعل", format="%.1f"),
            "followers_count": st.column_config.NumberColumn("المتابعون", format="%d"),
            "following_count": st.column_config.NumberColumn("يتابع", format="%d"),
            "account_created_at": "تاريخ الإنشاء", "topics": "أبرز الموضوعات",
            "profile_url": st.column_config.LinkColumn("الرابط", display_text="فتح"),
        })
    st.caption("المتابعون/تاريخ الإنشاء/الوصف تظهر عندما تتيحها X ضمن البيانات المستلمة؛ القيم الفارغة تعني «غير متاح».")
    st.divider()
    user = st.selectbox("تحليل حساب", t["username"].tolist(), format_func=lambda u: f"@{u}")
    a = t[t["username"] == user].iloc[0].to_dict()
    sub = df[df["username"] == user]
    st.markdown(f"### {a.get('display_name') or user}  ·  @{a.get('screen_name') or user}")
    if a.get("description"):
        st.write(a["description"])
    ui.kpi_cards([
        ("المتابعون", ui.fmt_num(a.get("followers_count")), "", "#2563EB"),
        ("يتابع", ui.fmt_num(a.get("following_count")), "", "#0EA5E9"),
        ("المنشورات المجمعة", ui.fmt_num(a["posts"]), f"{a['first_post']} ← {a['last_post']}", "#10B981"),
        ("متوسط التفاعل", ui.fmt_num(a.get("avg_engagement"), 1), "", "#F59E0B"),
    ])
    st.caption(f"تاريخ إنشاء الحساب: {a.get('account_created_at') or 'غير متاح'} · الموقع: {a.get('location') or 'غير متاح'}"
               f" · موثق: {'نعم' if a.get('verified') == 1 else ('لا' if a.get('verified') == 0 else 'غير متاح')}")
    if a.get("profile_url"):
        st.link_button("فتح الحساب في X", a["profile_url"])
    c1, c2 = st.columns(2)
    c1.plotly_chart(charts.timeline(stx.posts_over_time(sub, "D"), "نشاط الحساب عبر الزمن"), width="stretch")
    c2.plotly_chart(charts.bar(stx.top_hashtags(sub, 10), "hashtag", "posts", "هاشتاقات الحساب",
                               color=charts.COLORS[1]), width="stretch")
    c3, c4 = st.columns(2)
    c3.plotly_chart(charts.bar(stx.top_words(sub, 12), "word", "count", "الكلمات الأكثر استخداماً",
                               color=charts.COLORS[2]), width="stretch")
    c4.plotly_chart(charts.heatmap(stx.hourly_heatmap(sub), "أوقات النشر"), width="stretch")
    st.subheader("منشورات الحساب (الأعلى تفاعلاً)")
    for r in sub.sort_values("engagement", ascending=False, na_position="last").head(15).to_dict("records"):
        ui.post_card(r)
