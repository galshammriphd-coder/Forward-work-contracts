"""Ghalib X Data Collector — Streamlit entry point.

Run:  streamlit run app.py      (or double-click run_windows.bat on Windows)
"""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st  # noqa: E402

import config  # noqa: E402

config.ensure_dirs()

from database import db  # noqa: E402

@st.cache_resource(show_spinner=False)
def _boot() -> bool:
    """Process-wide startup. Streamlit re-executes this script on every interaction;
    cache_resource guarantees this body runs once per server process."""
    root = logging.getLogger("ghalib")
    if not root.handlers:
        h = RotatingFileHandler(config.LOG_DIR / "ghalib.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root.addHandler(h)
        root.setLevel(logging.INFO)
    db.init_db()
    from collectors.collection_manager import recover_interrupted_jobs
    n = recover_interrupted_jobs()
    root.info("application started (%s interrupted jobs recovered)", n)
    db.audit("app_started", config.APP_VERSION)
    return True


_boot()

st.set_page_config(page_title=config.APP_NAME, page_icon="📊", layout="wide", initial_sidebar_state="expanded")

from dashboard import (  # noqa: E402
    accounts, analytics_page, compare, connection, export_page, hashtags, home, jobs, logs_page, posts, reports,
    search_page, settings_page, ui,
)
from browser import session_manager as sm  # noqa: E402
from collectors import collection_manager as cm  # noqa: E402

PAGES = {
    "الرئيسية": ("🏠", home.render),
    "الاتصال بمنصة X": ("🔐", connection.render),
    "محرك البحث": ("🔎", search_page.render_search),
    "إنشاء عملية جمع": ("➕", search_page.render_create),
    "عمليات الجمع": ("⚙️", jobs.render),
    "المنشورات": ("📝", posts.render),
    "الحسابات": ("👤", accounts.render),
    "الهاشتاقات": ("#️⃣", hashtags.render),
    "التحليلات": ("🧠", analytics_page.render),
    "المقارنات": ("⚖️", compare.render),
    "التقارير": ("📑", reports.render),
    "تصدير البيانات": ("📤", export_page.render),
    "سجل العمليات": ("🗂️", logs_page.render),
    "الإعدادات": ("🛠️", settings_page.render),
}


def main() -> None:
    ui.apply_theme()
    if not ui.login_gate():
        return
    with st.sidebar:
        st.markdown(f"## 📊 {config.APP_NAME}")
        st.caption("منصة محلية لجمع وتحليل بيانات X")
        names = list(PAGES)
        # Pages request navigation through "nav_request"; it is applied before the menu widget exists.
        req = st.session_state.pop("nav_request", None)
        if req in names:
            st.session_state["nav"] = req
        if st.session_state.get("nav") not in names:
            st.session_state["nav"] = names[0]
        choice = st.radio("القائمة", names, key="nav", format_func=lambda n: f"{PAGES[n][0]}  {n}",
                          label_visibility="collapsed")
        st.divider()
        sess = sm.current_status()
        st.markdown("جلسة X: " + ui.badge(sm.STATUS_LABELS_AR.get(sess["status"], sess["status"]),
                                          ui.STATUS_KIND.get(sess["status"], "muted")), unsafe_allow_html=True)
        running = cm.any_running()
        if running is not None:
            st.markdown(ui.badge(f"عملية قيد التنفيذ #{running}", "info"), unsafe_allow_html=True)
        dark = st.toggle("🌙 الوضع الليلي", value=ui.is_dark())
        if dark != ui.is_dark():
            st.session_state["theme"] = "dark" if dark else "light"
            db.set_setting("ui_theme", st.session_state["theme"])
            st.rerun()
        if ui.auth_enabled():
            st.caption(f"المستخدم: {ui.current_user()} ({ui.ROLE_LABELS_AR.get(ui.current_role())})")
            if st.button("تسجيل الخروج من المنصة"):
                db.audit("app_logout", ui.current_user(), actor=ui.current_user())
                for k in ("user", "role"):
                    st.session_state.pop(k, None)
                st.rerun()
        st.caption(f"v{config.APP_VERSION} · البيانات محفوظة محلياً")
    try:
        PAGES[choice][1]()
    except Exception as exc:  # noqa: BLE001 — never show a blank page
        logging.getLogger("ghalib").exception("page %s failed", choice)
        st.error(f"حدث خطأ غير متوقع في هذه الصفحة: {type(exc).__name__}: {exc}")
        st.caption(f"التفاصيل في {config.LOG_DIR / 'ghalib.log'}")


main()
