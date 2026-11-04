"""الاتصال بمنصة X — browser window, manual login, session status."""
from __future__ import annotations

import streamlit as st

from browser import session_manager as sm
from browser.browser_manager import BrowserBusy, BrowserError, get_browser_manager
from dashboard import ui
from database import db


def _run(label: str, fn):
    try:
        with st.spinner(label):
            return fn()
    except BrowserBusy as exc:
        st.warning(str(exc))
    except BrowserError as exc:
        st.error(str(exc))
    except TimeoutError:
        st.error("انتهت مهلة الانتظار. تحقق من نافذة المتصفح ثم أعد المحاولة.")
    except Exception as exc:  # noqa: BLE001
        st.error(f"تعذر تنفيذ العملية: {type(exc).__name__}: {exc}")
    return None


def render() -> None:
    ui.hero("الاتصال بمنصة X", "اربط التطبيق بدخولك الحالي في متصفحك أو سجّل الدخول في نافذته — لا يتم طلب كلمة المرور أو حفظها")
    bm = get_browser_manager()
    sess = sm.current_status()
    info = bm.info()
    c1, c2, c3 = st.columns(3)
    c1.markdown("**حالة الجلسة**<br>" + ui.badge(sm.STATUS_LABELS_AR.get(sess["status"], sess["status"]),
                ui.STATUS_KIND.get(sess["status"], "muted")), unsafe_allow_html=True)
    c2.markdown(f"**الحساب**<br>{('@' + sess['username']) if sess['username'] else '—'}", unsafe_allow_html=True)
    c3.markdown(f"**آخر تحقق**<br>{sess['checked_at'] or '—'}", unsafe_allow_html=True)
    st.caption(
        f"المتصفح: {'مفتوح' if info['open'] else 'مغلق'}"
        + (f" · مشغول: {info['busy_with']}" if info["busy_with"] else "")
        + (f" · ملف الجلسة موجود" if sess["profile_exists"] else " · لا توجد جلسة محفوظة")
    )
    if sess["message"]:
        st.caption(f"آخر رسالة: {sess['message']}")

    if not ui.can("analyst"):
        st.info("إدارة الاتصال متاحة لصلاحية «محلل» أو أعلى.")
        return
    headless = db.get_setting_bool("browser_headless", False)
    if headless:
        st.warning("المتصفح مضبوط على الوضع المخفي (Headless) من الإعدادات؛ لا يمكن تسجيل الدخول يدوياً في هذا الوضع. "
                   "عطّله لفتح نافذة مرئية.")

    tab_cookie, tab_login = st.tabs(["① استخدام دخولك الحالي في متصفحك (موصى بها)", "② تسجيل الدخول في نافذة التطبيق"])
    with tab_cookie:
        st.markdown(
            "إذا كنت مسجلاً الدخول في X على Chrome أو Edge، انسخ **مفتاح الجلسة** مرة واحدة والصقه هنا، "
            "فيدخل التطبيق مباشرة دون صفحة تسجيل الدخول.\n\n"
            "**الخطوات (دقيقة واحدة):**\n"
            "1. افتح **x.com** في متصفحك المعتاد (وأنت مسجل الدخول).\n"
            "2. اضغط **F12** لفتح أدوات المطوّر.\n"
            "3. اختر تبويب **Application** (في Edge قد يظهر باسم **التطبيق**؛ إن لم يظهر اضغط **»** لإظهار بقية التبويبات).\n"
            "4. من القائمة اليسرى: **Storage ← Cookies ← https://x.com**.\n"
            "5. اكتب في مربع التصفية: `auth_token` ثم انقر على السطر وانسخ قيمة عمود **Value** (40 حرفاً تقريباً).\n"
            "6. كرر الخطوة نفسها لـ `ct0` (اختياري لكنه مستحسن).\n"
            "7. الصق القيم أدناه واضغط **ربط الجلسة**."
        )
        c1, c2 = st.columns(2)
        token = c1.text_input("auth_token", type="password", key="ck_auth",
                              help="يقبل أيضاً لصق سطر Cookie كاملاً أو ملف JSON من إضافة Cookie-Editor")
        ct0 = c2.text_input("ct0 (اختياري)", type="password", key="ck_ct0")
        if st.button("🔗 ربط الجلسة", type="primary", disabled=not token.strip()):
            try:
                cookies = sm.parse_cookie_input(token, ct0)
            except sm.CookieInputError as exc:
                st.error(str(exc))
            else:
                r = _run("جارٍ فتح X بجلستك والتحقق منها…", lambda: bm.import_session(cookies))
                if r:
                    if r["status"] == sm.STATUS_CONNECTED:
                        db.set_setting("session_source", "imported")
                        st.success(f"تم الربط بنجاح — متصل بحساب @{r.get('username') or '؟'}. "
                                   "يمكنك الآن إنشاء عمليات الجمع.")
                        st.balloons()
                    else:
                        st.error("رفضت X هذا المفتاح. تأكد أنك نسخت قيمة auth_token من متصفح مسجّل الدخول حالياً، "
                                 "وأنك لم تسجل الخروج منه بعد النسخ.")
        st.caption("🔒 المفتاح يُحفظ فقط داخل ملف جلسة المتصفح الخاص بالتطبيق على جهازك (مجلد data\\browser_session)، "
                   "ولا يُكتب في قاعدة البيانات أو السجلات. لا تشاركه مع أحد: من يملكه يستطيع الدخول إلى حسابك.")
        st.caption("ℹ️ لماذا لا يفتح التطبيق متصفحك نفسه؟ منذ إصدار 136 يمنع Chrome وEdge أي برنامج من التحكم بملف "
                   "المتصفح الرئيسي ويشفّران ملفات تعريف الارتباط، لذا تُنسخ الجلسة مرة واحدة بدلاً من ذلك.")
    with tab_login:
        st.caption("قد ترفض X أحياناً تسجيل الدخول من متصفح آلي؛ في هذه الحالة استخدم الطريقة ①.")
        b1, b2, b3 = st.columns(3)
        if b1.button("🌐 فتح منصة X", width="stretch"):
            r = _run("جارٍ فتح المتصفح…", lambda: bm.open_x())
            if r:
                st.success("تم فتح X في نافذة المتصفح. سجّل الدخول هناك ثم اضغط «التحقق من حالة الاتصال».")
                db.audit("open_x", r.get("url"), actor=ui.current_user())
        if b2.button("🔄 إعادة الاتصال", width="stretch", help="يفتح صفحة تسجيل الدخول عند انتهاء الجلسة"):
            r = _run("جارٍ فتح صفحة الدخول…", lambda: bm.open_x(target="https://x.com/i/flow/login"))
            if r:
                db.set_setting("session_source", "app_login")
                st.info("أكمل تسجيل الدخول في نافذة المتصفح ثم تحقق من الحالة.")

    b1, b2 = st.columns(2)
    if b1.button("✅ التحقق من حالة الاتصال", width="stretch"):
        r = _run("جارٍ التحقق من الجلسة…", lambda: bm.check_status(navigate=True))
        if r:
            if r.get("busy"):
                st.info("المتصفح ينفذ عملية جمع؛ تم عرض آخر حالة معروفة.")
            elif r["status"] == sm.STATUS_CONNECTED:
                st.success(f"متصل بحساب @{r.get('username') or '؟'}")
            else:
                st.warning("غير متصل. استخدم إحدى طريقتي الربط أعلاه.")
    with b2.popover("🚪 فصل / تسجيل الخروج", width="stretch"):
        mode = st.radio("نوع الفصل", ["local", "server"], format_func={
            "local": "فصل التطبيق فقط (يبقى حسابك مسجلاً في متصفحك)",
            "server": "تسجيل الخروج من X نهائياً (ينهي الجلسة في متصفحك أيضاً إذا كانت منسوخة منه)"}.get)
        wipe = st.checkbox("حذف ملفات الجلسة المحلية أيضاً", value=True)
        if st.button("تأكيد", type="primary"):
            r = _run("جارٍ الفصل…", lambda: bm.logout(wipe=wipe, server_logout=(mode == "server")))
            if r is not None:
                st.success("تم الفصل" + (" وحذف ملفات الجلسة" if wipe else ""))
                st.rerun()

    st.divider()
    st.subheader("نافذة مشاهدة المتصفح")
    st.caption("صورة حية من نافذة المتصفح (تُحدَّث عند الطلب، وتلقائياً أثناء عمليات الجمع).")
    n1, n2, n3 = st.columns([3, 1, 1])
    url = n1.text_input("انتقال إلى رابط على x.com", placeholder="https://x.com/search?q=…", label_visibility="collapsed")
    if n2.button("انتقال", width="stretch"):
        if not url.startswith(("https://x.com", "https://twitter.com")):
            st.error("يسمح بالانتقال إلى روابط x.com فقط")
        else:
            _run("جارٍ فتح الرابط…", lambda: bm.goto(url))
    refresh = n3.button("📸 تحديث الصورة", width="stretch")
    img = None
    if refresh and bm.is_open and not bm.busy_with:
        img = _run("التقاط الصورة…", lambda: bm.screenshot())
    img = img or bm.last_screenshot
    if img:
        st.image(img, width="stretch")
    else:
        st.info("لا توجد صورة بعد — افتح منصة X أولاً.")
    if info["open"] and ui.can("analyst"):
        if st.button("إغلاق نافذة المتصفح (مع الإبقاء على الجلسة)"):
            _run("إغلاق…", lambda: bm.close())
            st.rerun()
    with st.expander("ℹ️ كيف تعمل الجلسة؟"):
        st.markdown(
            "- تُفتح نافذة متصفح Chromium/Edge مستقلة يديرها التطبيق عبر Playwright.\n"
            "- تكتب بيانات الدخول في موقع x.com مباشرة؛ التطبيق لا يقرأ كلمة المرور ولا يخزنها.\n"
            "- تُحفظ ملفات تعريف الارتباط في مجلد `data/browser_session` المقيد بصلاحيات مستخدم Windows الحالي فقط.\n"
            "- عند انتهاء الجلسة تفشل عملية الجمع برسالة واضحة، وبعد إعادة الدخول يمكن استئنافها من «عمليات الجمع».\n"
            "- إن رفض X تسجيل الدخول من متصفح آلي، اختر Microsoft Edge المثبت من «الإعدادات» أو استخدم استيراد ملف HAR."
        )
