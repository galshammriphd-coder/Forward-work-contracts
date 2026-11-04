"""المنشورات — interactive data browser with selection and export."""
from __future__ import annotations

import json

import streamlit as st

from analytics import statistics as stx
from dashboard import ui
from exports.service import export_posts

SORTS = {
    "الأحدث": ("published_at", False),
    "الأقدم": ("published_at", True),
    "الأكثر تفاعلاً": ("engagement", False),
    "الأكثر إعجاباً": ("likes_count", False),
    "الأكثر مشاهدة": ("views_count", False),
    "الأكثر إعادة نشر": ("reposts_count", False),
}


def render() -> None:
    ui.hero("المنشورات", "استعراض البيانات المجمعة والبحث والتصفية والتصدير")
    f = ui.filters_bar("posts", expanded=True)
    c1, c2 = st.columns([2, 1])
    sort = c1.selectbox("الترتيب", list(SORTS))
    limit = c2.number_input("عدد السجلات المعروضة", 50, 50000, 2000, step=500)
    df = stx.load_posts(**f)
    if df.empty:
        st.info("لا توجد منشورات مطابقة.")
        return
    col, asc = SORTS[sort]
    df = df.sort_values(col, ascending=asc, na_position="last").head(int(limit)).reset_index(drop=True)
    st.caption(f"{len(df):,} منشور معروض")
    view = df[["published_date", "published_time", "username", "display_name", "clean_text", "lang", "post_type",
               "likes_count", "reposts_count", "replies_count", "views_count", "engagement", "post_url"]].copy()
    view["clean_text"] = view["clean_text"].fillna(df["raw_text"])
    event = st.dataframe(
        view,
        hide_index=True,
        width="stretch",
        height=520,
        on_select="rerun",
        selection_mode="multi-row",
        column_config={
            "published_date": st.column_config.TextColumn("التاريخ"),
            "published_time": st.column_config.TextColumn("الوقت"),
            "username": st.column_config.TextColumn("الحساب"),
            "display_name": st.column_config.TextColumn("الاسم"),
            "clean_text": st.column_config.TextColumn("النص", width="large"),
            "lang": st.column_config.TextColumn("اللغة"),
            "post_type": st.column_config.TextColumn("النوع"),
            "likes_count": st.column_config.NumberColumn("إعجابات", format="%d"),
            "reposts_count": st.column_config.NumberColumn("إعادة نشر", format="%d"),
            "replies_count": st.column_config.NumberColumn("ردود", format="%d"),
            "views_count": st.column_config.NumberColumn("مشاهدات", format="%d"),
            "engagement": st.column_config.NumberColumn("التفاعل", format="%d"),
            "post_url": st.column_config.LinkColumn("الرابط", display_text="فتح"),
        },
        key="posts_table",
    )
    rows = event.selection.rows if event and event.selection else []
    sel = df.iloc[rows] if rows else df.iloc[0:0]
    st.write(f"المحدد: **{len(sel)}** سجل")
    c1, c2, c3, c4 = st.columns(4)
    target = sel if len(sel) else df
    label = "المحددة" if len(sel) else "المعروضة"
    for c, fmt in zip((c1, c2, c3), ("xlsx", "csv", "json")):
        if c.button(f"تصدير {label} {fmt.upper()}", width="stretch", disabled=not ui.can("analyst")):
            path = export_posts(target, fmt, name=f"posts_{label}", filters={k: str(v) for k, v in f.items() if v},
                                actor=ui.current_user())
            st.success(f"تم الحفظ: {path}")
            st.download_button("تنزيل الملف", path.read_bytes(), file_name=path.name, key=f"dl_{fmt}")
    if len(sel):
        st.subheader("تفاصيل المنشور")
        r = sel.iloc[0].to_dict()
        ui.post_card(r)
        st.link_button("فتح المنشور الأصلي في X", r["post_url"])
        with st.expander("كل الحقول"):
            show = {k: v for k, v in r.items() if k not in ("raw_json", "published_dt", "hashtags", "mentions")}
            st.json(json.loads(json.dumps(show, default=str)))
        with st.expander("السجل الأصلي كما استُلم (raw)"):
            st.code((r.get("raw_json") or "")[:20000], language="json")
