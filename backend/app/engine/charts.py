"""Plotly figure specifications built from real data.

The backend returns plain JSON figure specs ({data, layout}); the frontend renders them
with Plotly (interactive, PNG/SVG export). No values are hard coded.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from .utils import to_jsonable

PALETTE = ["#2563eb", "#0d9488", "#d97706", "#7c3aed", "#db2777", "#475569", "#65a30d", "#0891b2"]


def _fig(cid: str, title_en: str, title_ar: str, data: list, layout: dict | None = None) -> dict:
    lay = {"margin": {"l": 50, "r": 20, "t": 40, "b": 50}, "colorway": PALETTE}
    lay.update(layout or {})
    return to_jsonable({"id": cid, "title_en": title_en, "title_ar": title_ar,
                        "figure": {"data": data, "layout": lay}})


def _vals(s: pd.Series) -> list:
    return [None if pd.isna(v) else float(v) for v in s]


def histogram(cid: str, s: pd.Series, name: str, with_normal: bool = True) -> dict:
    x = pd.to_numeric(s, errors="coerce").dropna()
    data = [{"type": "histogram", "x": _vals(x), "name": name, "histnorm": "probability density" if with_normal else "",
             "opacity": 0.75}]
    if with_normal and len(x) > 2 and x.std() > 0:
        grid = np.linspace(x.min(), x.max(), 80)
        data.append({"type": "scatter", "mode": "lines", "x": grid.tolist(),
                     "y": stats.norm.pdf(grid, x.mean(), x.std(ddof=1)).tolist(), "name": "Normal"})
    return _fig(cid, f"Histogram: {name}", f"المدرج التكراري: {name}", data,
                {"xaxis": {"title": {"text": name}}, "showlegend": with_normal, "bargap": 0.05})


def qq_plot(cid: str, s: pd.Series, name: str) -> dict:
    x = np.sort(pd.to_numeric(s, errors="coerce").dropna().to_numpy())
    n = len(x)
    if n < 3:
        return _fig(cid, f"Q-Q: {name}", f"مخطط Q-Q: {name}", [])
    theo = stats.norm.ppf((np.arange(1, n + 1) - 0.375) / (n + 0.25))  # Blom, as in SPSS
    slope, intercept = x.std(ddof=1), x.mean()
    return _fig(cid, f"Normal Q-Q plot: {name}", f"مخطط Q-Q الطبيعي: {name}", [
        {"type": "scatter", "mode": "markers", "x": theo.tolist(), "y": x.tolist(), "name": "Observed",
         "marker": {"size": 5}},
        {"type": "scatter", "mode": "lines", "x": [float(theo[0]), float(theo[-1])],
         "y": [float(intercept + slope * theo[0]), float(intercept + slope * theo[-1])], "name": "Expected"},
    ], {"xaxis": {"title": {"text": "Theoretical quantiles"}}, "yaxis": {"title": {"text": "Observed"}},
        "showlegend": False})


def box_by_group(cid: str, df: pd.DataFrame, value: str, group: str | None, violin: bool = False) -> dict:
    data = []
    if group:
        for g, sub in df.groupby(group, observed=True):
            v = pd.to_numeric(sub[value], errors="coerce").dropna()
            tr = {"type": "violin" if violin else "box", "y": _vals(v), "name": str(g)}
            if violin:
                tr.update({"box": {"visible": True}, "meanline": {"visible": True}})
            else:
                tr["boxmean"] = True
            data.append(tr)
    else:
        v = pd.to_numeric(df[value], errors="coerce").dropna()
        tr = {"type": "violin" if violin else "box", "y": _vals(v), "name": value}
        if violin:
            tr.update({"box": {"visible": True}, "meanline": {"visible": True}})
        else:
            tr["boxmean"] = True
        data.append(tr)
    kind_en, kind_ar = ("Violin plot", "مخطط الكمان") if violin else ("Box plot", "المخطط الصندوقي")
    return _fig(cid, f"{kind_en}: {value}" + (f" by {group}" if group else ""),
                f"{kind_ar}: {value}" + (f" حسب {group}" if group else ""), data,
                {"showlegend": False, "yaxis": {"title": {"text": value}}})


def bar(cid: str, labels: list, values: list, title_en: str, title_ar: str, horizontal: bool = False,
        error: list | None = None, yrange: list | None = None) -> dict:
    tr = {"type": "bar", "x": values if horizontal else labels, "y": labels if horizontal else values,
          "orientation": "h" if horizontal else "v", "text": [None if v is None else round(float(v), 2) for v in values],
          "textposition": "auto"}
    if error is not None:
        tr["error_x" if horizontal else "error_y"] = {"type": "data", "array": error, "visible": True}
    layout = {"showlegend": False}
    if yrange:
        layout["xaxis" if horizontal else "yaxis"] = {"range": yrange}
    if horizontal:
        layout["yaxis"] = {"automargin": True, "autorange": "reversed"}
        layout["margin"] = {"l": 140, "r": 20, "t": 40, "b": 40}
    return _fig(cid, title_en, title_ar, [tr], layout)


def pie(cid: str, labels: list, values: list, title_en: str, title_ar: str) -> dict:
    return _fig(cid, title_en, title_ar, [{"type": "pie", "labels": [str(l) for l in labels], "values": values,
                                            "hole": 0.45, "textinfo": "percent+label"}], {"showlegend": True})


def stacked_likert(cid: str, items: list[str], dist: list[list[float]], labels: list[str],
                   title_en: str, title_ar: str) -> dict:
    colors = ["#b91c1c", "#f97316", "#a3a3a3", "#60a5fa", "#1d4ed8", "#1e3a8a", "#172554"]
    colors_by_n = {2: [colors[0], colors[4]], 3: [colors[0], colors[2], colors[4]],
                   4: [colors[0], colors[1], colors[3], colors[4]], 5: colors[:5]}
    cols = colors_by_n.get(len(labels), None)
    data = []
    for j, lab in enumerate(labels):
        tr = {"type": "bar", "orientation": "h", "y": items, "x": [row[j] for row in dist], "name": lab,
              "hovertemplate": "%{y}: %{x:.1f}%<extra>" + lab + "</extra>"}
        if cols:
            tr["marker"] = {"color": cols[j]}
        data.append(tr)
    return _fig(cid, title_en, title_ar, data, {"barmode": "stack", "xaxis": {"title": {"text": "%"}, "range": [0, 100]},
                                                "yaxis": {"automargin": True, "autorange": "reversed"},
                                                "legend": {"orientation": "h", "y": -0.15},
                                                "margin": {"l": 140, "r": 20, "t": 40, "b": 60}})


def heatmap(cid: str, matrix: pd.DataFrame, title_en: str, title_ar: str, zrange=(-1, 1)) -> dict:
    z = [[None if pd.isna(v) else round(float(v), 3) for v in row] for row in matrix.to_numpy()]
    return _fig(cid, title_en, title_ar, [{
        "type": "heatmap", "z": z, "x": [str(c) for c in matrix.columns], "y": [str(i) for i in matrix.index],
        "zmin": zrange[0], "zmax": zrange[1], "colorscale": "RdBu", "reversescale": True,
        "text": z, "texttemplate": "%{text:.2f}" if len(matrix) <= 15 else "", "hoverongaps": False}],
        {"yaxis": {"autorange": "reversed", "automargin": True}, "xaxis": {"automargin": True}})


def scatter(cid: str, x: pd.Series, y: pd.Series, xname: str, yname: str, fit: bool = True) -> dict:
    d = pd.DataFrame({"x": pd.to_numeric(x, errors="coerce"), "y": pd.to_numeric(y, errors="coerce")}).dropna()
    data = [{"type": "scatter", "mode": "markers", "x": _vals(d["x"]), "y": _vals(d["y"]), "name": "Data",
             "marker": {"size": 6, "opacity": 0.6}}]
    if fit and len(d) > 2 and d["x"].std() > 0:
        b, a = np.polyfit(d["x"], d["y"], 1)
        xs = [float(d["x"].min()), float(d["x"].max())]
        data.append({"type": "scatter", "mode": "lines", "x": xs, "y": [a + b * v for v in xs], "name": "OLS fit"})
    return _fig(cid, f"{yname} vs {xname}", f"{yname} مقابل {xname}", data,
                {"xaxis": {"title": {"text": xname}}, "yaxis": {"title": {"text": yname}}, "showlegend": False})


def line(cid: str, x: list, ys: dict[str, list], title_en: str, title_ar: str, xtitle: str = "", ytitle: str = "",
         dash: dict | None = None) -> dict:
    data = []
    for name, y in ys.items():
        tr = {"type": "scatter", "mode": "lines+markers", "x": x, "y": y, "name": name}
        if dash and name in dash:
            tr["line"] = {"dash": dash[name]}
        data.append(tr)
    return _fig(cid, title_en, title_ar, data, {"xaxis": {"title": {"text": xtitle}}, "yaxis": {"title": {"text": ytitle}}})


def radar(cid: str, labels: list[str], values: list[float], title_en: str, title_ar: str, rng: list | None = None) -> dict:
    return _fig(cid, title_en, title_ar, [{"type": "scatterpolar", "r": values + values[:1], "theta": labels + labels[:1],
                                            "fill": "toself", "name": "Mean"}],
                {"polar": {"radialaxis": {"visible": True, "range": rng}}, "showlegend": False})
