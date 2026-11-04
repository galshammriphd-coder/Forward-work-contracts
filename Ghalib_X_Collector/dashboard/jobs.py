"""عمليات الجمع — job list, live progress and controls."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from collectors import collection_manager as cm
from dashboard import ui
from database import db, models
from processing.pipeline import run_pipeline


def _jobs_df() -> pd.DataFrame:
    df = db.read_df(
        "SELECT id, name, search_type, query_text, status, received_count, new_count, duplicate_count,"
        " processed_count, error_count, start_date, end_date, created_at, started_at, finished_at FROM search_jobs"
        " ORDER BY id DESC")
    if df.empty:
        return df
    df["status"] = df["status"].map(models.STATUS_LABELS_AR)
    df["search_type"] = df["search_type"].map(models.SEARCH_TYPE_LABELS_AR)
    return df.rename(columns={
        "id": "رقم", "name": "الاسم", "search_type": "النوع", "query_text": "عبارة البحث", "status": "الحالة",
        "received_count": "المستلمة", "new_count": "الجديدة", "duplicate_count": "المكررة",
        "processed_count": "المعالجة", "error_count": "الأخطاء", "start_date": "من", "end_date": "إلى",
        "created_at": "تاريخ الإنشاء", "started_at": "بدء التنفيذ", "finished_at": "الانتهاء"})


@st.fragment(run_every=3)
def _live(job_id: int) -> None:
    j = cm.job_summary(job_id)
    if not j:
        return
    st.markdown(ui.badge(j["status_ar"], ui.STATUS_KIND.get(j["status"], "muted")), unsafe_allow_html=True)
    ui.kpi_cards([
        ("المستلمة", ui.fmt_num(j["received_count"]), "منشورات فريدة في العملية", "#2563EB"),
        ("الجديدة", ui.fmt_num(j["new_count"]), "لم تكن في قاعدة البيانات", "#10B981"),
        ("المكررة", ui.fmt_num(j["duplicate_count"]), "موجودة سابقاً", "#F59E0B"),
        ("المعالجة", ui.fmt_num(j["processed_count"]), f"أخطاء: {j['error_count']}", "#6366F1"),
    ])
    prog = j["progress"]
    if prog:
        rows = [{"#": int(k) + 1, "الاستعلام": v.get("query"), "المجموع": v.get("collected", 0),
                 "أقدم منشور": v.get("oldest") or "—", "مكتمل": "✓" if v.get("done") else "…"}
                for k, v in sorted(prog.items(), key=lambda kv: int(kv[0]))]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        total = len(j["queries"]) or 1
        done = sum(1 for v in prog.values() if v.get("done"))
        st.progress(min(done / total, 1.0), text=f"الاستعلامات المكتملة: {done}/{total}")
    if j["last_error"]:
        st.error(j["last_error"])
    if j["running_now"]:
        from browser.browser_manager import get_browser_manager
        img = get_browser_manager().last_screenshot
        if img:
            with st.expander("👁 مشاهدة المتصفح أثناء الجمع", expanded=False):
                st.image(img, width="stretch")
    logs = db.read_df("SELECT ts AS 'الوقت', level AS 'المستوى', event AS 'الحدث', message AS 'الرسالة'"
                      " FROM collection_logs WHERE job_id = ? ORDER BY id DESC LIMIT 30", (job_id,))
    st.dataframe(logs, hide_index=True, width="stretch", height=260)


def render() -> None:
    ui.hero("عمليات الجمع", "متابعة الحالة والتقدم، الإيقاف والاستئناف وإعادة التنفيذ")
    df = _jobs_df()
    if df.empty:
        st.info("لا توجد عمليات بعد. أنشئ عملية من «إنشاء عملية جمع».")
        return
    status_filter = st.multiselect("تصفية حسب الحالة", list(models.STATUS_LABELS_AR.values()))
    view = df[df["الحالة"].isin(status_filter)] if status_filter else df
    st.dataframe(view, hide_index=True, width="stretch", height=300)

    ids = df["رقم"].tolist()
    default = st.session_state.get("selected_job")
    idx = ids.index(default) if default in ids else 0
    job_id = st.selectbox("اختر عملية", ids, index=idx,
                          format_func=lambda i: f"#{i} — {df.loc[df['رقم'] == i, 'الاسم'].iloc[0]}")
    st.session_state["selected_job"] = job_id
    j = models.get_job(job_id)
    st.markdown(f"### #{j['id']} {j['name']}")
    with st.expander("تفاصيل البحث"):
        st.write({"النوع": models.SEARCH_TYPE_LABELS_AR.get(j["search_type"]), "عبارة البحث": j["query_text"],
                  "الترتيب": j["sort_mode"], "الحد الأقصى لكل استعلام": j["max_posts"],
                  "من": j["start_date"], "إلى": j["end_date"], "أنشأها": j["created_by"],
                  "العملية الأصل": j["parent_job_id"]})
        for q in j["queries"]:
            st.code(q, language=None)

    can_run = ui.can("analyst")
    running = cm.is_running(job_id)
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    if c1.button("▶ تنفيذ", disabled=not can_run or running or j["status"] != "new" or j["search_type"] == "import",
                 width="stretch"):
        try:
            cm.start_job(job_id)
            st.rerun()
        except (RuntimeError, ValueError) as exc:
            st.error(str(exc))
    if c2.button("⏸ إيقاف", disabled=not can_run or not (running or j["status"] == "running"), width="stretch"):
        cm.stop_job(job_id)
        db.audit("job_stop", f"job:{job_id}", actor=ui.current_user())
        st.toast("تم طلب الإيقاف؛ تتوقف العملية بعد الخطوة الحالية")
    if c3.button("⏯ استئناف", disabled=not can_run or running or j["status"] not in ("stopped", "failed")
                 or j["search_type"] == "import", width="stretch",
                 help="يكمل الاستعلامات غير المكتملة ويبدأ من أقدم منشور تم جمعه"):
        try:
            cm.start_job(job_id, resume=True)
            st.rerun()
        except (RuntimeError, ValueError) as exc:
            st.error(str(exc))
    if c4.button("🔁 إعادة تنفيذ", disabled=not can_run or j["search_type"] == "import", width="stretch",
                 help="ينشئ عملية جديدة بنفس الإعدادات"):
        try:
            new_id = cm.rerun_job(job_id, created_by=ui.current_user())
            st.session_state["selected_job"] = new_id
            if cm.any_running() is None:
                cm.start_job(new_id)
            st.rerun()
        except (RuntimeError, ValueError) as exc:
            st.error(str(exc))
    if c5.button("🧹 معالجة", disabled=not can_run or running, width="stretch",
                 help="تشغيل دورة التنظيف والمعالجة على منشورات العملية"):
        r = run_pipeline(job_id=job_id, reprocess=True)
        st.success(f"تمت معالجة {r['records']} سجل")
    with c6.popover("🗑 حذف", width="stretch", disabled=not ui.can("admin") or running):
        st.write("يحذف العملية والمنشورات التي لم تجدها عملية أخرى.")
        if st.button("تأكيد الحذف", type="primary"):
            r = db.delete_job_data(job_id)
            db.audit("job_deleted", f"job:{job_id}", r, actor=ui.current_user())
            st.session_state.pop("selected_job", None)
            st.success(f"تم الحذف ({r['posts_deleted']} منشور)")
            st.rerun()
    _live(job_id)
