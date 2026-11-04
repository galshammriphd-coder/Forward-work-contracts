"""Shared UI helpers: RTL styling, light/dark theme, cards, permissions."""
from __future__ import annotations

import hashlib
import hmac
import html
import os

import streamlit as st

from dashboard import charts
from database import db
from processing.language_detection import language_name

ROLE_LEVEL = {"viewer": 1, "analyst": 2, "admin": 3}
ROLE_LABELS_AR = {"viewer": "مشاهد", "analyst": "محلل", "admin": "مدير"}

_LIGHT = dict(bg="#F5F7FB", panel="#FFFFFF", text="#0F172A", muted="#64748B", border="#E2E8F0",
              accent="#1D4ED8", accent2="#0EA5E9", sidebar="#0B1F4D", sidetext="#E2E8F0")
_DARK = dict(bg="#0B1220", panel="#111A2E", text="#E5E7EB", muted="#94A3B8", border="#1F2A44",
             accent="#60A5FA", accent2="#38BDF8", sidebar="#070D1A", sidetext="#CBD5E1")


def is_dark() -> bool:
    return st.session_state.get("theme", db.get_setting("ui_theme", "light")) == "dark"


def apply_theme() -> None:
    dark = is_dark()
    charts.set_dark(dark)
    try:  # native widgets / dataframes follow Streamlit's own theme
        st._config.set_option("theme.base", "dark" if dark else "light")
    except Exception:
        pass
    c = _DARK if dark else _LIGHT
    st.markdown(
        f"""
<style>
:root {{ --g-bg:{c['bg']}; --g-panel:{c['panel']}; --g-text:{c['text']}; --g-muted:{c['muted']};
        --g-border:{c['border']}; --g-accent:{c['accent']}; --g-accent2:{c['accent2']}; }}
html, body, [class*="css"], .stMarkdown, .stText, p, label, input, textarea, button, select, h1, h2, h3, h4 {{
  font-family: 'Segoe UI', Tahoma, 'Noto Naskh Arabic', 'DejaVu Sans', Arial, sans-serif !important; }}
.stApp, [data-testid="stAppViewContainer"] {{ background: var(--g-bg); color: var(--g-text); }}
[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stMain"] .block-container {{ direction: rtl; text-align: right; padding-top: 1.6rem; max-width: 1400px; }}
[data-testid="stMain"] h1, [data-testid="stMain"] h2, [data-testid="stMain"] h3, [data-testid="stMain"] h4,
[data-testid="stMain"] p, [data-testid="stMain"] li, [data-testid="stMain"] label {{ color: var(--g-text); }}
[data-testid="stSidebar"] {{ background: {c['sidebar']}; direction: rtl; }}
[data-testid="stSidebar"] * {{ color: {c['sidetext']} !important; }}
[data-testid="stSidebar"] [role="radiogroup"] label {{ padding: 6px 10px; border-radius: 10px; margin-bottom: 2px; width: 100%; }}
[data-testid="stSidebar"] [role="radiogroup"] label:hover {{ background: rgba(255,255,255,0.08); }}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {{ background: rgba(96,165,250,0.22); }}
[data-testid="stMarkdownContainer"] ul, [data-testid="stMarkdownContainer"] ol {{ padding-right: 1.2rem; padding-left: 0; }}
input, textarea {{ direction: auto; unicode-bidi: plaintext; }}
[data-testid="stDataFrame"], [data-testid="stTable"] {{ direction: ltr; }}
.stTabs [data-baseweb="tab-list"] {{ direction: rtl; gap: 4px; }}
[data-testid="stMetric"] {{ direction: rtl; }}
div[data-testid="stExpander"] details {{ background: var(--g-panel); border-color: var(--g-border); border-radius: 12px; }}
.g-hero {{ background: linear-gradient(120deg, #1D4ED8 0%, #0EA5E9 100%); color: #fff; border-radius: 18px;
  padding: 18px 24px; margin-bottom: 18px; display:flex; justify-content:space-between; align-items:center; gap:12px; flex-wrap:wrap; }}
.g-hero h1 {{ color:#fff !important; margin:0; font-size: 1.6rem; font-weight: 800; }}
.g-hero p {{ color: rgba(255,255,255,.9) !important; margin: 4px 0 0 0; }}
.g-card {{ background: var(--g-panel); border: 1px solid var(--g-border); border-radius: 16px; padding: 14px 16px;
  box-shadow: 0 1px 2px rgba(15,23,42,.05); height: 100%; }}
.g-card .lbl {{ color: var(--g-muted); font-size: .86rem; }}
.g-card .val {{ color: var(--g-text); font-size: 1.65rem; font-weight: 800; line-height: 1.3; direction: ltr; text-align: right; }}
.g-card .sub {{ color: var(--g-muted); font-size: .75rem; }}
.g-card .bar {{ height: 4px; border-radius: 4px; margin-top: 8px; }}
.g-badge {{ display:inline-block; padding: 2px 10px; border-radius: 999px; font-size: .8rem; font-weight: 700; }}
.g-ok {{ background:#DCFCE7; color:#166534; }} .g-warn {{ background:#FEF3C7; color:#92400E; }}
.g-err {{ background:#FEE2E2; color:#991B1B; }} .g-info {{ background:#DBEAFE; color:#1E40AF; }}
.g-muted {{ background:#E2E8F0; color:#334155; }}
[data-testid="stSidebar"] .g-ok {{ color:#166534 !important; }} [data-testid="stSidebar"] .g-warn {{ color:#92400E !important; }}
[data-testid="stSidebar"] .g-err {{ color:#991B1B !important; }} [data-testid="stSidebar"] .g-info {{ color:#1E40AF !important; }}
[data-testid="stSidebar"] .g-muted {{ color:#334155 !important; }}
.g-post {{ background: var(--g-panel); border:1px solid var(--g-border); border-radius:14px; padding:12px 16px; margin-bottom:8px; }}
.g-post .t {{ white-space: pre-wrap; unicode-bidi: plaintext; color: var(--g-text); }}
.g-post .m {{ color: var(--g-muted); font-size:.8rem; margin-top:6px; }}
</style>
""",
        unsafe_allow_html=True,
    )


def hero(title: str, subtitle: str = "", right_html: str = "") -> None:
    st.markdown(
        f'<div class="g-hero"><div><h1>{html.escape(title)}</h1><p>{html.escape(subtitle)}</p></div>{right_html}</div>',
        unsafe_allow_html=True,
    )


def fmt_num(v, decimals: int = 0) -> str:
    if v is None:
        return "غير متاح"
    try:
        if v != v:  # NaN
            return "غير متاح"
        return f"{v:,.{decimals}f}"
    except (TypeError, ValueError):
        return str(v)


def kpi_cards(items: list[tuple], per_row: int = 4) -> None:
    """items: (label, value, sub, color)"""
    for i in range(0, len(items), per_row):
        cols = st.columns(per_row)
        for col, it in zip(cols, items[i:i + per_row]):
            label, value, sub, color = (list(it) + ["", "#2563EB"])[:4]
            col.markdown(
                f'<div class="g-card"><div class="lbl">{html.escape(str(label))}</div>'
                f'<div class="val">{html.escape(str(value))}</div><div class="sub">{html.escape(str(sub or ""))}</div>'
                f'<div class="bar" style="background:{color}"></div></div>',
                unsafe_allow_html=True,
            )
        st.write("")


def badge(text: str, kind: str = "info") -> str:
    return f'<span class="g-badge g-{kind}">{html.escape(text)}</span>'


STATUS_KIND = {"new": "muted", "running": "info", "completed": "ok", "stopped": "warn", "failed": "err",
               "connected": "ok", "disconnected": "muted", "expired": "err", "unknown": "muted"}


def post_card(r: dict) -> None:
    eng = []
    for k, lab in (("replies_count", "💬"), ("reposts_count", "🔁"), ("likes_count", "❤"), ("views_count", "👁")):
        v = r.get(k)
        eng.append(f"{lab} {fmt_num(v) if v is not None and v == v else '—'}")
    url = html.escape(r.get("post_url") or "")
    st.markdown(
        f'<div class="g-post"><b>{html.escape(str(r.get("display_name") or ""))}</b> '
        f'<span style="color:var(--g-muted)">@{html.escape(str(r.get("username") or ""))}</span>'
        f'<div class="t">{html.escape(str(r.get("clean_text") or r.get("raw_text") or ""))}</div>'
        f'<div class="m">{html.escape(str(r.get("published_date") or ""))} {html.escape(str(r.get("published_time") or ""))}'
        f' · {" · ".join(eng)} · <a href="{url}" target="_blank">فتح المنشور</a></div></div>',
        unsafe_allow_html=True,
    )


# ------------------------------------------------------------- permissions
def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or os.urandom(16).hex()
    h = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 240_000).hex()
    return h, salt


def verify_password(password: str, stored_hash: str, salt: str) -> bool:
    return hmac.compare_digest(hash_password(password, salt)[0], stored_hash)


def auth_enabled() -> bool:
    return db.get_setting_bool("auth_enabled", False) and bool(db.fetch_value("SELECT COUNT(*) FROM app_users", default=0))


def current_user() -> str:
    return st.session_state.get("user", "local") if auth_enabled() else "local"


def current_role() -> str:
    return st.session_state.get("role", "viewer") if auth_enabled() else "admin"


def can(required: str) -> bool:
    return ROLE_LEVEL.get(current_role(), 0) >= ROLE_LEVEL[required]


def require(required: str, action: str = "هذا الإجراء") -> bool:
    if can(required):
        return True
    st.warning(f"{action} يتطلب صلاحية «{ROLE_LABELS_AR[required]}» أو أعلى. صلاحيتك الحالية: {ROLE_LABELS_AR.get(current_role())}")
    return False


def login_gate() -> bool:
    """Returns True when the user may use the app."""
    if not auth_enabled() or st.session_state.get("user"):
        return True
    st.markdown("<div style='max-width:420px;margin:8vh auto 0 auto'>", unsafe_allow_html=True)
    hero("Ghalib X Data Collector", "تسجيل الدخول إلى المنصة المحلية")
    with st.form("login"):
        u = st.text_input("اسم المستخدم")
        p = st.text_input("كلمة المرور", type="password")
        ok = st.form_submit_button("دخول", width="stretch")
    if ok:
        row = db.fetch_one("SELECT * FROM app_users WHERE username = ?", (u.strip(),))
        if row and verify_password(p, row["password_hash"], row["salt"]):
            st.session_state["user"], st.session_state["role"] = row["username"], row["role"]
            db.execute("UPDATE app_users SET last_login_at = ? WHERE username = ?", (db.utcnow(), row["username"]))
            db.audit("app_login", row["username"], actor=row["username"])
            st.rerun()
        else:
            db.audit("app_login_failed", u.strip())
            st.error("بيانات الدخول غير صحيحة")
    st.markdown("</div>", unsafe_allow_html=True)
    return False


def job_options(include_all: bool = False) -> dict:
    rows = db.fetch_all("SELECT id, name, status, received_count FROM search_jobs ORDER BY id DESC")
    opts = {f"#{r['id']} — {r['name']} ({r['received_count']})": r["id"] for r in rows}
    return ({"كل البيانات": None} | opts) if include_all else opts


def language_options() -> list[str]:
    return [r["l"] for r in db.fetch_all(
        "SELECT DISTINCT COALESCE(detected_language, language, 'und') AS l FROM posts ORDER BY l")]


def filters_bar(key: str, show_jobs: bool = True, expanded: bool = False) -> dict:
    """Interactive filters shared by the dashboard pages (date, language, keyword, accounts, job)."""
    with st.expander("🔎 المرشحات", expanded=expanded):
        c1, c2, c3 = st.columns(3)
        jobs = job_options()
        sel_jobs = c1.multiselect("عمليات الجمع", list(jobs), key=f"{key}_jobs") if show_jobs else []
        langs = c2.multiselect("اللغة", language_options(), key=f"{key}_langs",
                               format_func=lambda x: f"{x} — {language_name(x)}")
        kw = c3.text_input("كلمة مفتاحية داخل النص", key=f"{key}_kw")
        c4, c5, c6 = st.columns(3)
        dfrom = c4.date_input("من تاريخ", value=None, key=f"{key}_from")
        dto = c5.date_input("إلى تاريخ", value=None, key=f"{key}_to")
        users = c6.text_input("الحسابات (مفصولة بفواصل)", key=f"{key}_users")
        c7, c8 = st.columns(2)
        tag = c7.text_input("هاشتاق", key=f"{key}_tag")
        nodup = c8.checkbox("استبعاد النصوص المكررة", key=f"{key}_nodup")
    return {
        "job_ids": [jobs[j] for j in sel_jobs] or None,
        "languages": langs or None,
        "keyword": kw.strip() or None,
        "date_from": dfrom,
        "date_to": dto,
        "usernames": [u.strip() for u in users.replace("،", ",").split(",") if u.strip()] or None,
        "hashtag": tag.strip() or None,
        "exclude_duplicate_text": nodup,
    }
