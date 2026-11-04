"""سجل العمليات — collection logs, processing logs, audit trail, application log file."""
from __future__ import annotations

import streamlit as st

import config
from dashboard import ui
from database import db


def render() -> None:
    ui.hero("سجل العمليات", "سجلات الجمع والمعالجة وسجل التدقيق وأخطاء التطبيق")
    t1, t2, t3, t4 = st.tabs(["سجل الجمع", "سجل المعالجة", "سجل التدقيق", "ملف سجل التطبيق"])
    with t1:
        c1, c2 = st.columns(2)
        lvl = c1.multiselect("المستوى", ["INFO", "WARNING", "ERROR"], default=["INFO", "WARNING", "ERROR"])
        job = c2.text_input("رقم العملية (اختياري)")
        where, params = [f"level IN ({','.join('?' * len(lvl))})"] if lvl else ["1=1"], list(lvl)
        if job.strip().isdigit():
            where.append("job_id = ?")
            params.append(int(job))
        df = db.read_df(f"SELECT id, job_id, ts, level, event, message, details FROM collection_logs WHERE {' AND '.join(where)}"
                        " ORDER BY id DESC LIMIT 1000", params)
        st.dataframe(df, hide_index=True, width="stretch", height=520)
    with t2:
        df = db.read_df("SELECT run_id, job_id, step, ts, records_in, records_affected, message FROM processing_logs"
                        " ORDER BY id DESC LIMIT 1000")
        st.dataframe(df, hide_index=True, width="stretch", height=520, column_config={
            "step": "الخطوة", "records_in": "السجلات", "records_affected": "المتأثرة", "message": "الوصف"})
    with t3:
        if not ui.require("admin", "عرض سجل التدقيق"):
            pass
        else:
            df = db.read_df("SELECT ts, actor, action, target, details FROM audit_log ORDER BY id DESC LIMIT 2000")
            st.dataframe(df, hide_index=True, width="stretch", height=520)
    with t4:
        f = config.LOG_DIR / "ghalib.log"
        if f.exists():
            lines = f.read_text(encoding="utf-8", errors="replace").splitlines()[-400:]
            st.code("\n".join(lines), language=None)
        else:
            st.info("لا يوجد ملف سجل بعد.")
