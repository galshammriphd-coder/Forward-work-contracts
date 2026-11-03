"""Descriptive statistics, frequencies, Likert-scale analysis and normality assessment."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.diagnostic import lilliefors

from . import charts
from .dictionary import band_for
from .utils import AnalysisError, assumption, col, result, table, to_jsonable, warn


def se_skew(n: int) -> float:
    return math.sqrt(6.0 * n * (n - 1) / ((n - 2) * (n + 1) * (n + 3))) if n > 2 else float("nan")


def se_kurt(n: int) -> float:
    return 2 * se_skew(n) * math.sqrt((n * n - 1) / ((n - 3) * (n + 5))) if n > 3 else float("nan")


def describe(x: pd.Series, conf: float = 0.95) -> dict:
    """SPSS-compatible descriptives: skewness G1 and excess kurtosis G2 (bias-corrected); quartiles by
    the weighted-average method (SPSS default, Hyndman–Fan type 6); t-based CI for the mean."""
    v = pd.to_numeric(x, errors="coerce")
    n_missing = int(v.isna().sum())
    v = v.dropna()
    n = len(v)
    out = {"n": n, "missing": n_missing}
    if n == 0:
        return out
    sd = v.std(ddof=1) if n > 1 else float("nan")
    modes = v.mode()
    q1, med, q3 = np.percentile(v, [25, 50, 75], method="weibull")
    tcrit = stats.t.ppf(0.5 + conf / 2, n - 1) if n > 1 else float("nan")
    se = sd / math.sqrt(n) if n > 1 else float("nan")
    out.update({
        "mean": v.mean(), "median": float(np.median(v)), "mode": float(modes.iloc[0]) if len(modes) else None,
        "multiple_modes": len(modes) > 1, "sd": sd, "variance": v.var(ddof=1) if n > 1 else float("nan"),
        "min": v.min(), "max": v.max(), "range": v.max() - v.min(), "se": se,
        "skewness": stats.skew(v, bias=False) if n > 2 else float("nan"), "se_skewness": se_skew(n),
        "kurtosis": stats.kurtosis(v, bias=False) if n > 3 else float("nan"), "se_kurtosis": se_kurt(n),
        "q1": q1, "q3": q3, "iqr": q3 - q1, "ci_low": v.mean() - tcrit * se, "ci_high": v.mean() + tcrit * se,
        "sum": v.sum(), "cv": sd / v.mean() if v.mean() else float("nan"),
    })
    return to_jsonable(out)


def frequencies(x: pd.Series, order: list | None = None, labels: dict | None = None) -> list[dict]:
    total = len(x)
    valid = x.dropna()
    counts = valid.value_counts()
    keys = order if order is not None else sorted(counts.index, key=lambda k: (isinstance(k, str), k))
    rows, cum = [], 0.0
    for k in keys:
        c = int(counts.get(k, 0))
        pct_valid = 100 * c / len(valid) if len(valid) else 0
        cum += pct_valid
        label = labels.get(k) if labels else None
        rows.append({"value": _fmt_key(k), "label": label, "count": c, "percent": 100 * c / total if total else 0,
                     "valid_percent": pct_valid, "cumulative_percent": cum})
    miss = total - len(valid)
    if miss:
        rows.append({"value": "Missing", "label": "مفقود", "count": miss, "percent": 100 * miss / total,
                     "valid_percent": None, "cumulative_percent": None})
    return to_jsonable(rows)


def _fmt_key(k):
    if isinstance(k, float) and k.is_integer():
        return int(k)
    return k


DESC_COLS = [col("variable", "Variable", "المتغير"), col("n", "N", "العدد"), col("missing", "Missing", "المفقود"),
             col("mean", "M", "المتوسط", "2"), col("sd", "SD", "الانحراف المعياري", "2"), col("se", "SE", "الخطأ المعياري", "3"),
             col("ci", "95% CI", "فترة الثقة 95%"), col("median", "Mdn", "الوسيط", "2"), col("mode", "Mode", "المنوال", "2"),
             col("variance", "Variance", "التباين", "2"), col("min", "Min", "أدنى قيمة", "2"), col("max", "Max", "أعلى قيمة", "2"),
             col("range", "Range", "المدى", "2"), col("q1", "Q1", "الربيع الأول", "2"), col("q3", "Q3", "الربيع الثالث", "2"),
             col("iqr", "IQR", "المدى الربيعي", "2"), col("skewness", "Skewness", "الالتواء", "3"),
             col("kurtosis", "Kurtosis", "التفلطح", "3")]


def run_descriptive(df: pd.DataFrame, params: dict, ctx: dict) -> dict:
    variables = params.get("variables") or []
    if not variables:
        raise AnalysisError("Select at least one variable.", "اختر متغيراً واحداً على الأقل.")
    conf = float(params.get("confidence", 0.95))
    group_by = params.get("group_by")
    rows, tables, charts_out = [], [], []
    numeric_vars = [v for v in variables if ctx["is_numeric"](v)]
    cat_vars = [v for v in variables if v not in numeric_vars]
    for v in numeric_vars:
        d = describe(df[v], conf)
        if d.get("n"):
            d["ci"] = f"[{d['ci_low']:.2f}, {d['ci_high']:.2f}]" if d.get("ci_low") is not None else "—"
        rows.append({"variable": ctx["label"](v), **d})
    if rows:
        tables.append(table("descriptives", "Descriptive statistics", "الإحصاء الوصفي", DESC_COLS, rows,
                            "Skewness and kurtosis are bias-corrected (G1, G2 as in SPSS); quartiles use the weighted-average definition.",
                            "الالتواء والتفلطح مصححان للتحيز (G1, G2 كما في SPSS)؛ والربيعيات بطريقة المتوسط الموزون."))
    if group_by and numeric_vars:
        grows = []
        for v in numeric_vars:
            for g, sub in df.groupby(group_by, observed=True):
                d = describe(sub[v], conf)
                grows.append({"variable": ctx["label"](v), "group": str(g), **d})
        tables.append(table("by_group", f"Descriptives by {group_by}", f"الإحصاء الوصفي حسب {group_by}",
                            [col("variable", "Variable", "المتغير"), col("group", "Group", "المجموعة")] + DESC_COLS[1:5] + DESC_COLS[7:8],
                            grows))
    for v in cat_vars + [v for v in numeric_vars if ctx["n_unique"](v) <= 12]:
        labels = ctx["value_labels"](v)
        tables.append(table(f"freq_{v}", f"Frequencies: {ctx['label'](v)}", f"التكرارات: {ctx['label'](v)}",
                            [col("value", "Value", "القيمة"), col("label", "Label", "التسمية"), col("count", "Frequency", "التكرار"),
                             col("percent", "Percent", "النسبة %", "1"), col("valid_percent", "Valid %", "النسبة الصالحة %", "1"),
                             col("cumulative_percent", "Cumulative %", "النسبة التراكمية %", "1")],
                            frequencies(df[v], labels=labels)))
    for v in numeric_vars[:6]:
        if ctx["n_unique"](v) > 12:
            charts_out.append(charts.histogram(f"hist_{v}", df[v], v))
            charts_out.append(charts.box_by_group(f"box_{v}", df, v, group_by))
    for v in cat_vars[:6]:
        vc = df[v].dropna().astype(str).value_counts()
        if len(vc) <= 8:
            charts_out.append(charts.pie(f"pie_{v}", list(vc.index), vc.values.tolist(), f"Distribution of {v}", f"توزيع {v}"))
        else:
            charts_out.append(charts.bar(f"bar_{v}", list(vc.index), vc.values.tolist(), f"Distribution of {v}", f"توزيع {v}"))
    return result("descriptive", "Descriptive statistics", "الإحصاء الوصفي", params=params, n=len(df), tables=tables,
                  charts=charts_out, stats={"descriptives": rows}, nature="descriptive")


# --------------------------------------------------------------------------------------------
# Likert analysis
# --------------------------------------------------------------------------------------------


def run_likert(df: pd.DataFrame, params: dict, ctx: dict) -> dict:
    d = ctx["dictionary"]
    lk = d["likert"]
    lo, hi = lk["min"], lk["max"]
    bands = params.get("interpretation") or lk["interpretation"]
    points = list(range(int(lo), int(hi) + 1))
    anchors_en = lk.get("anchors_en") or [str(p) for p in points]
    anchors_ar = lk.get("anchors_ar") or [str(p) for p in points]
    if len(anchors_en) != len(points):
        anchors_en = [str(p) for p in points]
        anchors_ar = [str(p) for p in points]
    dims = [dm for dm in d.get("dimensions", []) if not params.get("dimension") or dm["name"] == params["dimension"]]
    item_names = [i for dm in dims for i in dm["items"] if i in df.columns]
    if not item_names:
        item_names = [v["name"] for v in d["variables"] if v.get("is_likert") and v["name"] in df.columns]
        dims = [{"name": "ALL", "label": "All items", "items": item_names}]
    if not item_names:
        raise AnalysisError("No Likert items are defined in the data dictionary.", "لا توجد بنود ليكرت معرفة في قاموس البيانات.")
    item_rows, dist = [], []
    for dm in dims:
        for it in dm["items"]:
            if it not in df.columns:
                continue
            x = pd.to_numeric(df[it], errors="coerce").dropna()
            n = len(x)
            counts = [int((x == p).sum()) for p in points]
            pct = [100 * c / n if n else 0 for c in counts]
            mean, sd = (x.mean(), x.std(ddof=1)) if n > 1 else (float("nan"), float("nan"))
            band = band_for(mean, bands)
            row = {"dimension": dm.get("label") or dm["name"], "item": it, "label": ctx["label"](it), "n": n, "mean": mean, "sd": sd,
                   "relative_weight": 100 * (mean - lo) / (hi - lo) if n else None,
                   "level_en": band["en"] if band else None, "level_ar": band["ar"] if band else None,
                   "reverse": ctx["var"](it).get("reverse", False)}
            for p, c, pc in zip(points, counts, pct):
                row[f"f{p}"] = c
                row[f"p{p}"] = pc
            item_rows.append(row)
            dist.append(pct)
    # rank within dimension and overall
    for dm in dims:
        sub = [r for r in item_rows if r["dimension"] == (dm.get("label") or dm["name"]) and r["mean"] is not None]
        for rank, r in enumerate(sorted(sub, key=lambda r: -r["mean"]), 1):
            r["rank"] = rank
    dim_rows = []
    for dm in dims:
        items = [i for i in dm["items"] if i in df.columns]
        if not items:
            continue
        score = df[items].apply(pd.to_numeric, errors="coerce").mean(axis=1, skipna=True)
        score = score.where(df[items].notna().mean(axis=1) >= 0.5).dropna()
        m = score.mean()
        band = band_for(m, bands)
        dim_rows.append({"dimension": dm.get("label") or dm["name"], "items": len(items), "n": len(score), "mean": m,
                         "sd": score.std(ddof=1), "relative_weight": 100 * (m - lo) / (hi - lo),
                         "level_en": band["en"] if band else None, "level_ar": band["ar"] if band else None})
    for rank, r in enumerate(sorted(dim_rows, key=lambda r: -(r["mean"] or 0)), 1):
        r["rank"] = rank
    all_items = df[item_names].apply(pd.to_numeric, errors="coerce")
    overall = all_items.mean(axis=1).where(all_items.notna().mean(axis=1) >= 0.5).dropna()
    ob = band_for(overall.mean(), bands)
    valid_items = [r for r in item_rows if r["mean"] is not None]
    top = sorted(valid_items, key=lambda r: -r["mean"])[:3]
    bottom = sorted(valid_items, key=lambda r: r["mean"])[:3]
    item_cols = [col("dimension", "Dimension", "البعد"), col("item", "Item", "البند"), col("n", "N", "العدد")]
    for p, ae, aa in zip(points, anchors_en, anchors_ar):
        item_cols.append(col(f"p{p}", f"{p} ({ae}) %", f"{p} ({aa}) %", "1"))
    item_cols += [col("mean", "M", "المتوسط", "2"), col("sd", "SD", "الانحراف", "2"),
                  col("relative_weight", "Relative weight %", "الوزن النسبي %", "1"),
                  col("level_en", "Level", "المستوى"), col("rank", "Rank", "الترتيب")]
    band_text_en = "; ".join(f"{b['from']:.2f}–{b['to']:.2f} = {b['en']}" for b in bands)
    band_text_ar = "؛ ".join(f"{b['from']:.2f}–{b['to']:.2f} = {b['ar']}" for b in bands)
    tables = [
        table("likert_items", "Item statistics", "إحصاءات البنود", item_cols, item_rows,
              f"Scale {lo}–{hi}. Interpretation bands: {band_text_en}. Relative weight = (M − min)/(max − min) × 100. Reverse items are shown after recoding.",
              f"المقياس {lo}–{hi}. حدود التفسير: {band_text_ar}. الوزن النسبي = (المتوسط − الحد الأدنى)/(المدى) × 100. البنود العكسية معروضة بعد إعادة الترميز."),
        table("likert_dims", "Dimension statistics", "إحصاءات الأبعاد",
              [col("dimension", "Dimension", "البعد"), col("items", "Items", "عدد البنود"), col("n", "N", "العدد"),
               col("mean", "M", "المتوسط", "2"), col("sd", "SD", "الانحراف", "2"),
               col("relative_weight", "Relative weight %", "الوزن النسبي %", "1"), col("level_en", "Level", "المستوى"),
               col("rank", "Rank", "الترتيب")], dim_rows),
    ]
    ch = [charts.stacked_likert("likert_stack", [r["item"] for r in item_rows], dist, [f"{p} {a}" for p, a in zip(points, anchors_en)],
                                "Response distribution per item", "توزيع الاستجابات لكل بند"),
          charts.bar("dim_means", [r["dimension"] for r in dim_rows], [r["mean"] for r in dim_rows], "Dimension means",
                     "متوسطات الأبعاد", error=[r["sd"] for r in dim_rows], yrange=[lo, hi])]
    if len(dim_rows) >= 3:
        ch.append(charts.radar("dim_radar", [r["dimension"] for r in dim_rows], [r["mean"] for r in dim_rows],
                               "Dimension profile", "ملف الأبعاد", [lo, hi]))
    return result("likert", "Likert scale analysis", "تحليل مقياس ليكرت", params=params, n=len(df), tables=tables, charts=ch,
                  stats={"overall_mean": overall.mean(), "overall_sd": overall.std(ddof=1), "overall_level_en": ob["en"] if ob else None,
                         "overall_level_ar": ob["ar"] if ob else None, "top": top, "bottom": bottom, "dimensions": dim_rows,
                         "scale": [lo, hi], "bands": bands}, nature="descriptive",
                  warnings=[warn("Treating Likert means as interval data is a convention; report medians/frequencies for single items when appropriate.",
                                 "معاملة متوسطات ليكرت كبيانات فترية عُرف شائع؛ يُفضّل عرض الوسيط والتكرارات للبنود المفردة عند الاقتضاء.")])


# --------------------------------------------------------------------------------------------
# Normality
# --------------------------------------------------------------------------------------------


def normality(x: pd.Series) -> dict:
    v = pd.to_numeric(x, errors="coerce").dropna().to_numpy(dtype=float)
    n = len(v)
    out = {"n": n}
    if n < 3 or np.std(v) == 0:
        out["error"] = "insufficient variation or n < 3"
        return out
    sk, ku = stats.skew(v, bias=False), stats.kurtosis(v, bias=False) if n > 3 else float("nan")
    out.update({"skewness": sk, "kurtosis": ku, "z_skewness": sk / se_skew(n), "z_kurtosis": ku / se_kurt(n) if n > 3 else None})
    if n <= 5000:
        w, p = stats.shapiro(v)
        out.update({"shapiro_w": w, "shapiro_p": p})
    if n >= 5:
        d, p = lilliefors(v, dist="norm", pvalmethod="table")
        out.update({"ks_d": d, "ks_p": p})
    try:  # SciPy >= 1.17: interpolated p-value
        ad = stats.anderson(v, dist="norm", method="interpolate")
        out.update({"ad_stat": ad.statistic, "ad_p": ad.pvalue})
    except TypeError:  # older SciPy: compare with the 5% critical value
        ad = stats.anderson(v, dist="norm")
        idx = list(ad.significance_level).index(5.0)
        out.update({"ad_stat": ad.statistic, "ad_p": 0.01 if ad.statistic > ad.critical_values[idx] else 0.10})
    # Decision rule that weighs sample size (not p alone)
    if n < 50:
        normal = out.get("shapiro_p", 0) >= 0.05
        basis_en, basis_ar = "Shapiro–Wilk (n < 50)", "شابيرو–ويلك (n < 50)"
    elif n < 300:
        normal = abs(out["z_skewness"]) < 3.29 and abs(out["z_kurtosis"] or 0) < 3.29
        basis_en, basis_ar = "|z| of skewness and kurtosis < 3.29 (50 ≤ n < 300)", "القيمة المطلقة لـ z للالتواء والتفلطح < 3.29 (50 ≤ n < 300)"
    else:
        normal = abs(sk) < 2 and abs(ku) < 7
        basis_en, basis_ar = "|skewness| < 2 and |kurtosis| < 7 (n ≥ 300; Kim, 2013)", "|الالتواء| < 2 و|التفلطح| < 7 (n ≥ 300؛ Kim, 2013)"
    out.update({"approximately_normal": bool(normal), "basis_en": basis_en, "basis_ar": basis_ar})
    return to_jsonable(out)


def run_normality(df: pd.DataFrame, params: dict, ctx: dict) -> dict:
    variables = params.get("variables") or []
    if not variables:
        raise AnalysisError("Select at least one numeric variable.", "اختر متغيراً رقمياً واحداً على الأقل.")
    group_by = params.get("group_by")
    rows, ch = [], []
    targets = []
    for v in variables:
        if group_by:
            for g, sub in df.groupby(group_by, observed=True):
                targets.append((v, str(g), sub[v]))
        else:
            targets.append((v, None, df[v]))
    for v, g, s in targets:
        r = normality(s)
        rows.append({"variable": ctx["label"](v), "group": g, **r,
                     "decision_en": ("Approximately normal" if r.get("approximately_normal") else "Departs from normality") if "error" not in r else r["error"],
                     "decision_ar": ("قريب من التوزيع الطبيعي" if r.get("approximately_normal") else "ينحرف عن التوزيع الطبيعي") if "error" not in r else r["error"]})
    for v in variables[:4]:
        ch.append(charts.histogram(f"nh_{v}", df[v], v))
        ch.append(charts.qq_plot(f"qq_{v}", df[v], v))
    cols = [col("variable", "Variable", "المتغير")] + ([col("group", "Group", "المجموعة")] if group_by else []) + [
        col("n", "N", "العدد"), col("skewness", "Skewness", "الالتواء", "3"), col("z_skewness", "z skew", "z الالتواء", "2"),
        col("kurtosis", "Kurtosis", "التفلطح", "3"), col("z_kurtosis", "z kurt", "z التفلطح", "2"),
        col("shapiro_w", "Shapiro–Wilk W", "W شابيرو–ويلك", "3"), col("shapiro_p", "p (S–W)", "p (ش–و)", "p"),
        col("ks_d", "K–S D (Lilliefors)", "D كولموجوروف–سميرنوف (ليليفورس)", "3"), col("ks_p", "p (K–S)", "p (ك–س)", "p"),
        col("ad_stat", "Anderson–Darling A²", "A² أندرسون–دارلنج", "3"), col("ad_p", "p (A–D)", "p (أ–د)", "p"),
        col("decision_en", "Assessment", "التقييم"), col("basis_en", "Basis", "الأساس")]
    return result("normality", "Normality assessment", "اختبارات التوزيع الطبيعي", params=params, n=len(df),
                  tables=[table("normality", "Tests of normality", "اختبارات التوزيع الطبيعي", cols, rows,
                                "K–S uses the Lilliefors correction because the mean and SD are estimated from the sample (the classic K–S test requires fully specified parameters). Large samples make tests over-sensitive: inspect the plots and skewness/kurtosis.",
                                "يُستخدم تصحيح ليليفورس لاختبار K–S لأن المتوسط والانحراف مقدَّران من العينة (يتطلب اختبار K–S التقليدي معلمات محددة مسبقاً). في العينات الكبيرة تصبح الاختبارات شديدة الحساسية؛ لذا تُفحص الرسوم ومؤشرات الالتواء والتفلطح.")],
                  charts=ch, stats={"rows": rows}, nature="assumption")
