"""الإعدادات — collection pace, browser, AI models, users & permissions, backup, data deletion."""
from __future__ import annotations

from pathlib import Path

import streamlit as st

import config
from browser import session_manager as sm
from browser.browser_manager import get_browser_manager
from collectors import collection_manager as cm
from dashboard import ui
from database import db


def _collection_settings() -> None:
    st.subheader("وتيرة الجمع")
    st.caption("قيم محافظة تحمي حسابك وتخفف الضغط على المنصة. تأخير التمرير عشوائي بين الحدين.")
    c1, c2, c3 = st.columns(3)
    dmin = c1.number_input("أدنى تأخير بين التمريرات (ثانية)", 0.5, 60.0, db.get_setting_float("scroll_delay_min", 2.0), 0.5)
    dmax = c2.number_input("أقصى تأخير (ثانية)", 0.5, 120.0, db.get_setting_float("scroll_delay_max", 4.5), 0.5)
    maxp = c3.number_input("الحد الافتراضي للمنشورات لكل استعلام", 10, 20000, db.get_setting_int("max_posts_per_query", 300), 50)
    c4, c5, c6 = st.columns(3)
    maxs = c4.number_input("أقصى عدد تمريرات لكل استعلام", 5, 2000, db.get_setting_int("max_scrolls_per_query", 120), 5)
    idle = c5.number_input("إيقاف بعد تمريرات بلا نتائج جديدة", 2, 50, db.get_setting_int("max_idle_scrolls", 6))
    backoff = c6.number_input("الانتظار عند رسالة خطأ من X (ثانية)", 5, 900, db.get_setting_int("retry_backoff_seconds", 30), 5)
    c7, c8, c9 = st.columns(3)
    retries = c7.number_input("عدد مرات إعادة المحاولة", 0, 10, db.get_setting_int("max_retries", 3))
    timeout = c8.number_input("مهلة تحميل الصفحة (مللي ثانية)", 5000, 180000, db.get_setting_int("page_timeout_ms", 45000), 5000)
    tz = c9.text_input("المنطقة الزمنية", db.get_setting("timezone", "Asia/Riyadh"))
    st.subheader("المتصفح")
    b1, b2 = st.columns(2)
    channels = {"": "Chromium المرفق مع Playwright", "msedge": "Microsoft Edge المثبت", "chrome": "Google Chrome المثبت"}
    cur = db.get_setting("browser_channel", "") or ""
    channel = b1.selectbox("المتصفح المستخدم", list(channels), index=list(channels).index(cur) if cur in channels else 0,
                           format_func=channels.get)
    headless = b2.checkbox("وضع مخفي (Headless) لعمليات الجمع — يتطلب جلسة مسجلة مسبقاً",
                           value=db.get_setting_bool("browser_headless", False))
    st.subheader("نماذج الذكاء الاصطناعي المحلية (اختيارية)")
    m1, m2 = st.columns(2)
    sar = m1.text_input("نموذج المشاعر العربي", db.get_setting("sentiment_model_ar", "CAMeL-Lab/bert-base-arabic-camelbert-da-sentiment"))
    smu = m2.text_input("نموذج المشاعر متعدد اللغات", db.get_setting("sentiment_model_multi", "cardiffnlp/twitter-xlm-roberta-base-sentiment"))
    m3, m4 = st.columns(2)
    nar = m3.text_input("نموذج الكيانات العربي", db.get_setting("ner_model_ar", "CAMeL-Lab/bert-base-arabic-camelbert-msa-ner"))
    nmu = m4.text_input("نموذج الكيانات الإنجليزي", db.get_setting("ner_model_multi", "dslim/bert-base-NER"))
    summ = st.text_input("نموذج التلخيص", db.get_setting("summary_model", "csebuetnlp/mT5_multilingual_XLSum"))
    st.caption(f"تُحمَّل النماذج مرة واحدة إلى {config.MODELS_DIR} ثم تعمل دون اتصال. يمكن ضبط HF_HUB_OFFLINE=1 لمنع أي اتصال.")
    if st.button("حفظ الإعدادات", type="primary"):
        if dmax < dmin:
            st.error("أقصى تأخير يجب أن يكون أكبر من أو يساوي الأدنى")
            return
        try:
            from zoneinfo import ZoneInfo
            ZoneInfo(tz)
        except Exception:
            st.error("منطقة زمنية غير صالحة (مثال: Asia/Riyadh)")
            return
        vals = {"scroll_delay_min": dmin, "scroll_delay_max": dmax, "max_posts_per_query": int(maxp),
                "max_scrolls_per_query": int(maxs), "max_idle_scrolls": int(idle), "retry_backoff_seconds": int(backoff),
                "max_retries": int(retries), "page_timeout_ms": int(timeout), "timezone": tz, "browser_channel": channel,
                "browser_headless": headless, "sentiment_model_ar": sar, "sentiment_model_multi": smu,
                "ner_model_ar": nar, "ner_model_multi": nmu, "summary_model": summ}
        for k, v in vals.items():
            db.set_setting(k, v)
        db.audit("settings_saved", "application_settings", vals, actor=ui.current_user())
        st.success("تم الحفظ. تُطبق إعدادات المتصفح عند فتحه في المرة القادمة.")


def _users() -> None:
    st.subheader("المستخدمون والصلاحيات")
    st.caption("مشاهد: عرض فقط · محلل: الجمع والتحليل والتصدير · مدير: الإعدادات والحذف والنسخ الاحتياطي والمستخدمون.")
    users = db.fetch_all("SELECT username, role, created_at, last_login_at FROM app_users ORDER BY username")
    if users:
        st.dataframe(users, hide_index=True, width="stretch")
    with st.form("add_user", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        u = c1.text_input("اسم المستخدم")
        p = c2.text_input("كلمة المرور", type="password")
        r = c3.selectbox("الصلاحية", list(ui.ROLE_LABELS_AR), index=2 if not users else 0, format_func=ui.ROLE_LABELS_AR.get)
        if st.form_submit_button("إضافة / تحديث مستخدم"):
            if not u.strip() or len(p) < 8:
                st.error("اسم المستخدم مطلوب وكلمة المرور 8 أحرف على الأقل")
            else:
                h, s = ui.hash_password(p)
                db.execute("INSERT INTO app_users(username, password_hash, salt, role, created_at) VALUES (?,?,?,?,?)"
                           " ON CONFLICT(username) DO UPDATE SET password_hash = excluded.password_hash,"
                           " salt = excluded.salt, role = excluded.role", (u.strip(), h, s, r, db.utcnow()))
                db.audit("user_saved", u.strip(), {"role": r}, actor=ui.current_user())
                st.success("تم الحفظ")
                st.rerun()
    if users:
        d1, d2 = st.columns([3, 1])
        target = d1.selectbox("حذف مستخدم", [x["username"] for x in users])
        if d2.button("حذف"):
            admins = [x for x in users if x["role"] == "admin"]
            if len(admins) == 1 and admins[0]["username"] == target and ui.auth_enabled():
                st.error("لا يمكن حذف المدير الوحيد أثناء تفعيل تسجيل الدخول")
            else:
                db.execute("DELETE FROM app_users WHERE username = ?", (target,))
                db.audit("user_deleted", target, actor=ui.current_user())
                st.rerun()
    has_admin = any(x["role"] == "admin" for x in users)
    enabled = st.toggle("تفعيل تسجيل الدخول إلى المنصة", value=db.get_setting_bool("auth_enabled", False),
                        disabled=not has_admin, help="يتطلب وجود مستخدم واحد على الأقل بصلاحية مدير")
    if enabled != db.get_setting_bool("auth_enabled", False):
        db.set_setting("auth_enabled", enabled)
        db.audit("auth_toggled", str(enabled), actor=ui.current_user())
        if enabled:
            st.session_state.pop("user", None)
        st.rerun()


def _backup() -> None:
    st.subheader("النسخ الاحتياطي والاستعادة")
    c1, c2 = st.columns(2)
    if c1.button("إنشاء نسخة احتياطية الآن", type="primary"):
        p = db.backup_database()
        db.audit("backup_created", str(p), actor=ui.current_user())
        st.success(f"تم إنشاء النسخة: {p}")
    backups = db.list_backups()
    st.caption(f"مجلد النسخ: {config.BACKUP_DIR} · عدد النسخ: {len(backups)}")
    if backups:
        pick = st.selectbox("النسخ المتاحة", backups, format_func=lambda p: f"{p.name} ({p.stat().st_size / 1e6:.1f} MB)")
        d1, d2 = st.columns(2)
        d1.download_button("تنزيل النسخة", Path(pick).read_bytes(), file_name=Path(pick).name)
        with d2.popover("استعادة هذه النسخة"):
            st.warning("ستُستبدل قاعدة البيانات الحالية (تُحفظ نسخة أمان تلقائياً قبل الاستعادة).")
            if st.button("تأكيد الاستعادة", type="primary", disabled=cm.any_running() is not None):
                safety = db.restore_database(Path(pick))
                db.audit("backup_restored", str(pick), {"safety_backup": str(safety)}, actor=ui.current_user())
                st.success("تمت الاستعادة")
                st.rerun()
    up = st.file_uploader("استعادة من ملف نسخة (.db)", type=["db"])
    if up and st.button("استعادة من الملف"):
        tmp = config.BACKUP_DIR / f"uploaded_{up.name}"
        tmp.write_bytes(up.getvalue())
        if not db.verify_database_file(tmp):
            tmp.unlink(missing_ok=True)
            st.error("الملف ليس قاعدة بيانات صالحة لهذا التطبيق")
        else:
            db.restore_database(tmp)
            db.audit("backup_restored", up.name, actor=ui.current_user())
            st.success("تمت الاستعادة")
            st.rerun()


def _danger() -> None:
    st.subheader("حذف البيانات")
    c1, c2 = st.columns(2)
    with c1.popover("حذف كل البيانات المجمعة", width="stretch"):
        st.error("يحذف كل المنشورات والحسابات والعمليات والسجلات (الإعدادات والمستخدمون يبقون). أنشئ نسخة احتياطية أولاً.")
        confirm = st.text_input("اكتب: حذف")
        if st.button("حذف نهائي", type="primary", disabled=confirm.strip() != "حذف" or cm.any_running() is not None):
            p = db.backup_database(label="before_delete_all")
            db.delete_all_data()
            db.audit("all_data_deleted", "database", {"backup": str(p)}, actor=ui.current_user())
            st.success(f"تم الحذف (نسخة أمان: {p.name})")
    with c2.popover("حذف ملفات جلسة X", width="stretch"):
        st.warning("يغلق المتصفح ويحذف ملفات تعريف الارتباط المحلية؛ ستحتاج لتسجيل الدخول مجدداً.")
        if st.button("حذف الجلسة", type="primary", disabled=cm.any_running() is not None):
            try:
                get_browser_manager().close()
            except Exception:
                pass
            sm.wipe_session()
            st.success("تم حذف ملفات الجلسة")


def render() -> None:
    ui.hero("الإعدادات", "الإعدادات العامة والأمان والنسخ الاحتياطي")
    theme = st.radio("المظهر", ["light", "dark"], format_func={"light": "☀️ نهاري", "dark": "🌙 ليلي"}.get, horizontal=True,
                     index=1 if ui.is_dark() else 0)
    if theme != st.session_state.get("theme", db.get_setting("ui_theme", "light")):
        st.session_state["theme"] = theme
        db.set_setting("ui_theme", theme)
        st.rerun()
    if not ui.require("admin", "تعديل الإعدادات"):
        return
    t1, t2, t3, t4, t5 = st.tabs(["الجمع والمتصفح", "المستخدمون والصلاحيات", "النسخ الاحتياطي", "حذف البيانات", "معلومات النظام"])
    with t1:
        _collection_settings()
    with t2:
        _users()
    with t3:
        _backup()
    with t4:
        _danger()
    with t5:
        st.write({"التطبيق": f"{config.APP_NAME} {config.APP_VERSION}", "قاعدة البيانات": str(db.db_path()),
                  "حجم القاعدة (MB)": round(db.db_path().stat().st_size / 1e6, 2) if db.db_path().exists() else 0,
                  "مجلد الجلسة": str(sm.session_dir()), "مجلد التصدير": str(config.EXPORT_DIR),
                  "خط PDF العربي": config.pdf_font_path() or "غير موجود"})
        st.dataframe([{"الجدول": k, "السجلات": v} for k, v in db.table_counts().items()], hide_index=True,
                     width="stretch")
