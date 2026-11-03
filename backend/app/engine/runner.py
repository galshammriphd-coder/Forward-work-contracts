"""Analysis registry, context helpers and EDA."""
from __future__ import annotations

import pandas as pd

from . import advanced, charts, descriptive, differences, factor, regression, reliability, text
from .descriptive import describe
from .interpret import interpret
from .utils import AnalysisError, col, result, table, to_jsonable

REGISTRY = {
    "descriptive": (descriptive.run_descriptive, "descriptive"),
    "likert": (descriptive.run_likert, "descriptive"),
    "normality": (descriptive.run_normality, "assumption"),
    "reliability": (reliability.run_reliability, "psychometric"),
    "validity": (reliability.run_validity, "psychometric"),
    "ttest_ind": (differences.run_ttest_ind, "difference"),
    "ttest_paired": (differences.run_ttest_paired, "difference"),
    "ttest_one": (differences.run_onesample, "difference"),
    "mannwhitney": (differences.run_mannwhitney, "difference"),
    "wilcoxon": (differences.run_wilcoxon, "difference"),
    "anova": (differences.run_anova, "difference"),
    "anova_twoway": (differences.run_anova_twoway, "difference"),
    "rm_anova": (differences.run_rm_anova, "difference"),
    "kruskal": (differences.run_kruskal, "difference"),
    "friedman": (differences.run_friedman, "difference"),
    "correlation": (regression.run_correlation, "relationship"),
    "linear": (regression.run_linear, "regression"),
    "hierarchical": (regression.run_hierarchical, "regression"),
    "logistic": (regression.run_logistic, "regression"),
    "ordinal": (regression.run_ordinal, "regression"),
    "efa": (factor.run_efa, "factor"),
    "pca": (factor.run_pca, "factor"),
    "cfa": (factor.run_cfa, "factor"),
    "sem": (factor.run_sem, "advanced"),
    "multigroup": (factor.run_multigroup_cfa, "advanced"),
    "mediation": (advanced.run_mediation, "advanced"),
    "moderation": (advanced.run_moderation, "advanced"),
    "manova": (advanced.run_manova, "advanced"),
    "cluster": (advanced.run_cluster, "advanced"),
    "discriminant": (advanced.run_discriminant, "advanced"),
    "chisquare": (advanced.run_chisquare, "association"),
    "fisher": (advanced.run_fisher, "association"),
    "mcnemar": (advanced.run_mcnemar, "association"),
    "survival": (advanced.run_survival, "advanced"),
    "text": (text.run_text, "qualitative"),
}


def make_ctx(df: pd.DataFrame, dictionary: dict) -> dict:
    vars_ = {v["name"]: v for v in dictionary["variables"]}
    composites = set(df.attrs.get("composites", {}).values())
    derived = {d["name"]: d for d in dictionary.get("derived", [])}

    def var(v):
        if v in vars_:
            return vars_[v]
        if v in composites:
            return {"name": v, "dtype": "numeric", "level": "interval", "role": "composite"}
        if v in derived:
            return {"name": v, "dtype": "categorical" if derived[v]["type"] == "bin" else "numeric",
                    "level": "ordinal" if derived[v]["type"] == "bin" else "interval", "role": "derived"}
        return {"name": v, "dtype": "numeric" if pd.api.types.is_numeric_dtype(df.get(v, pd.Series(dtype=object))) else "categorical", "level": "nominal"}

    def is_numeric(v):
        return var(v).get("dtype") == "numeric" and pd.api.types.is_numeric_dtype(pd.to_numeric(df[v], errors="coerce")) and var(v).get("level") != "nominal"

    def value_labels(v):
        if var(v).get("is_likert"):
            lk = dictionary.get("likert", {})
            anchors = lk.get("anchors_en") or []
            lo = lk.get("min", 1)
            return {lo + i: a for i, a in enumerate(anchors)}
        return None

    return {"dictionary": dictionary, "var": var, "is_numeric": is_numeric, "label": lambda v: var(v).get("label") or v,
            "n_unique": lambda v: int(df[v].nunique()) if v in df.columns else 0, "value_labels": value_labels,
            "is_composite": lambda v: v in composites}


def run_analysis(kind: str, df: pd.DataFrame, dictionary: dict, params: dict, alpha: float = 0.05) -> dict:
    if kind == "eda":
        res = run_eda(df, params, make_ctx(df, dictionary))
    else:
        if kind not in REGISTRY:
            raise AnalysisError(f"Unknown analysis '{kind}'.", f"تحليل غير معروف '{kind}'.")
        fn, _ = REGISTRY[kind]
        try:
            res = fn(df, params, make_ctx(df, dictionary))
        except AnalysisError:
            raise
        except KeyError as exc:
            raise AnalysisError(f"Missing parameter or variable: {exc}", f"معامل أو متغير مفقود: {exc}") from exc
    res["category"] = REGISTRY.get(kind, (None, "exploratory"))[1]
    res["interpretation"] = interpret(res, alpha)
    res["alpha"] = alpha
    return to_jsonable(res)


def run_eda(df: pd.DataFrame, params: dict, ctx: dict) -> dict:
    d = ctx["dictionary"]
    numeric = [c for c in df.columns if ctx["is_numeric"](c) and ctx["var"](c).get("role") not in ("id", "response_time")]
    comps = list(df.attrs.get("composites", {}).values())
    focus = params.get("variables") or (comps or numeric[:12])
    rows = []
    for v in focus:
        if v in df.columns and ctx["is_numeric"](v):
            ds = describe(df[v])
            rows.append({"variable": v, **ds})
    tables = [table("eda_desc", "Distribution summary", "ملخص التوزيعات",
                    [col("variable", "Variable", "المتغير"), col("n", "N", "العدد"), col("mean", "M", "المتوسط", "2"), col("sd", "SD", "الانحراف", "2"),
                     col("median", "Mdn", "الوسيط", "2"), col("min", "Min", "أدنى", "2"), col("max", "Max", "أعلى", "2"), col("skewness", "Skew", "الالتواء", "2"),
                     col("kurtosis", "Kurt", "التفلطح", "2")], rows)]
    ch = []
    for v in focus[:8]:
        if v in df.columns and ctx["is_numeric"](v):
            ch.append(charts.histogram(f"h_{v}", df[v], v, with_normal=False))
            ch.append(charts.box_by_group(f"b_{v}", df, v, params.get("group_by")))
    corr_vars = [v for v in focus if v in df.columns and ctx["is_numeric"](v)]
    if len(corr_vars) >= 2:
        R = df[corr_vars].apply(pd.to_numeric, errors="coerce").corr(method="spearman")
        ch.append(charts.heatmap("eda_corr", R, "Preliminary correlations (Spearman)", "الارتباطات الأولية (سبيرمان)"))
    # demographics
    demo = [v["name"] for v in d["variables"] if v.get("role") == "demographic" and v["name"] in df.columns]
    for v in demo[:6]:
        vc = df[v].dropna().map(lambda x: str(int(x)) if isinstance(x, float) and x.is_integer() else str(x)).value_counts()
        if 1 < len(vc) <= 10:
            ch.append(charts.pie(f"demo_{v}", list(vc.index), vc.values.tolist(), f"Sample by {v}", f"العينة حسب {v}"))
        elif len(vc) > 10 and ctx["is_numeric"](v):
            ch.append(charts.histogram(f"demo_{v}", df[v], v, with_normal=False))
    miss = df.isna().mean().sort_values(ascending=False)
    miss = miss[miss > 0][:25]
    if len(miss):
        ch.append(charts.bar("missing", list(miss.index), [round(100 * m, 2) for m in miss.values], "Missing values by variable (%)", "نسبة القيم المفقودة لكل متغير (%)"))
    return result("eda", "Exploratory data analysis", "التحليل الاستكشافي للبيانات", params=params, n=len(df), tables=tables, charts=ch,
                  stats={"rows": rows}, nature="exploratory")
