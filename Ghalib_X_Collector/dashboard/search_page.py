"""محرك البحث + إنشاء عملية جمع."""
from __future__ import annotations

from datetime import date

import streamlit as st

from browser.browser_manager import BrowserBusy, BrowserError
from collectors import collection_manager as cm
from dashboard import ui
from database import db, models
from search.query_builder import POST_TYPE_LABELS_AR, SORT_LABELS_AR, SearchParams, build_queries, describe, split_list
from search.search_engine import engine

TYPE_TABS = {"hashtag": "# الهاشتاقات", "user": "@ اسم المستخدم", "keyword": "الكلمات المفتاحية", "advanced": "البحث المتقدم"}
LANGS = {"": "كل اللغات", "ar": "العربية", "en": "الإنجليزية", "fr": "الفرنسية", "es": "الإسبانية", "tr": "التركية",
         "ur": "الأردية", "fa": "الفارسية", "de": "الألمانية", "id": "الإندونيسية"}


def _d(v):
    if not v:
        return None
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def search_form(key: str, initial: dict | None = None) -> SearchParams | None:
    """Renders the search form; returns SearchParams (or None when invalid)."""
    p = SearchParams.from_dict(initial or {})
    types = list(TYPE_TABS)
    stype = st.radio("نوع البحث", types, index=types.index(p.search_type) if p.search_type in types else 2,
                     format_func=TYPE_TABS.get, horizontal=True, key=f"{key}_type")
    out = SearchParams(search_type=stype)
    if stype == "hashtag":
        out.hashtags = split_list(st.text_area(
            "الهاشتاقات (واحد في كل سطر أو مفصولة بفواصل)", value="\n".join(p.hashtags), key=f"{key}_tags",
            placeholder="#الذكاء_الاصطناعي\n#رؤية_السعودية_2030\n#ArtificialIntelligence"))
        out.hashtag_mode = st.radio("طريقة الجمع بين الهاشتاقات", ["any", "all", "separate"],
                                    format_func={"any": "أي منها (OR)", "all": "جميعها معاً (AND)",
                                                 "separate": "بحث مستقل لكل هاشتاق"}.get,
                                    index=["any", "all", "separate"].index(p.hashtag_mode), horizontal=True,
                                    key=f"{key}_tagmode")
        out.keywords = st.text_input("كلمات إضافية (اختياري)", value=p.keywords, key=f"{key}_kw")
    elif stype == "user":
        out.usernames = split_list(st.text_area(
            "أسماء المستخدمين أو روابط الحسابات", value="\n".join(p.usernames), key=f"{key}_users",
            placeholder="@SPAregions\nhttps://x.com/sdaia"))
        out.keywords = st.text_input("موضوع محدد داخل منشورات الحساب (اختياري)", value=p.keywords, key=f"{key}_kw",
                                     placeholder="الذكاء الاصطناعي")
        c1, c2 = st.columns(2)
        out.user_mode = c1.radio("فصل النتائج", ["separate", "combined"], horizontal=True,
                                 format_func={"separate": "استعلام مستقل لكل حساب", "combined": "استعلام واحد مجمع"}.get,
                                 index=0 if p.user_mode == "separate" else 1, key=f"{key}_umode")
        out.collect_profiles = c2.checkbox("جمع معلومات الحساب العامة من صفحة الملف الشخصي", value=p.collect_profiles,
                                           key=f"{key}_prof")
    else:
        out.keywords = st.text_input(
            "عبارة البحث", value=p.keywords, key=f"{key}_kw",
            placeholder='الذكاء الاصطناعي في السعودية   |   التحول الرقمي AND البيانات   |   "Artificial Intelligence"',
            help='يدعم: "عبارة محددة"، AND (ضمني)، OR، NOT أو -كلمة للاستبعاد، والأقواس.')
        if stype == "advanced":
            c1, c2 = st.columns(2)
            out.exact_phrase = c1.text_input("العبارة المطابقة تماماً", value=p.exact_phrase, key=f"{key}_exact")
            out.any_words = c2.text_input("أي من هذه الكلمات", value=p.any_words, key=f"{key}_any")
            c3, c4 = st.columns(2)
            out.hashtags = split_list(c3.text_input("الهاشتاق", value=" ".join(p.hashtags), key=f"{key}_atags"))
            out.usernames = split_list(c4.text_input("من الحساب", value=" ".join(p.usernames), key=f"{key}_ausers"))
            c5, c6 = st.columns(2)
            out.to_user = c5.text_input("رداً على الحساب", value=p.to_user, key=f"{key}_to")
            out.mention_user = c6.text_input("يذكر الحساب", value=p.mention_user, key=f"{key}_mention")
            c7, c8, c9 = st.columns(3)
            out.min_likes = c7.number_input("أدنى إعجابات", 0, 10_000_000, int(p.min_likes), key=f"{key}_minl")
            out.min_reposts = c8.number_input("أدنى إعادة نشر", 0, 10_000_000, int(p.min_reposts), key=f"{key}_minr")
            out.min_replies = c9.number_input("أدنى ردود", 0, 10_000_000, int(p.min_replies), key=f"{key}_minrep")
    out.exclude_words = st.text_input("كلمات مستبعدة (مفصولة بمسافة)", value=p.exclude_words, key=f"{key}_ex")
    c1, c2, c3, c4, c5 = st.columns(5)
    out.since = c1.date_input("تاريخ البداية", value=_d(p.since), key=f"{key}_since")
    out.until = c2.date_input("تاريخ النهاية", value=_d(p.until), key=f"{key}_until")
    out.lang = c3.selectbox("اللغة", list(LANGS), index=list(LANGS).index(p.lang) if p.lang in LANGS else 0,
                            format_func=LANGS.get, key=f"{key}_lang")
    out.post_type = c4.selectbox("نوع المنشور", list(POST_TYPE_LABELS_AR),
                                 index=list(POST_TYPE_LABELS_AR).index(p.post_type), format_func=POST_TYPE_LABELS_AR.get,
                                 key=f"{key}_ptype")
    out.sort = c5.selectbox("ترتيب النتائج", list(SORT_LABELS_AR), index=0 if p.sort == "live" else 1,
                            format_func=SORT_LABELS_AR.get, key=f"{key}_sort")
    out.since = out.since.isoformat() if out.since else None
    out.until = out.until.isoformat() if out.until else None
    try:
        queries = build_queries(out)
    except ValueError as exc:
        st.info(str(exc))
        return None
    st.markdown("**الاستعلامات التي ستُنفذ في X:**")
    for q in queries:
        st.code(q, language=None)
    return out


def render_search() -> None:
    ui.hero("محرك البحث", "صياغة استعلامات X المتقدمة، معاينتها في المتصفح، وحفظها أو تحويلها إلى عملية جمع")
    tab_x, tab_local = st.tabs(["البحث في منصة X", "البحث في قاعدة البيانات المحلية"])
    with tab_x:
        saved = models.list_saved_searches()
        initial = st.session_state.pop("search_initial", None)
        if saved:
            choice = st.selectbox("تحميل بحث محفوظ", ["—"] + [s["name"] for s in saved], key="load_saved")
            if choice != "—" and st.button("تحميل"):
                s = next(x for x in saved if x["name"] == choice)
                for k in list(st.session_state):
                    if k.startswith("srch_"):
                        del st.session_state[k]
                st.session_state["search_initial"] = s["params"]
                st.rerun()
        params = search_form("srch", initial)
        if params:
            c1, c2, c3 = st.columns(3)
            if c1.button("👁 عرض النتائج في نافذة المتصفح", width="stretch",
                         disabled=not ui.can("analyst")):
                try:
                    with st.spinner("فتح البحث في المتصفح…"):
                        engine.open_in_browser(params)
                    st.success("تم فتح نتائج البحث في نافذة المتصفح (صفحة «الاتصال بمنصة X» تعرض صورة منها).")
                except (BrowserBusy, BrowserError) as exc:
                    st.error(str(exc))
                except Exception as exc:  # noqa: BLE001
                    st.error(f"تعذر فتح المتصفح: {exc}")
            with c2.popover("💾 حفظ إعدادات البحث", width="stretch"):
                name = st.text_input("اسم البحث المحفوظ", value=describe(params)[:60])
                if st.button("حفظ", disabled=not ui.can("analyst")):
                    models.save_search(name, params.search_type, params.to_dict())
                    db.audit("search_saved", name, params.to_dict(), actor=ui.current_user())
                    st.success("تم الحفظ")
            if c3.button("➕ إنشاء عملية جمع بهذا البحث", width="stretch", type="primary",
                         disabled=not ui.can("analyst")):
                st.session_state["job_initial"] = params.to_dict()
                st.session_state["nav_request"] = "إنشاء عملية جمع"
                for k in list(st.session_state):
                    if k.startswith("job_") and k != "job_initial":
                        del st.session_state[k]
                st.rerun()
        if saved and ui.can("analyst"):
            with st.expander("إدارة عمليات البحث المحفوظة"):
                for s in saved:
                    a, b = st.columns([5, 1])
                    a.write(f"**{s['name']}** — {s['search_type']}")
                    if b.button("حذف", key=f"del_saved_{s['id']}"):
                        models.delete_saved_search(s["id"])
                        st.rerun()
    with tab_local:
        from analytics import statistics as stx
        q = st.text_input("ابحث في نصوص المنشورات المجمعة", key="local_q")
        if q:
            df = stx.load_posts(keyword=q, limit=200)
            st.caption(f"{len(df)} نتيجة (أول 200)")
            for r in df.head(50).to_dict("records"):
                ui.post_card(r)


def render_create() -> None:
    ui.hero("إنشاء عملية جمع", "كل عملية مستقلة: لها اسمها واستعلاماتها وإحصاءاتها وسجلها")
    if not ui.require("analyst", "إنشاء عمليات الجمع"):
        return
    tab_browser, tab_import = st.tabs(["جمع عبر المتصفح", "استيراد ملف (HAR / JSON / CSV)"])
    with tab_browser:
        initial = st.session_state.pop("job_initial", None)
        params = search_form("job", initial)
        c1, c2 = st.columns([2, 1])
        name = c1.text_input("اسم العملية", value=describe(params)[:80] if params else "", key="job_name_input")
        max_posts = c2.number_input("الحد الأقصى للمنشورات لكل استعلام", 10, 20000,
                                    db.get_setting_int("max_posts_per_query", 300), step=50, key="job_max")
        start_now = st.checkbox("بدء التنفيذ فوراً", value=True, key="job_start_now")
        st.caption("يتم التمرير في صفحة النتائج بوتيرة بشرية (تأخير عشوائي قابل للضبط من الإعدادات) لتجنب الضغط على المنصة.")
        if st.button("إنشاء العملية", type="primary", disabled=params is None, key="job_create_btn"):
            try:
                job_id = engine.create_job(name, params, max_posts=int(max_posts), created_by=ui.current_user())
                st.success(f"تم إنشاء العملية رقم {job_id}")
                if start_now:
                    cm.start_job(job_id)
                    st.info("بدأ التنفيذ. تابع التقدم من صفحة «عمليات الجمع».")
                st.session_state["selected_job"] = job_id
            except (ValueError, RuntimeError) as exc:
                st.error(str(exc))
    with tab_import:
        st.markdown(
            "بديل عملي عندما لا يكون الجمع الآلي متاحاً: احفظ نشاط الشبكة من أدوات المطور في متصفحك "
            "(DevTools ← Network ← Save all as HAR) أثناء تصفح نتائج البحث في x.com، ثم استورد الملف هنا. "
            "يقبل أيضاً ملفات JSON/CSV المصدّرة من هذا التطبيق.")
        name = st.text_input("اسم عملية الاستيراد", key="imp_name")
        up = st.file_uploader("الملف", type=["har", "json", "jsonl", "csv"], key="imp_file")
        if st.button("استيراد", type="primary", disabled=up is None):
            try:
                with st.spinner("جارٍ الاستيراد والمعالجة…"):
                    r = cm.import_file_as_job(name or up.name, up.name, up.getvalue(), created_by=ui.current_user())
                st.success(f"تم الاستيراد إلى العملية رقم {r['job_id']}: {r['received']} منشور "
                           f"({r['new']} جديد، {r['duplicate']} مكرر)، {r['accounts']} حساب. الصيغة: {r['format']}")
            except Exception as exc:  # noqa: BLE001
                st.error(f"فشل الاستيراد: {exc}")
