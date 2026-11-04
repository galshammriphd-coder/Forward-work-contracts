"""التقارير — analytical reports exported to Excel and PDF."""
from __future__ import annotations

import streamlit as st

from dashboard import charts, ui
from exports.report_builder import build_report
from exports.service import export_report


def render() -> None:
    ui.hero("التقارير", "ملخص تنفيذي، معلومات البحث، الإحصائيات، الرسوم، الهاشتاقات، الحسابات، المشاعر، الموضوعات والاستنتاجات")
    opts = ui.job_options()
    c1, c2 = st.columns([2, 1])
    sel = c1.multiselect("عمليات الجمع المشمولة (فارغ = كل البيانات)", list(opts))
    title = c2.text_input("عنوان التقرير", value="تقرير تحليل بيانات منصة X")
    c3, c4, c5, c6 = st.columns(4)
    dfrom = c3.date_input("من تاريخ", value=None, key="rep_from")
    dto = c4.date_input("إلى تاريخ", value=None, key="rep_to")
    kw = c5.text_input("تقييد بكلمة", key="rep_kw")
    ntop = c6.number_input("عدد الموضوعات", 2, 12, 5)
    if st.button("إعداد التقرير", type="primary", disabled=not ui.can("analyst")):
        with st.spinner("جارٍ حساب محتوى التقرير…"):
            st.session_state["report"] = build_report(title, job_ids=[opts[s] for s in sel] or None, date_from=dfrom,
                                                      date_to=dto, keyword=kw or None, n_topics=int(ntop))
            st.session_state["report_jobs"] = [opts[s] for s in sel]
    rep = st.session_state.get("report")
    if not rep:
        return
    st.subheader(rep["title"])
    st.markdown("#### الملخص التنفيذي والاستنتاجات")
    for line in rep["conclusions"]:
        st.markdown(f"- {line}")
    if not rep.get("empty"):
        c1, c2 = st.columns(2)
        c1.plotly_chart(charts.timeline(rep["timeline"]), width="stretch")
        c2.plotly_chart(charts.sentiment_pie(rep["sentiment"]), width="stretch")
        c3, c4 = st.columns(2)
        c3.plotly_chart(charts.bar(rep["top_hashtags"], "hashtag", "posts", "أبرز الهاشتاقات", color=charts.COLORS[1]),
                        width="stretch")
        ta = rep["top_accounts"].assign(label=lambda d: "@" + d["username"].astype(str))
        c4.plotly_chart(charts.bar(ta, "label", "posts", "أبرز الحسابات", color=charts.COLORS[5]), width="stretch")
        if not rep["topics"].empty:
            st.markdown("#### الموضوعات الرئيسية")
            st.dataframe(rep["topics"], hide_index=True, width="stretch")
        else:
            st.caption(rep["topics_note"])
    st.markdown("#### تصدير")
    e1, e2 = st.columns(2)
    jobs = st.session_state.get("report_jobs") or []
    for col, fmt, lab in ((e1, "xlsx", "Excel"), (e2, "pdf", "PDF")):
        if col.button(f"تصدير التقرير {lab}", width="stretch", disabled=not ui.can("analyst")):
            with st.spinner("جارٍ إنشاء الملف…"):
                path = export_report(rep, fmt, rep["title"], job_id=jobs[0] if len(jobs) == 1 else None,
                                     actor=ui.current_user())
            col.success(f"تم الحفظ: {path}")
            col.download_button("تنزيل", path.read_bytes(), file_name=path.name, key=f"rep_dl_{fmt}")
