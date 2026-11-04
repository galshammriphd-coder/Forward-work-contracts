"""المقارنات — compare keywords, hashtags, accounts, periods and jobs."""
from __future__ import annotations

import streamlit as st

from analytics import statistics as stx
from analytics.comparison import compare_groups
from dashboard import charts, ui

MODES = {"keywords": "كلمات مفتاحية", "hashtags": "هاشتاقات", "accounts": "حسابات", "periods": "فترتان زمنيتان",
         "jobs": "عمليات بحث"}


def render() -> None:
    ui.hero("المقارنات", "مقارنة الحجم والتفاعل والنمو والمشاعر والكلمات بين مجموعات من المنشورات")
    mode = st.radio("نوع المقارنة", list(MODES), format_func=MODES.get, horizontal=True)
    groups = {}
    if mode in ("keywords", "hashtags", "accounts"):
        raw = st.text_input("العناصر المراد مقارنتها (مفصولة بفواصل)",
                            placeholder={"keywords": "الذكاء الاصطناعي, التحول الرقمي",
                                         "hashtags": "#الذكاء_الاصطناعي, #رؤية_السعودية_2030",
                                         "accounts": "account1, account2"}[mode])
        items = [x.strip() for x in raw.replace("،", ",").split(",") if x.strip()]
        for it in items:
            if mode == "keywords":
                groups[it] = stx.load_posts(keyword=it)
            elif mode == "hashtags":
                groups["#" + it.lstrip("#")] = stx.load_posts(hashtag=it)
            else:
                groups["@" + it.lstrip("@")] = stx.load_posts(usernames=[it])
    elif mode == "periods":
        c1, c2 = st.columns(2)
        a = c1.date_input("الفترة الأولى", value=[], key="pa")
        b = c2.date_input("الفترة الثانية", value=[], key="pb")
        kw = st.text_input("تقييد بكلمة (اختياري)")
        if len(a) == 2 and len(b) == 2:
            groups[f"{a[0]} → {a[1]}"] = stx.load_posts(date_from=a[0], date_to=a[1], keyword=kw or None)
            groups[f"{b[0]} → {b[1]}"] = stx.load_posts(date_from=b[0], date_to=b[1], keyword=kw or None)
    else:
        opts = ui.job_options()
        sel = st.multiselect("اختر عمليتين أو أكثر", list(opts))
        for s in sel:
            groups[s.split(" (")[0]] = stx.load_posts(job_ids=[opts[s]])
    if len(groups) < 2:
        st.info("حدد عنصرين على الأقل للمقارنة.")
        return
    res = compare_groups(groups)
    s = res["summary"]
    st.dataframe(s, hide_index=True, width="stretch", column_config={
        "group": "المجموعة", "posts": "المنشورات", "accounts": "الحسابات", "avg_engagement": "متوسط التفاعل",
        "avg_views": "متوسط المشاهدات", "growth_pct": "نمو الاهتمام %"})
    st.caption("نمو الاهتمام: الفرق بين متوسط المنشورات اليومية في النصف الثاني والنصف الأول من الفترة.")
    c1, c2 = st.columns(2)
    c1.plotly_chart(charts.compare_bars(s, "group", "posts", "حجم المنشورات"), width="stretch")
    c2.plotly_chart(charts.compare_bars(s.dropna(subset=["avg_engagement"]), "group", "avg_engagement", "معدل التفاعل"),
                    width="stretch")
    st.plotly_chart(charts.timeline(res["timeline"], "نمو الاهتمام عبر الزمن", color="term"), width="stretch")
    st.plotly_chart(charts.sentiment_stacked(res["sentiment"], "group", "اتجاه المشاعر"), width="stretch")
    st.subheader("أكثر الحسابات ظهوراً في كل مجموعة")
    acc = res["accounts"]
    if not acc.empty:
        cols = st.columns(min(len(groups), 4))
        for i, (g, sub) in enumerate(acc.groupby("group", sort=False)):
            cols[i % len(cols)].markdown(f"**{g}**")
            cols[i % len(cols)].dataframe(sub[["username", "posts"]], hide_index=True, width="stretch")
    st.subheader("الكلمات المشتركة")
    st.write("، ".join(res["common_words"]) or "لا توجد كلمات مشتركة بين أعلى الكلمات")
    st.subheader("الاختلافات (كلمات مميزة لكل مجموعة)")
    for g, ws in res["distinctive_words"].items():
        st.markdown(f"**{g}:** " + ("، ".join(ws) or "—"))
