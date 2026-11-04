"""التحليلات — sentiment, topics, keywords, entities, summaries, trends (all local)."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from analytics import statistics as stx
from analytics.entities import TYPE_LABELS_AR, analyze_entities, top_entities
from analytics.sentiment import LABELS_AR, analyze_posts, stored_sentiment, transformers_available
from analytics.summarization import abstractive_summary, extractive_summary
from analytics.topic_modeling import extract_keywords, latest_topic_run, run_topic_model
from analytics.trend_analysis import detect_trends, term_timeseries
from dashboard import charts, ui


def _engine_select(key: str, rules_label: str) -> str:
    opts = {"lexicon" if key == "sent" else "rules": rules_label}
    if transformers_available():
        opts["transformers"] = "نموذج Transformers محلي"
    return st.radio("المحرك", list(opts), format_func=opts.get, horizontal=True, key=f"{key}_engine")


def render() -> None:
    ui.hero("التحليلات والذكاء الاصطناعي", "تحليل اختياري يعمل محلياً بالكامل — لا تُرسل أي بيانات إلى خدمات خارجية")
    f = ui.filters_bar("an")
    df = stx.load_posts(**f)
    if df.empty:
        st.info("لا توجد بيانات للتحليل.")
        return
    st.caption(f"نطاق التحليل: {len(df):,} منشور")
    if not transformers_available():
        st.caption("نماذج Transformers غير مثبتة؛ تعمل المحركات المدمجة. لتفعيل النماذج: pip install -r requirements-ai.txt")
    allowed = ui.can("analyst")
    tabs = st.tabs(["المشاعر", "الموضوعات", "الكلمات المفتاحية", "الكيانات", "الملخص", "الاتجاهات"])

    with tabs[0]:
        eng = _engine_select("sent", "المعجم المدمج (عربي/إنجليزي)")
        if st.button("تشغيل تحليل المشاعر", disabled=not allowed, key="run_sent"):
            with st.spinner("جارٍ التحليل…"):
                try:
                    analyze_posts(df, engine=eng)
                    st.success("تم التحليل وحفظ النتائج")
                except Exception as exc:  # noqa: BLE001
                    st.error(str(exc))
        s = stored_sentiment(df["post_id"].tolist())
        if s.empty:
            st.info("لم يتم تحليل هذه المنشورات بعد.")
        else:
            dist = s["label"].value_counts().reindex(list(LABELS_AR)).fillna(0).astype(int).reset_index()
            dist.columns = ["label", "posts"]
            dist["label_ar"] = dist["label"].map(LABELS_AR)
            c1, c2 = st.columns(2)
            c1.plotly_chart(charts.sentiment_pie(dist), width="stretch")
            m = df[["post_id", "published_date"]].merge(s, on="post_id").dropna(subset=["published_date"])
            if not m.empty:
                t = m.groupby(["published_date", "label"]).size().reset_index(name="n")
                t["share"] = t["n"] / t.groupby("published_date")["n"].transform("sum") * 100
                t["label_ar"] = t["label"].map(LABELS_AR)
                c2.plotly_chart(charts.sentiment_stacked(t, "published_date", "اتجاه المشاعر يومياً"),
                                width="stretch")
            st.caption(f"المحركات المستخدمة: {', '.join(s['model'].unique())} · المعجم المدمج خط أساس ولا يلتقط السخرية والسياق.")
            lab = st.selectbox("عرض منشورات تصنيف", list(LABELS_AR), format_func=LABELS_AR.get)
            ids = set(s.loc[s["label"] == lab, "post_id"])
            for r in df[df["post_id"].isin(ids)].sort_values("engagement", ascending=False, na_position="last").head(8).to_dict("records"):
                ui.post_card(r)

    with tabs[1]:
        c1, c2 = st.columns(2)
        k = c1.slider("عدد الموضوعات", 2, 15, 6)
        nw = c2.slider("كلمات لكل موضوع", 4, 15, 8)
        if st.button("اكتشاف الموضوعات", disabled=not allowed):
            try:
                with st.spinner("جارٍ بناء النموذج…"):
                    res = run_topic_model(df, n_topics=k, n_words=nw)
                st.session_state["topics_res"] = res
            except ValueError as exc:
                st.warning(str(exc))
        res = st.session_state.get("topics_res")
        if res:
            tdf = pd.DataFrame([{"label": t["label"], "posts": t["posts"], "keywords": "، ".join(t["keywords"]),
                                 "topic_id": t["topic_id"]} for t in res["topics"]]).sort_values("posts", ascending=False)
            st.plotly_chart(charts.topic_bars(tdf), width="stretch")
            st.dataframe(tdf, hide_index=True, width="stretch")
            tid = st.selectbox("منشورات موضوع", tdf["topic_id"], format_func=lambda i: tdf.set_index("topic_id").loc[i, "label"])
            a = res["assignments"]
            ids = a[a["topic_id"] == tid].sort_values("weight", ascending=False)["post_id"].head(8)
            for r in df.set_index("post_id").loc[ids].reset_index().to_dict("records"):
                ui.post_card(r)
        else:
            last = latest_topic_run()
            if last:
                st.caption(f"آخر تشغيل محفوظ ({last['model']}، {last['created_at']}):")
                st.dataframe(last["topics"], hide_index=True, width="stretch")

    with tabs[2]:
        n = st.slider("عدد الكلمات", 10, 100, 30)
        kw = extract_keywords(df, n)
        if kw.empty:
            st.info("البيانات غير كافية.")
        else:
            c1, c2 = st.columns(2)
            c1.plotly_chart(charts.bar(kw.head(25), "keyword", "score", "الكلمات المفتاحية (TF-IDF)",
                                       color=charts.COLORS[2], height=600), width="stretch")
            c2.dataframe(kw, hide_index=True, width="stretch", height=600,
                         column_config={"keyword": "الكلمة/العبارة", "score": "الوزن", "documents": "عدد المنشورات"})

    with tabs[3]:
        eng = _engine_select("ner", "قواعد وأنماط عربية/إنجليزية")
        if st.button("استخراج الكيانات", disabled=not allowed):
            with st.spinner("جارٍ الاستخراج…"):
                try:
                    st.session_state["ents"] = analyze_entities(df, engine=eng)
                except Exception as exc:  # noqa: BLE001
                    st.error(str(exc))
        ents = st.session_state.get("ents")
        if ents is not None:
            if ents.empty:
                st.info("لم يتم العثور على كيانات.")
            else:
                cols = st.columns(3)
                for i, (typ, lab) in enumerate(TYPE_LABELS_AR.items()):
                    sub = ents[ents["entity_type"] == typ]
                    if sub.empty:
                        continue
                    te = top_entities(sub, 10).head(10)
                    cols[i % 3].plotly_chart(charts.bar(te, "entity", "posts", lab, color=charts.COLORS[i % 10], height=320),
                                             width="stretch")

    with tabs[4]:
        k = st.slider("عدد المنشورات في الملخص", 3, 15, 6)
        summ = extractive_summary(df, k=k)
        st.markdown("**ملخص استخلاصي:** أكثر المنشورات تمثيلاً لمحاور النقاش (مع التنوع)، وكل سطر منشور حقيقي برابطه.")
        for r in summ.to_dict("records"):
            st.markdown(f"- **@{r['username']}**: {r['text'][:400]}  [↗]({r['post_url']})")
        if transformers_available() and allowed and st.button("توليد ملخص بنموذج محلي (mT5)"):
            with st.spinner("قد يستغرق التحميل الأول وقتاً…"):
                try:
                    st.info(abstractive_summary(summ["text"].tolist()))
                except Exception as exc:  # noqa: BLE001
                    st.error(str(exc))

    with tabs[5]:
        c1, c2, c3 = st.columns(3)
        window = c1.selectbox("نافذة المقارنة", [1, 3, 7, 14, 30], index=0, format_func=lambda d: f"آخر {d} يوم مقابل ما قبلها")
        kind = c2.radio("النوع", ["words", "hashtags"], format_func={"words": "كلمات", "hashtags": "هاشتاقات"}.get, horizontal=True)
        minc = c3.number_input("أدنى تكرار", 1, 1000, 3)
        tr = detect_trends(df, window_days=window, kind=kind, min_count=minc)
        if tr.empty:
            st.info("لا توجد اتجاهات صاعدة بهذه الإعدادات (قد تحتاج بيانات أكثر أو نافذة أطول).")
        else:
            st.plotly_chart(charts.bar(tr.head(15), "term", "growth", "الموضوعات الصاعدة (معامل النمو)",
                                       color=charts.COLORS[4]), width="stretch")
            st.dataframe(tr, hide_index=True, width="stretch", column_config={
                "term": "المصطلح", "recent": "الفترة الحالية", "baseline": "الفترة السابقة",
                "recent_share": "النسبة الحالية", "baseline_share": "النسبة السابقة", "growth": "معامل النمو"})
            pick = st.multiselect("منحنى زمني للمصطلحات", tr["term"].tolist(), default=tr["term"].head(3).tolist())
            if pick:
                ts = term_timeseries(df, pick, "D")
                st.plotly_chart(charts.timeline(ts, "تطور المصطلحات", color="term"), width="stretch")
