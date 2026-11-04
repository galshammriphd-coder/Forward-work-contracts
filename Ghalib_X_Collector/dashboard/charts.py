"""Plotly figure builders (pure functions → testable without a browser)."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from processing.language_detection import language_name

COLORS = ["#2563EB", "#0EA5E9", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6", "#EC4899", "#64748B", "#14B8A6", "#F97316"]
SENTIMENT_COLORS = {"إيجابي": "#10B981", "محايد": "#94A3B8", "سلبي": "#EF4444", "مختلط": "#F59E0B"}
FONT = "Tajawal, 'Segoe UI', Tahoma, Arial, sans-serif"
_theme = {"dark": False}


def set_dark(dark: bool) -> None:
    _theme["dark"] = bool(dark)


def _layout(fig: go.Figure, title: str | None = None, height: int = 360) -> go.Figure:
    dark = _theme["dark"]
    fig.update_layout(
        template="plotly_dark" if dark else "plotly_white",
        title={"text": title or "", "x": 0.98, "xanchor": "right", "font": {"size": 15}},
        font={"family": FONT, "size": 12},
        height=height,
        margin={"l": 10, "r": 10, "t": 50 if title else 20, "b": 10},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend={"orientation": "h", "y": -0.18, "x": 1, "xanchor": "right"},
        hoverlabel={"font_family": FONT},
    )
    return fig


def empty_figure(message: str = "لا توجد بيانات") -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False, font={"size": 15})
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return _layout(fig, height=260)


def timeline(df: pd.DataFrame, title: str = "تطور المنشورات عبر الزمن", color: str | None = None) -> go.Figure:
    if df.empty:
        return empty_figure()
    if color and color in df:
        fig = px.line(df, x="period", y="posts", color=color, markers=True, color_discrete_sequence=COLORS)
    else:
        fig = px.area(df, x="period", y="posts", color_discrete_sequence=COLORS)
        fig.update_traces(line={"width": 2.5}, fillcolor="rgba(37,99,235,0.15)")
    fig.update_xaxes(title=None)
    fig.update_yaxes(title="عدد المنشورات")
    return _layout(fig, title)


def bar(df: pd.DataFrame, x: str, y: str, title: str, horizontal: bool = True, color: str = COLORS[0],
        height: int = 400, color_col: str | None = None) -> go.Figure:
    if df.empty:
        return empty_figure()
    d = df.copy()
    if horizontal:
        d = d.iloc[::-1]
        fig = px.bar(d, x=y, y=x, orientation="h", color=color_col,
                     color_discrete_sequence=COLORS if color_col else [color], text=y)
        fig.update_yaxes(title=None, automargin=True)
        fig.update_xaxes(title=None)
    else:
        fig = px.bar(d, x=x, y=y, color=color_col, color_discrete_sequence=COLORS if color_col else [color], text=y)
        fig.update_xaxes(title=None)
        fig.update_yaxes(title=None)
    fig.update_traces(textposition="outside", cliponaxis=False)
    return _layout(fig, title, height)


def languages_pie(df: pd.DataFrame, title: str = "توزيع المنشورات حسب اللغة") -> go.Figure:
    if df.empty:
        return empty_figure()
    d = df.copy()
    d["اللغة"] = d["lang"].map(language_name)
    fig = px.pie(d, names="اللغة", values="posts", hole=0.55, color_discrete_sequence=COLORS)
    fig.update_traces(textinfo="percent+label")
    return _layout(fig, title)


def sentiment_pie(df: pd.DataFrame, title: str = "توزيع المشاعر") -> go.Figure:
    if df.empty or df["posts"].sum() == 0:
        return empty_figure("لم يتم تحليل المشاعر بعد")
    fig = px.pie(df, names="label_ar", values="posts", hole=0.5, color="label_ar", color_discrete_map=SENTIMENT_COLORS)
    fig.update_traces(textinfo="percent+label")
    return _layout(fig, title)


def engagement_hist(df: pd.DataFrame, title: str = "توزيع التفاعل") -> go.Figure:
    if df.empty or df["posts"].sum() == 0:
        return empty_figure("عدادات التفاعل غير متاحة")
    return bar(df, "bucket", "posts", title, horizontal=False, color=COLORS[3], height=340)


def heatmap(pivot: pd.DataFrame, title: str = "النشاط حسب اليوم والساعة") -> go.Figure:
    if pivot is None or pivot.empty:
        return empty_figure()
    days = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
    pivot = pivot.reindex(index=range(7), columns=range(24), fill_value=0)
    fig = go.Figure(go.Heatmap(z=pivot.values, x=[f"{h:02d}" for h in range(24)], y=days, colorscale="Blues",
                               hovertemplate="%{y} %{x}:00 — %{z} منشور<extra></extra>"))
    return _layout(fig, title, 340)


def account_activity(df: pd.DataFrame, title: str = "تحليل نشاط الحسابات") -> go.Figure:
    if df.empty:
        return empty_figure()
    fig = px.bar(df, x="date", y="posts", color="username", color_discrete_sequence=COLORS)
    fig.update_xaxes(title=None)
    fig.update_yaxes(title="منشورات")
    return _layout(fig, title, 380)


def compare_bars(df: pd.DataFrame, x: str, y: str, title: str) -> go.Figure:
    if df.empty:
        return empty_figure()
    fig = px.bar(df, x=x, y=y, color=x, color_discrete_sequence=COLORS, text=y)
    fig.update_traces(texttemplate="%{text:,.1f}", textposition="outside", cliponaxis=False)
    fig.update_layout(showlegend=False)
    fig.update_xaxes(title=None)
    fig.update_yaxes(title=None)
    return _layout(fig, title, 340)


def sentiment_stacked(df: pd.DataFrame, group: str, title: str = "اتجاه المشاعر") -> go.Figure:
    if df.empty:
        return empty_figure("لم يتم تحليل المشاعر بعد")
    fig = px.bar(df, x=group, y="share", color="label_ar", color_discrete_map=SENTIMENT_COLORS, text="share",
                 barmode="stack")
    fig.update_traces(texttemplate="%{text:.0f}%", textposition="inside")
    fig.update_yaxes(title="%", range=[0, 100])
    fig.update_xaxes(title=None)
    return _layout(fig, title, 360)


def topic_bars(topics: pd.DataFrame, title: str = "الموضوعات المكتشفة") -> go.Figure:
    if topics.empty:
        return empty_figure()
    return bar(topics, "label", "posts", title, horizontal=True, color=COLORS[5])


def treemap_words(df: pd.DataFrame, title: str = "الكلمات الأكثر تكراراً") -> go.Figure:
    if df.empty:
        return empty_figure()
    fig = px.treemap(df, path=["word"], values="count", color="count", color_continuous_scale="Blues")
    fig.update_traces(textinfo="label+value")
    fig.update_layout(coloraxis_showscale=False)
    return _layout(fig, title, 380)
