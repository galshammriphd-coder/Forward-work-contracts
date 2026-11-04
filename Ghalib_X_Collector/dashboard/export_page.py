"""تصدير البيانات — XLSX / CSV / JSON, one folder per export."""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import streamlit as st

import config
from analytics import statistics as stx
from dashboard import ui
from database import db, models
from exports.service import export_posts, export_posts_all_formats


def render() -> None:
    ui.hero("تصدير البيانات", "تصدير منشورات عملية أو نتائج مرشحات إلى Excel وCSV وJSON في مجلد مستقل")
    if not ui.require("analyst", "التصدير"):
        return
    scope = st.radio("نطاق التصدير", ["عملية جمع", "مرشحات مخصصة"], horizontal=True)
    job_id, name, filters = None, "all_data", {}
    if scope == "عملية جمع":
        opts = ui.job_options()
        if not opts:
            st.info("لا توجد عمليات.")
            return
        s = st.selectbox("العملية", list(opts))
        job_id = opts[s]
        name = models.get_job(job_id)["name"]
        df = stx.load_posts(job_ids=[job_id], only_valid=False)
    else:
        filters = ui.filters_bar("exp", expanded=True)
        name = st.text_input("اسم التصدير", value="filtered_posts")
        df = stx.load_posts(**filters)
    st.caption(f"{len(df):,} منشور")
    formats = st.multiselect("الصيغ", ["xlsx", "csv", "json"], default=["xlsx", "csv", "json"])
    include_raw = st.checkbox("تضمين السجل الأصلي الخام (raw_json) في JSON", value=False)
    if st.button("تصدير", type="primary", disabled=df.empty or not formats):
        clean_filters = {k: str(v) for k, v in filters.items() if v}
        with st.spinner("جارٍ التصدير…"):
            if set(formats) == {"xlsx", "csv", "json"} and not include_raw:
                paths = export_posts_all_formats(df, name, job_id=job_id, filters=clean_filters, actor=ui.current_user())
            else:
                paths = [export_posts(df, f, name, job_id=job_id, filters=clean_filters, actor=ui.current_user(),
                                      include_raw=include_raw) for f in formats]
        st.success("تم التصدير إلى: " + ", ".join(str(p.parent) for p in {p.parent: p for p in paths}.values()))
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for p in paths:
                z.write(p, arcname=p.name)
        st.download_button("تنزيل الملفات (ZIP)", buf.getvalue(), file_name=f"{paths[0].stem}.zip")
    st.divider()
    st.subheader("سجل عمليات التصدير")
    ex = db.read_df("SELECT id, export_type, format, record_count, path, created_by, created_at FROM exports ORDER BY id DESC LIMIT 200")
    st.dataframe(ex, hide_index=True, width="stretch", column_config={
        "export_type": "النوع", "format": "الصيغة", "record_count": "السجلات", "path": "المسار",
        "created_by": "بواسطة", "created_at": "التاريخ"})
    st.caption(f"مجلد التصدير: {config.EXPORT_DIR}")
    if not ex.empty:
        pick = st.selectbox("تنزيل ملف سابق", ex["path"].tolist())
        p = Path(pick)
        if p.exists():
            st.download_button("تنزيل", p.read_bytes(), file_name=p.name, key="dl_prev")
        else:
            st.caption("الملف لم يعد موجوداً على القرص.")
