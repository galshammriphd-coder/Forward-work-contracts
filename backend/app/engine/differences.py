"""Difference tests with assumption checks, effect sizes, CIs and post-hoc procedures."""
from __future__ import annotations

import itertools
import math

import numpy as np
import pandas as pd
import pingouin as pg
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import stats
from statsmodels.stats.multitest import multipletests

from . import charts
from .descriptive import normality
from .utils import AnalysisError, assumption, cohen_label, col, fp, require_columns, require_n, result, table, to_jsonable, warn


def _groups(df: pd.DataFrame, dv: str, group: str) -> tuple[pd.DataFrame, list]:
    require_columns(df, [dv, group])
    d = pd.DataFrame({"y": pd.to_numeric(df[dv], errors="coerce"), "g": df[group]}).dropna()
    d["g"] = d["g"].map(lambda v: str(int(v)) if isinstance(v, float) and v.is_integer() else str(v))
    levels = sorted(d["g"].unique(), key=lambda s: (len(s), s))
    return d, levels


def _group_desc(d: pd.DataFrame, levels) -> list[dict]:
    rows = []
    for g in levels:
        y = d.loc[d["g"] == g, "y"]
        n = len(y)
        se = y.std(ddof=1) / math.sqrt(n) if n > 1 else float("nan")
        t = stats.t.ppf(0.975, n - 1) if n > 1 else float("nan")
        rows.append({"group": g, "n": n, "mean": y.mean(), "sd": y.std(ddof=1), "se": se, "median": y.median(),
                     "ci_low": y.mean() - t * se, "ci_high": y.mean() + t * se})
    return rows


GDESC_COLS = [col("group", "Group", "المجموعة"), col("n", "N", "العدد"), col("mean", "M", "المتوسط", "2"), col("sd", "SD", "الانحراف", "2"),
              col("se", "SE", "الخطأ المعياري", "3"), col("median", "Mdn", "الوسيط", "2"), col("ci_low", "95% CI low", "الحد الأدنى", "2"),
              col("ci_high", "95% CI high", "الحد الأعلى", "2")]


def _normality_assumptions(d, levels) -> tuple[list, bool]:
    out, all_ok = [], True
    for g in levels:
        r = normality(d.loc[d["g"] == g, "y"])
        if "error" in r:
            continue
        ok = r["approximately_normal"]
        all_ok &= ok
        sw = f"W = {r['shapiro_w']:.3f}, p {fp(r['shapiro_p'])}" if r.get("shapiro_w") is not None else ""
        out.append(assumption(f"Normality ({g})", f"الاعتدالية ({g})", "Shapiro–Wilk / skewness–kurtosis", ok,
                              f"n = {r['n']}, {sw}, skew = {r['skewness']:.2f}, kurt = {r['kurtosis']:.2f}; {r['basis_en']}",
                              f"n = {r['n']}، {sw}، الالتواء = {r['skewness']:.2f}، التفلطح = {r['kurtosis']:.2f}؛ {r['basis_ar']}",
                              r.get("shapiro_w"), r.get("shapiro_p")))
    return out, all_ok


def _levene(d, levels):
    samples = [d.loc[d["g"] == g, "y"].to_numpy() for g in levels]
    W, p = stats.levene(*samples, center="mean")
    return assumption("Homogeneity of variances", "تجانس التباين", "Levene (mean-centred, as SPSS)", p >= 0.05,
                      f"F = {W:.3f}, p {fp(p)}", f"F = {W:.3f}، p {fp(p)}", W, p), p >= 0.05, W, p


def _alt(alternative: str | None) -> str:
    return {"greater": "greater", "less": "less"}.get(alternative or "", "two-sided")


# --------------------------------------------------------------------------------------------
def run_ttest_ind(df, params, ctx):
    dv, group = params["dv"], params["group"]
    d, levels = _groups(df, dv, group)
    if params.get("levels"):
        levels = [str(x) for x in params["levels"]][:2]
        d = d[d["g"].isin(levels)]
    if len(levels) != 2:
        raise AnalysisError(f"The grouping variable must have exactly 2 groups (found {len(levels)}). Select two levels or use ANOVA.",
                            f"يجب أن يحتوي متغير التجميع على مجموعتين فقط (وُجد {len(levels)}). اختر مستويين أو استخدم ANOVA.")
    a, b = (d.loc[d["g"] == g, "y"] for g in levels)
    require_n(min(len(a), len(b)), 2, "each group")
    alt = _alt(params.get("alternative"))
    norm_a, norm_ok = _normality_assumptions(d, levels)
    lev_a, equal_var, W, lp = _levene(d, levels)
    student = pg.ttest(a, b, paired=False, alternative=alt, correction=False).iloc[0]
    welch = pg.ttest(a, b, paired=False, alternative=alt, correction=True).iloc[0]
    use = student if equal_var else welch
    n1, n2 = len(a), len(b)
    diff = a.mean() - b.mean()
    sp = math.sqrt(((n1 - 1) * a.var(ddof=1) + (n2 - 1) * b.var(ddof=1)) / (n1 + n2 - 2))
    d_cohen = diff / sp if sp > 0 else float("nan")
    g_hedges = d_cohen * (1 - 3 / (4 * (n1 + n2) - 9))
    se_d = math.sqrt((n1 + n2) / (n1 * n2) + d_cohen ** 2 / (2 * (n1 + n2)))
    def _row(r, label_en, label_ar, eq):
        # exact two-sided 95% CI of the mean difference (pingouin rounds its CI to 2 decimals)
        se = sp * math.sqrt(1 / n1 + 1 / n2) if eq else math.sqrt(a.var(ddof=1) / n1 + b.var(ddof=1) / n2)
        q = stats.t.ppf(0.975, r["dof"])
        lo, hi = diff - q * se, diff + q * se
        return {"test_en": label_en, "test_ar": label_ar, "t": r["T"], "df": r["dof"], "p": r["p_val"] if "p_val" in r else r["p-val"],
                "mean_diff": diff, "ci_low": lo, "ci_high": hi, "equal_var": eq}
    rows = [_row(student, "Student's t (equal variances)", "ت ستيودنت (تباين متساوٍ)", True),
            _row(welch, "Welch's t (unequal variances)", "ت ويلش (تباين غير متساوٍ)", False)]
    chosen = rows[0] if equal_var else rows[1]
    mag = cohen_label(d_cohen, "d")
    st = {"dv": dv, "group": group, "levels": levels, "t": chosen["t"], "df": chosen["df"], "p": chosen["p"], "mean_diff": diff,
          "ci_low": chosen["ci_low"], "ci_high": chosen["ci_high"], "cohens_d": d_cohen, "hedges_g": g_hedges,
          "d_ci_low": d_cohen - 1.96 * se_d, "d_ci_high": d_cohen + 1.96 * se_d, "effect_label_en": mag[0], "effect_label_ar": mag[1],
          "test_used": "Student" if equal_var else "Welch", "alternative": alt, "groups": _group_desc(d, levels), "normal": norm_ok}
    warns = []
    if not norm_ok and min(n1, n2) < 30:
        warns.append(warn("Normality is doubtful with small groups; the Mann–Whitney U test is a robust alternative.",
                          "الاعتدالية موضع شك مع مجموعات صغيرة؛ ويُعد اختبار مان–ويتني بديلاً مناسباً."))
    return result("ttest_ind", "Independent-samples t-test", "اختبار (ت) لعينتين مستقلتين", params=params, n=len(d),
                  tables=[table("groups", "Group statistics", "إحصاءات المجموعات", GDESC_COLS, st["groups"]),
                          table("ttest", "Independent-samples test", "نتائج اختبار العينتين المستقلتين",
                                [col("test_en", "Test", "الاختبار"), col("t", "t", "ت", "3"), col("df", "df", "د.ح", "2"), col("p", "p", "p", "p"),
                                 col("mean_diff", "Mean difference", "فرق المتوسطين", "3"), col("ci_low", "95% CI low", "الحد الأدنى", "3"),
                                 col("ci_high", "95% CI high", "الحد الأعلى", "3")], rows,
                                f"Reported test: {st['test_used']} (based on Levene's test). Cohen's d = {d_cohen:.3f}, Hedges' g = {g_hedges:.3f}.",
                                f"الاختبار المعتمد: {'ستيودنت' if equal_var else 'ويلش'} (بناءً على اختبار ليفين). d كوهين = {d_cohen:.3f}، g هيدجز = {g_hedges:.3f}.")],
                  charts=[charts.box_by_group("box", d.rename(columns={"y": dv, "g": group}), dv, group),
                          charts.box_by_group("violin", d.rename(columns={"y": dv, "g": group}), dv, group, violin=True)],
                  assumptions=norm_a + [lev_a], stats=st, warnings=warns)


def run_mannwhitney(df, params, ctx):
    dv, group = params["dv"], params["group"]
    d, levels = _groups(df, dv, group)
    if params.get("levels"):
        levels = [str(x) for x in params["levels"]][:2]
        d = d[d["g"].isin(levels)]
    if len(levels) != 2:
        raise AnalysisError("Mann–Whitney U requires exactly 2 groups.", "يتطلب اختبار مان–ويتني مجموعتين فقط.")
    a, b = (d.loc[d["g"] == g, "y"].to_numpy() for g in levels)
    alt = _alt(params.get("alternative"))
    U, p = stats.mannwhitneyu(a, b, alternative=alt, method="asymptotic", use_continuity=True)
    n1, n2 = len(a), len(b)
    ranks = stats.rankdata(np.concatenate([a, b]))
    _, tie_counts = np.unique(ranks, return_counts=True)
    N = n1 + n2
    sigma = math.sqrt(n1 * n2 / 12 * ((N + 1) - (tie_counts ** 3 - tie_counts).sum() / (N * (N - 1))))
    z = (U - n1 * n2 / 2) / sigma if sigma > 0 else float("nan")
    r = abs(z) / math.sqrt(N)
    rbc = 1 - 2 * U / (n1 * n2)
    rows = []
    for g, arr, rk in [(levels[0], a, ranks[:n1]), (levels[1], b, ranks[n1:])]:
        rows.append({"group": g, "n": len(arr), "median": float(np.median(arr)), "mean_rank": rk.mean(), "sum_ranks": rk.sum()})
    mag = cohen_label(r, "r")
    st = {"dv": dv, "group": group, "levels": levels, "U": U, "z": z, "p": p, "r": r, "rank_biserial": rbc,
          "effect_label_en": mag[0], "effect_label_ar": mag[1], "groups": rows, "alternative": alt}
    return result("mannwhitney", "Mann–Whitney U test", "اختبار مان–ويتني", params=params, n=N,
                  tables=[table("ranks", "Ranks", "الرتب", [col("group", "Group", "المجموعة"), col("n", "N", "العدد"), col("median", "Mdn", "الوسيط", "2"),
                                                          col("mean_rank", "Mean rank", "متوسط الرتب", "2"), col("sum_ranks", "Sum of ranks", "مجموع الرتب", "1")], rows),
                          table("mw", "Test statistics", "إحصاءات الاختبار", [col("U", "U", "U", "1"), col("z", "Z", "Z", "3"), col("p", "p", "p", "p"),
                                                                             col("r", "r = |Z|/√N", "r", "3"), col("rank_biserial", "Rank-biserial", "الارتباط الرتبي الثنائي", "3")], [st],
                                "Asymptotic p with continuity and tie correction.", "قيمة p تقريبية مع تصحيح الاستمرارية والرتب المتساوية.")],
                  charts=[charts.box_by_group("box", d.rename(columns={"y": dv, "g": group}), dv, group)], stats=st)


def run_ttest_paired(df, params, ctx):
    a_, b_ = params["var1"], params["var2"]
    require_columns(df, [a_, b_])
    d = df[[a_, b_]].apply(pd.to_numeric, errors="coerce").dropna()
    require_n(len(d), 3, "paired test")
    alt = _alt(params.get("alternative"))
    r = pg.ttest(d[a_], d[b_], paired=True, alternative=alt).iloc[0]
    diff = d[a_] - d[b_]
    dz = diff.mean() / diff.std(ddof=1)
    nr = normality(diff)
    q = stats.t.ppf(0.975, len(d) - 1)
    se_d = diff.std(ddof=1) / math.sqrt(len(d))
    ci = (diff.mean() - q * se_d, diff.mean() + q * se_d)
    mag = cohen_label(dz, "d")
    st = {"var1": a_, "var2": b_, "n": len(d), "mean1": d[a_].mean(), "mean2": d[b_].mean(), "sd1": d[a_].std(), "sd2": d[b_].std(),
          "mean_diff": diff.mean(), "sd_diff": diff.std(ddof=1), "t": r["T"], "df": r["dof"], "p": r["p_val"] if "p_val" in r else r["p-val"],
          "ci_low": ci[0], "ci_high": ci[1], "cohens_dz": dz, "r_pairs": d[a_].corr(d[b_]), "effect_label_en": mag[0], "effect_label_ar": mag[1]}
    return result("ttest_paired", "Paired-samples t-test", "اختبار (ت) للعينات المترابطة", params=params, n=len(d),
                  tables=[table("paired", "Paired-samples test", "نتائج اختبار العينات المترابطة",
                                [col("mean1", f"M ({a_})", f"المتوسط ({a_})", "2"), col("mean2", f"M ({b_})", f"المتوسط ({b_})", "2"),
                                 col("mean_diff", "Mean diff.", "فرق المتوسطين", "3"), col("sd_diff", "SD diff.", "انحراف الفروق", "3"),
                                 col("t", "t", "ت", "3"), col("df", "df", "د.ح", "0"), col("p", "p", "p", "p"), col("ci_low", "95% CI low", "الحد الأدنى", "3"),
                                 col("ci_high", "95% CI high", "الحد الأعلى", "3"), col("cohens_dz", "Cohen's dz", "dz كوهين", "3")], [st])],
                  assumptions=[assumption("Normality of differences", "اعتدالية الفروق", "Shapiro–Wilk", nr.get("approximately_normal"),
                                          f"n = {nr['n']}; {nr.get('basis_en', '')}", f"n = {nr['n']}؛ {nr.get('basis_ar', '')}", nr.get("shapiro_w"), nr.get("shapiro_p"))],
                  charts=[charts.histogram("diff_hist", diff, f"{a_} − {b_}")], stats=st)


def run_wilcoxon(df, params, ctx):
    a_, b_ = params["var1"], params["var2"]
    d = df[[a_, b_]].apply(pd.to_numeric, errors="coerce").dropna()
    diff = (d[a_] - d[b_]).to_numpy()
    nz = diff[diff != 0]
    require_n(len(nz), 3, "non-zero differences")
    res = stats.wilcoxon(d[a_], d[b_], zero_method="wilcox", correction=False, alternative=_alt(params.get("alternative")), method="approx")
    n = len(nz)
    ranks = stats.rankdata(np.abs(nz))
    _, t = np.unique(ranks, return_counts=True)
    mu, sigma = n * (n + 1) / 4, math.sqrt(n * (n + 1) * (2 * n + 1) / 24 - (t ** 3 - t).sum() / 48)
    wplus = ranks[nz > 0].sum()
    z = (wplus - mu) / sigma
    r = abs(z) / math.sqrt(n)
    mag = cohen_label(r, "r")
    st = {"var1": a_, "var2": b_, "n": len(d), "n_nonzero": n, "positive_ranks": int((nz > 0).sum()), "negative_ranks": int((nz < 0).sum()),
          "ties": int((diff == 0).sum()), "W": res.statistic, "z": z, "p": res.pvalue, "r": r, "median1": d[a_].median(), "median2": d[b_].median(),
          "effect_label_en": mag[0], "effect_label_ar": mag[1]}
    return result("wilcoxon", "Wilcoxon signed-rank test", "اختبار ويلكوكسون للرتب المؤشرة", params=params, n=len(d),
                  tables=[table("wil", "Test statistics", "إحصاءات الاختبار",
                                [col("median1", f"Mdn ({a_})", f"الوسيط ({a_})", "2"), col("median2", f"Mdn ({b_})", f"الوسيط ({b_})", "2"),
                                 col("positive_ranks", "Positive ranks", "رتب موجبة"), col("negative_ranks", "Negative ranks", "رتب سالبة"),
                                 col("ties", "Ties", "متساوية"), col("W", "W", "W", "1"), col("z", "Z", "Z", "3"), col("p", "p", "p", "p"),
                                 col("r", "r", "r", "3")], [st], "Zero differences discarded (Wilcoxon method); normal approximation with tie correction.",
                                "استُبعدت الفروق الصفرية؛ وتقريب طبيعي مع تصحيح الرتب المتساوية.")], stats=st)


# --------------------------------------------------------------------------------------------
def _posthoc(d: pd.DataFrame, which: str) -> list[dict]:
    if which == "tukey":
        ph = pg.pairwise_tukey(data=d, dv="y", between="g")
        return [{"A": r["A"], "B": r["B"], "diff": r["diff"], "se": r["se"], "stat": r["T"], "p": r["p_tukey"] if "p_tukey" in r else r["p-tukey"],
                 "effect": r["hedges"]} for _, r in ph.iterrows()]
    if which == "games_howell":
        ph = pg.pairwise_gameshowell(data=d, dv="y", between="g")
        return [{"A": r["A"], "B": r["B"], "diff": r["diff"], "se": r["se"], "stat": r["T"], "p": r["pval"] if "pval" in r else r["p_val"] if "p_val" in r else r["p-val"],
                 "effect": r["hedges"]} for _, r in ph.iterrows()]
    ph = pg.pairwise_tests(data=d, dv="y", between="g", padjust="bonf", effsize="hedges", parametric=True)
    pcol = next(c for c in ph.columns if c.lower().replace("-", "_") in ("p_corr",))
    tcol = "T"
    return [{"A": r["A"], "B": r["B"], "diff": None, "se": None, "stat": r[tcol], "p": r[pcol], "effect": r["hedges"]} for _, r in ph.iterrows()]


PH_COLS = [col("A", "Group A", "المجموعة أ"), col("B", "Group B", "المجموعة ب"), col("diff", "Mean diff. (A−B)", "فرق المتوسطين", "3"),
           col("se", "SE", "الخطأ المعياري", "3"), col("stat", "t", "ت", "3"), col("p", "p (adjusted)", "p (معدلة)", "p"),
           col("effect", "Hedges' g", "g هيدجز", "3")]


def run_anova(df, params, ctx):
    dv, group = params["dv"], params["group"]
    d, levels = _groups(df, dv, group)
    if len(levels) < 2:
        raise AnalysisError("At least 2 groups are required.", "يلزم وجود مجموعتين على الأقل.")
    if min(d["g"].value_counts()) < 2:
        raise AnalysisError("Every group needs at least 2 observations.", "يجب أن تحتوي كل مجموعة على ملاحظتين على الأقل.")
    norm_a, norm_ok = _normality_assumptions(d, levels)
    lev_a, equal_var, W, lp = _levene(d, levels)
    aov = pg.anova(data=d, dv="y", between="g", detailed=True)
    welch = pg.welch_anova(data=d, dv="y", between="g").iloc[0]
    ss_b, ss_w = aov.loc[0, "SS"], aov.loc[1, "SS"]
    df_b, df_w = aov.loc[0, "DF"], aov.loc[1, "DF"]
    ms_w = ss_w / df_w
    F = aov.loc[0, "F"]
    p = aov.loc[0, "p_unc"] if "p_unc" in aov.columns else aov.loc[0, "p-unc"]
    eta2 = ss_b / (ss_b + ss_w)
    omega2 = (ss_b - df_b * ms_w) / (ss_b + ss_w + ms_w)
    wp = welch["p_unc"] if "p_unc" in welch else welch["p-unc"]
    anova_rows = [{"source_en": "Between groups", "source_ar": "بين المجموعات", "ss": ss_b, "df": df_b, "ms": ss_b / df_b, "F": F, "p": p},
                  {"source_en": "Within groups", "source_ar": "داخل المجموعات", "ss": ss_w, "df": df_w, "ms": ms_w, "F": None, "p": None},
                  {"source_en": "Total", "source_ar": "الكلي", "ss": ss_b + ss_w, "df": df_b + df_w, "ms": None, "F": None, "p": None}]
    use_welch = not equal_var
    main_p = wp if use_welch else p
    posthoc_method = params.get("posthoc") or ("games_howell" if use_welch else "tukey")
    ph = _posthoc(d, posthoc_method) if len(levels) > 2 and main_p < float(params.get("alpha", 0.05)) else []
    mag = cohen_label(eta2, "eta2")
    st = {"dv": dv, "group": group, "levels": levels, "F": F, "df1": df_b, "df2": df_w, "p": p, "welch_F": welch["F"],
          "welch_df1": welch["ddof1"], "welch_df2": welch["ddof2"], "welch_p": wp, "eta2": eta2, "omega2": omega2,
          "test_used": "Welch" if use_welch else "Fisher", "main_p": main_p, "posthoc_method": posthoc_method if ph else None,
          "posthoc": ph, "groups": _group_desc(d, levels), "effect_label_en": mag[0], "effect_label_ar": mag[1], "normal": norm_ok}
    tables = [table("groups", "Descriptives", "الإحصاءات الوصفية", GDESC_COLS, st["groups"]),
              table("anova", "One-way ANOVA", "تحليل التباين الأحادي",
                    [col("source_en", "Source", "المصدر"), col("ss", "SS", "مجموع المربعات", "3"), col("df", "df", "د.ح", "0"),
                     col("ms", "MS", "متوسط المربعات", "3"), col("F", "F", "ف", "3"), col("p", "p", "p", "p")], anova_rows,
                    f"η² = {eta2:.3f}, ω² = {omega2:.3f}. Welch's F({welch['ddof1']:.0f}, {welch['ddof2']:.2f}) = {welch['F']:.3f}, p {fp(wp)}.",
                    f"η² = {eta2:.3f}، ω² = {omega2:.3f}. ف ويلش({welch['ddof1']:.0f}، {welch['ddof2']:.2f}) = {welch['F']:.3f}، p {fp(wp)}.")]
    if ph:
        names = {"tukey": ("Tukey HSD", "توكي HSD"), "games_howell": ("Games–Howell", "جيمس–هاول"), "bonferroni": ("Bonferroni", "بونفيروني")}[posthoc_method]
        tables.append(table("posthoc", f"Post-hoc comparisons ({names[0]})", f"المقارنات البعدية ({names[1]})", PH_COLS, ph,
                            "Games–Howell is used when variances are unequal; Tukey HSD otherwise.", "يُستخدم جيمس–هاول عند عدم تجانس التباين، وتوكي في غير ذلك."))
    return result("anova", "One-way ANOVA", "تحليل التباين الأحادي", params=params, n=len(d), tables=tables,
                  charts=[charts.box_by_group("box", d.rename(columns={"y": dv, "g": group}), dv, group),
                          charts.bar("means", [g["group"] for g in st["groups"]], [g["mean"] for g in st["groups"]], f"Means of {dv}", f"متوسطات {dv}",
                                     error=[(g["ci_high"] - g["mean"]) if g["ci_high"] is not None else None for g in st["groups"]])],
                  assumptions=norm_a + [lev_a], stats=st,
                  warnings=[warn("Variances are unequal: Welch's ANOVA and Games–Howell are reported as primary.",
                                 "التباينات غير متجانسة: يُعتمد تحليل ويلش واختبار جيمس–هاول.")] if use_welch else [])


def _dunn(d: pd.DataFrame, levels) -> list[dict]:
    d = d.copy()
    d["r"] = stats.rankdata(d["y"])
    N = len(d)
    _, t = np.unique(d["r"], return_counts=True)
    tie = (t ** 3 - t).sum() / (12 * (N - 1))
    rows, ps = [], []
    for a, b in itertools.combinations(levels, 2):
        ra, rb = d.loc[d["g"] == a, "r"], d.loc[d["g"] == b, "r"]
        se = math.sqrt((N * (N + 1) / 12 - tie) * (1 / len(ra) + 1 / len(rb)))
        z = (ra.mean() - rb.mean()) / se
        pv = 2 * stats.norm.sf(abs(z))
        ps.append(pv)
        rows.append({"A": a, "B": b, "diff": ra.mean() - rb.mean(), "se": se, "stat": z, "p_unadj": pv, "effect": abs(z) / math.sqrt(len(ra) + len(rb))})
    adj = multipletests(ps, method="bonferroni")[1]
    for r, pa in zip(rows, adj):
        r["p"] = pa
    return rows


def run_kruskal(df, params, ctx):
    dv, group = params["dv"], params["group"]
    d, levels = _groups(df, dv, group)
    if len(levels) < 2:
        raise AnalysisError("At least 2 groups are required.", "يلزم وجود مجموعتين على الأقل.")
    H, p = stats.kruskal(*[d.loc[d["g"] == g, "y"] for g in levels])
    n, k = len(d), len(levels)
    eps2 = H / ((n ** 2 - 1) / (n + 1))
    eta2h = (H - k + 1) / (n - k)
    ranks = stats.rankdata(d["y"])
    rows = [{"group": g, "n": int((d["g"] == g).sum()), "median": d.loc[d["g"] == g, "y"].median(), "mean_rank": ranks[(d["g"] == g).to_numpy()].mean()} for g in levels]
    ph = _dunn(d, levels) if k > 2 and p < float(params.get("alpha", 0.05)) else []
    mag = cohen_label(eta2h, "eta2")
    st = {"dv": dv, "group": group, "H": H, "df": k - 1, "p": p, "epsilon2": eps2, "eta2_H": eta2h, "groups": rows, "posthoc": ph,
          "effect_label_en": mag[0], "effect_label_ar": mag[1]}
    tables = [table("ranks", "Ranks", "الرتب", [col("group", "Group", "المجموعة"), col("n", "N", "العدد"), col("median", "Mdn", "الوسيط", "2"),
                                              col("mean_rank", "Mean rank", "متوسط الرتب", "2")], rows),
              table("kw", "Kruskal–Wallis test", "اختبار كروسكال–واليس", [col("H", "H", "H", "3"), col("df", "df", "د.ح", "0"), col("p", "p", "p", "p"),
                                                                       col("epsilon2", "ε²", "ε²", "3"), col("eta2_H", "η²H", "η²H", "3")], [st])]
    if ph:
        tables.append(table("dunn", "Dunn's pairwise comparisons (Bonferroni)", "مقارنات دن الثنائية (بونفيروني)",
                            [col("A", "A", "أ"), col("B", "B", "ب"), col("diff", "Mean-rank diff.", "فرق متوسط الرتب", "2"), col("stat", "z", "z", "3"),
                             col("p_unadj", "p (unadj.)", "p غير معدلة", "p"), col("p", "p (Bonferroni)", "p (بونفيروني)", "p"), col("effect", "r", "r", "3")], ph))
    return result("kruskal", "Kruskal–Wallis H test", "اختبار كروسكال–واليس", params=params, n=n, tables=tables,
                  charts=[charts.box_by_group("box", d.rename(columns={"y": dv, "g": group}), dv, group)], stats=st)


def run_anova_twoway(df, params, ctx):
    dv, a, b = params["dv"], params["factor_a"], params["factor_b"]
    require_columns(df, [dv, a, b])
    d = pd.DataFrame({"y": pd.to_numeric(df[dv], errors="coerce"), "A": df[a].astype(str), "B": df[b].astype(str)})
    d = d[df[a].notna() & df[b].notna()].dropna()
    cells = d.groupby(["A", "B"]).size()
    if (cells < 2).any():
        raise AnalysisError("Some factor-combination cells have fewer than 2 observations.", "بعض خلايا تقاطع العاملين تحتوي أقل من ملاحظتين.")
    model = smf.ols("y ~ C(A, Sum) * C(B, Sum)", data=d).fit()
    tab = sm.stats.anova_lm(model, typ=3)
    ss_err = tab.loc["Residual", "sum_sq"]
    rows = []
    labels = {"C(A, Sum)": a, "C(B, Sum)": b, "C(A, Sum):C(B, Sum)": f"{a} × {b}", "Residual": "Error"}
    for idx, r in tab.iterrows():
        if idx == "Intercept":
            continue
        pe = r["sum_sq"] / (r["sum_sq"] + ss_err) if idx != "Residual" else None
        rows.append({"source_en": labels.get(idx, idx), "source_ar": labels.get(idx, idx).replace("Error", "الخطأ"), "ss": r["sum_sq"], "df": r["df"],
                     "ms": r["sum_sq"] / r["df"], "F": r.get("F"), "p": r.get("PR(>F)"), "partial_eta2": pe})
    lev = stats.levene(*[g["y"] for _, g in d.groupby(["A", "B"])], center="mean")
    means = d.groupby(["A", "B"])["y"].agg(["count", "mean", "std"]).reset_index().rename(columns={"A": a, "B": b, "count": "n", "std": "sd"})
    fig = {"id": "interaction", "title_en": "Interaction plot", "title_ar": "مخطط التفاعل",
           "figure": {"data": [{"type": "scatter", "mode": "lines+markers", "name": str(bl), "x": list(sub[a]), "y": list(sub["mean"])}
                               for bl, sub in means.groupby(b)], "layout": {"xaxis": {"title": {"text": a}}, "yaxis": {"title": {"text": dv}}}}}
    return result("anova_twoway", "Two-way ANOVA", "تحليل التباين الثنائي", params=params, n=len(d),
                  tables=[table("cells", "Cell means", "متوسطات الخلايا", [col(a, a, a), col(b, b, b), col("n", "N", "العدد"), col("mean", "M", "المتوسط", "2"), col("sd", "SD", "الانحراف", "2")],
                                means.to_dict(orient="records")),
                          table("anova2", "Tests of between-subjects effects (Type III SS)", "اختبارات التأثيرات بين المجموعات (مجموع المربعات من النوع الثالث)",
                                [col("source_en", "Source", "المصدر"), col("ss", "SS", "مجموع المربعات", "3"), col("df", "df", "د.ح", "0"), col("ms", "MS", "متوسط المربعات", "3"),
                                 col("F", "F", "ف", "3"), col("p", "p", "p", "p"), col("partial_eta2", "Partial η²", "η² الجزئي", "3")], rows)],
                  charts=[to_jsonable(fig)],
                  assumptions=[assumption("Homogeneity of variances", "تجانس التباين", "Levene", lev.pvalue >= 0.05, f"F = {lev.statistic:.3f}, p {fp(lev.pvalue)}",
                                          f"F = {lev.statistic:.3f}، p {fp(lev.pvalue)}", lev.statistic, lev.pvalue),
                               assumption("Normality of residuals", "اعتدالية البواقي", "Shapiro–Wilk", stats.shapiro(model.resid).pvalue >= 0.05 if len(d) <= 5000 else None,
                                          f"W = {stats.shapiro(model.resid).statistic:.3f}", f"W = {stats.shapiro(model.resid).statistic:.3f}")],
                  stats={"effects": rows, "dv": dv, "factor_a": a, "factor_b": b})


def run_rm_anova(df, params, ctx):
    vars_ = params["variables"]
    if len(vars_) < 2:
        raise AnalysisError("Select at least 2 repeated measures.", "اختر قياسين متكررين على الأقل.")
    d = df[vars_].apply(pd.to_numeric, errors="coerce").dropna()
    require_n(len(d), 3)
    long = d.reset_index().melt(id_vars="index", var_name="condition", value_name="y")
    aov = pg.rm_anova(data=long, dv="y", within="condition", subject="index", correction=True, detailed=True)
    r0 = aov.iloc[0]
    pcol = "p_unc" if "p_unc" in aov.columns else "p-unc"
    spher = pg.sphericity(data=long, dv="y", within="condition", subject="index")
    sph_ok = bool(spher[0]) if len(vars_) > 2 else True
    gg_p = r0.get("p_GG_corr", r0.get("p-GG-corr"))
    eps = r0.get("eps")
    use_p = r0[pcol] if sph_ok or gg_p is None or (isinstance(gg_p, float) and math.isnan(gg_p)) else gg_p
    ph = pg.pairwise_tests(data=long, dv="y", within="condition", subject="index", padjust="bonf")
    pc = next(c for c in ph.columns if c.lower().replace("-", "_") == "p_corr")
    ph_rows = [{"A": r["A"], "B": r["B"], "stat": r["T"], "p": r[pc], "effect": r.get("hedges")} for _, r in ph.iterrows()]
    st = {"F": r0["F"], "df1": r0["DF"], "df2": aov.iloc[1]["DF"], "p": r0[pcol], "p_gg": gg_p, "epsilon_gg": eps, "p_used": use_p,
          "np2": r0.get("np2", r0.get("ng2")), "ng2": r0.get("ng2"), "sphericity_W": spher[1] if len(vars_) > 2 else None,
          "sphericity_p": spher[4] if len(vars_) > 2 else None, "posthoc": ph_rows, "variables": vars_}
    means = [{"condition": v, "n": len(d), "mean": d[v].mean(), "sd": d[v].std()} for v in vars_]
    return result("rm_anova", "Repeated-measures ANOVA", "تحليل التباين للقياسات المتكررة", params=params, n=len(d),
                  tables=[table("means", "Descriptives", "الإحصاءات الوصفية", [col("condition", "Measure", "القياس"), col("n", "N", "العدد"), col("mean", "M", "المتوسط", "2"), col("sd", "SD", "الانحراف", "2")], means),
                          table("rm", "Within-subjects effects", "التأثيرات داخل الأفراد",
                                [col("F", "F", "ف", "3"), col("df1", "df1", "د.ح1", "0"), col("df2", "df2", "د.ح2", "0"), col("p", "p", "p", "p"),
                                 col("epsilon_gg", "ε (G–G)", "إبسلون (G–G)", "3"), col("p_gg", "p (G–G)", "p (G–G)", "p"), col("ng2", "η²G", "η²G", "3")], [st],
                                "Greenhouse–Geisser correction applied when sphericity is violated.", "يُطبق تصحيح جرينهاوس–جيسر عند انتهاك الكروية."),
                          table("posthoc", "Pairwise comparisons (Bonferroni)", "المقارنات الثنائية (بونفيروني)", [col("A", "A", "أ"), col("B", "B", "ب"), col("stat", "t", "ت", "3"), col("p", "p", "p", "p"), col("effect", "g", "g", "3")], ph_rows)],
                  charts=[charts.bar("means", vars_, [m["mean"] for m in means], "Means by measure", "المتوسطات حسب القياس")],
                  assumptions=[assumption("Sphericity", "الكروية", "Mauchly", sph_ok, f"W = {spher[1]:.3f}, p {fp(spher[4])}" if len(vars_) > 2 else "2 levels: not applicable",
                                          f"W = {spher[1]:.3f}، p {fp(spher[4])}" if len(vars_) > 2 else "مستويان: لا ينطبق")], stats=st)


def run_friedman(df, params, ctx):
    vars_ = params["variables"]
    d = df[vars_].apply(pd.to_numeric, errors="coerce").dropna()
    if len(vars_) < 3:
        raise AnalysisError("Friedman's test needs ≥ 3 related measures (use Wilcoxon for 2).", "يتطلب اختبار فريدمان 3 قياسات مترابطة فأكثر (استخدم ويلكوكسون لقياسين).")
    chi, p = stats.friedmanchisquare(*[d[v] for v in vars_])
    n, k = len(d), len(vars_)
    W = chi / (n * (k - 1))
    ranks = d.rank(axis=1).mean()
    rows = [{"condition": v, "median": d[v].median(), "mean_rank": ranks[v]} for v in vars_]
    st = {"chi2": chi, "df": k - 1, "p": p, "kendall_w": W, "n": n}
    mag = cohen_label(W, "w")
    st.update({"effect_label_en": mag[0], "effect_label_ar": mag[1]})
    return result("friedman", "Friedman test", "اختبار فريدمان", params=params, n=n,
                  tables=[table("ranks", "Mean ranks", "متوسطات الرتب", [col("condition", "Measure", "القياس"), col("median", "Mdn", "الوسيط", "2"), col("mean_rank", "Mean rank", "متوسط الرتب", "2")], rows),
                          table("fr", "Test statistics", "إحصاءات الاختبار", [col("n", "N", "العدد"), col("chi2", "χ²", "χ²", "3"), col("df", "df", "د.ح", "0"), col("p", "p", "p", "p"), col("kendall_w", "Kendall's W", "W كندال", "3")], [st])],
                  stats=st)


def run_onesample(df, params, ctx):
    v, mu = params["variable"], float(params.get("test_value", ctx["dictionary"]["likert"].get("min", 1) + (ctx["dictionary"]["likert"].get("max", 5) - ctx["dictionary"]["likert"].get("min", 1)) / 2))
    x = pd.to_numeric(df[v], errors="coerce").dropna()
    require_n(len(x), 3)
    r = pg.ttest(x, mu, alternative=_alt(params.get("alternative"))).iloc[0]
    q = stats.t.ppf(0.975, len(x) - 1)
    se_m = x.std(ddof=1) / math.sqrt(len(x))
    ci = (x.mean() - q * se_m, x.mean() + q * se_m)
    d = (x.mean() - mu) / x.std(ddof=1)
    mag = cohen_label(d, "d")
    st = {"variable": v, "test_value": mu, "n": len(x), "mean": x.mean(), "sd": x.std(ddof=1), "t": r["T"], "df": r["dof"],
          "p": r["p_val"] if "p_val" in r else r["p-val"], "mean_diff": x.mean() - mu, "ci_low": ci[0] - mu if params.get("ci_of_diff") else ci[0],
          "ci_high": ci[1] - mu if params.get("ci_of_diff") else ci[1], "cohens_d": d, "effect_label_en": mag[0], "effect_label_ar": mag[1]}
    return result("ttest_one", "One-sample t-test", "اختبار (ت) لعينة واحدة", params={**params, "test_value": mu}, n=len(x),
                  tables=[table("one", "One-sample test", "اختبار العينة الواحدة",
                                [col("n", "N", "العدد"), col("mean", "M", "المتوسط", "2"), col("sd", "SD", "الانحراف", "2"), col("test_value", "Test value", "القيمة المختبرة", "2"),
                                 col("t", "t", "ت", "3"), col("df", "df", "د.ح", "0"), col("p", "p", "p", "p"), col("ci_low", "95% CI of M (low)", "الحد الأدنى", "3"),
                                 col("ci_high", "95% CI of M (high)", "الحد الأعلى", "3"), col("cohens_d", "Cohen's d", "d كوهين", "3")], [st])], stats=st)
