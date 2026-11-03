"""Reliability and construct validity: alpha, omega, item-total statistics, CR, AVE,
Fornell–Larcker, HTMT, KMO and Bartlett."""
from __future__ import annotations

import math
import warnings as _w

import numpy as np
import pandas as pd
from factor_analyzer import FactorAnalyzer
from factor_analyzer.factor_analyzer import calculate_bartlett_sphericity, calculate_kmo

from . import charts
from .utils import AnalysisError, assumption, col, result, table, to_jsonable, warn


def cronbach_alpha(block: pd.DataFrame) -> float:
    k = block.shape[1]
    if k < 2:
        return float("nan")
    item_var = block.var(axis=0, ddof=1).sum()
    total_var = block.sum(axis=1).var(ddof=1)
    return float(k / (k - 1) * (1 - item_var / total_var)) if total_var > 0 else float("nan")


def standardized_alpha(block: pd.DataFrame) -> float:
    k = block.shape[1]
    r = block.corr().to_numpy()
    rbar = (r.sum() - k) / (k * (k - 1))
    return float(k * rbar / (1 + (k - 1) * rbar))


def alpha_ci(alpha: float, n: int, k: int, conf: float = 0.95) -> tuple[float, float]:
    """Feldt (1965) F-based confidence interval (as in pingouin / SPSS ICC-consistency)."""
    from scipy import stats
    df1, df2 = n - 1, (n - 1) * (k - 1)
    lo = 1 - (1 - alpha) * stats.f.ppf(0.5 + conf / 2, df1, df2)
    hi = 1 - (1 - alpha) * stats.f.ppf(0.5 - conf / 2, df1, df2)
    return lo, hi


def one_factor_loadings(block: pd.DataFrame) -> np.ndarray | None:
    if block.shape[1] < 3:
        return None
    with _w.catch_warnings():
        _w.simplefilter("ignore")
        try:
            fa = FactorAnalyzer(n_factors=1, rotation=None, method="ml")
            fa.fit(block.to_numpy())
            lam = fa.loadings_[:, 0]
        except Exception:  # noqa: BLE001
            return None
    if lam.sum() < 0:
        lam = -lam
    return lam


def omega_total(lam: np.ndarray | None) -> float:
    if lam is None:
        return float("nan")
    s = lam.sum() ** 2
    return float(s / (s + (1 - lam ** 2).sum()))


def split_half(block: pd.DataFrame) -> dict:
    odd, even = block.iloc[:, ::2].sum(axis=1), block.iloc[:, 1::2].sum(axis=1)
    r = np.corrcoef(odd, even)[0, 1]
    total_var = (odd + even).var(ddof=1)
    guttman = 2 * (1 - (odd.var(ddof=1) + even.var(ddof=1)) / total_var)
    return {"r_halves": r, "spearman_brown": 2 * r / (1 + r), "guttman": guttman}


def alpha_label(a: float) -> tuple[str, str]:
    """George & Mallery (2003) descriptive benchmarks — indicative only."""
    if a is None or math.isnan(a):
        return "undetermined", "غير محدد"
    for thr, en, ar in [(0.9, "excellent", "ممتاز"), (0.8, "good", "جيد"), (0.7, "acceptable", "مقبول"),
                        (0.6, "questionable", "مشكوك فيه"), (0.5, "poor", "ضعيف")]:
        if a >= thr:
            return en, ar
    return "unacceptable", "غير مقبول"


def scale_reliability(block: pd.DataFrame, name: str) -> tuple[dict, list[dict]]:
    block = block.apply(pd.to_numeric, errors="coerce").dropna()
    n, k = block.shape
    if k < 2 or n < 3:
        raise AnalysisError(f"Dimension {name}: at least 2 items and 3 complete cases are required.",
                            f"البعد {name}: يلزم بندان على الأقل و3 حالات مكتملة.")
    a = cronbach_alpha(block)
    lo, hi = alpha_ci(a, n, k)
    lam = one_factor_loadings(block)
    om = omega_total(lam)
    total = block.sum(axis=1)
    items = []
    r = block.corr().to_numpy()
    mean_inter = (r.sum() - k) / (k * (k - 1))
    for i, c in enumerate(block.columns):
        rest = total - block[c]
        citc = np.corrcoef(block[c], rest)[0, 1] if block[c].std() > 0 else float("nan")
        aid = cronbach_alpha(block.drop(columns=c)) if k > 2 else float("nan")
        items.append({"dimension": name, "item": c, "mean": block[c].mean(), "sd": block[c].std(ddof=1),
                      "scale_mean_if_deleted": rest.mean(), "scale_var_if_deleted": rest.var(ddof=1),
                      "citc": citc, "alpha_if_deleted": aid, "delta_alpha": aid - a if k > 2 else None,
                      "loading": lam[i] if lam is not None else None,
                      "flag_en": "low item-total correlation (< .30)" if citc < 0.30 else ("alpha increases if deleted" if k > 2 and aid > a + 0.005 else ""),
                      "flag_ar": "ارتباط منخفض بالدرجة الكلية (< .30)" if citc < 0.30 else ("يرتفع ألفا عند الحذف" if k > 2 and aid > a + 0.005 else "")})
    lab = alpha_label(a)
    summary = {"dimension": name, "items": k, "n": n, "alpha": a, "alpha_ci_low": lo, "alpha_ci_high": hi,
               "alpha_std": standardized_alpha(block), "omega": om, "mean_inter_item_r": mean_inter,
               **{f"split_{kk}": vv for kk, vv in split_half(block).items()},
               "label_en": lab[0], "label_ar": lab[1]}
    return to_jsonable(summary), to_jsonable(items)


def htmt(items_by_dim: dict[str, list[str]], data: pd.DataFrame) -> pd.DataFrame:
    """Heterotrait–monotrait ratio (Henseler, Ringle & Sarstedt, 2015) on absolute item correlations."""
    R = data.corr().abs()
    names = list(items_by_dim)
    out = pd.DataFrame(np.nan, index=names, columns=names)

    def mono(it):
        if len(it) < 2:
            return np.nan
        sub = R.loc[it, it].to_numpy()
        return sub[np.triu_indices(len(it), 1)].mean()

    for i, a in enumerate(names):
        for b in names[:i]:
            hetero = R.loc[items_by_dim[a], items_by_dim[b]].to_numpy().mean()
            out.loc[a, b] = hetero / math.sqrt(mono(items_by_dim[a]) * mono(items_by_dim[b]))
    return out


def run_reliability(df: pd.DataFrame, params: dict, ctx: dict) -> dict:
    d = ctx["dictionary"]
    dims = [dm for dm in d.get("dimensions", []) if not params.get("dimensions") or dm["name"] in params["dimensions"]]
    if params.get("items"):
        dims = [{"name": params.get("scale_name", "Scale"), "items": params["items"]}]
    if not dims:
        raise AnalysisError("Define the questionnaire dimensions (or select items) first.", "حدد أبعاد الاستبانة (أو اختر البنود) أولاً.")
    summaries, items, warns = [], [], []
    for dm in dims:
        cols = [c for c in dm["items"] if c in df.columns]
        try:
            s, it = scale_reliability(df[cols], dm["name"])
        except AnalysisError as e:
            warns.append(warn(e.en, e.ar))
            continue
        summaries.append(s)
        items.extend(it)
        if any(i["citc"] is not None and i["citc"] < 0 for i in it):
            warns.append(warn(f"{dm['name']}: negative item-total correlation — check for reverse-keyed items that were not recoded.",
                              f"{dm['name']}: ارتباط سالب بين بند والدرجة الكلية — تحقق من وجود بنود عكسية لم يُعَد ترميزها."))
    if len(dims) > 1 and not params.get("items"):
        all_items = [c for dm in dims for c in dm["items"] if c in df.columns]
        block = df[all_items].apply(pd.to_numeric, errors="coerce").dropna()
        if len(block) > 3 and len(all_items) >= 2:
            s, _ = scale_reliability(block, "Total scale / الأداة ككل")
            summaries.append(s)
    if not summaries:
        raise AnalysisError("No dimension had enough items/data for reliability analysis.", "لا يوجد بعد يحتوي بنوداً أو بيانات كافية لتحليل الثبات.")
    tables = [
        table("reliability", "Internal consistency", "الاتساق الداخلي",
              [col("dimension", "Dimension", "البعد"), col("items", "k", "عدد البنود"), col("n", "N", "العدد"),
               col("alpha", "Cronbach's α", "ألفا كرونباخ", "3"), col("alpha_ci_low", "95% CI low", "الحد الأدنى 95%", "3"),
               col("alpha_ci_high", "95% CI high", "الحد الأعلى 95%", "3"), col("alpha_std", "Standardized α", "ألفا المعيارية", "3"),
               col("omega", "McDonald's ω", "أوميغا ماكدونالد", "3"), col("mean_inter_item_r", "Mean inter-item r", "متوسط الارتباط البيني", "3"),
               col("split_spearman_brown", "Split-half (S–B)", "التجزئة النصفية (سبيرمان–براون)", "3"),
               col("split_guttman", "Guttman split-half", "التجزئة النصفية (جتمان)", "3"), col("label_en", "Benchmark", "التقدير")],
              summaries, "α CI by Feldt's method; ω total from a one-factor ML solution. Benchmarks (George & Mallery) are indicative only; α does not establish unidimensionality.",
              "فترة الثقة لألفا بطريقة فيلدت؛ وأوميغا الكلية من نموذج عامل واحد بطريقة الاحتمال الأقصى. التقديرات (George & Mallery) استرشادية فقط؛ ولا يدل ألفا على أحادية البعد."),
        table("item_total", "Item-total statistics", "إحصاءات البند–الدرجة الكلية",
              [col("dimension", "Dimension", "البعد"), col("item", "Item", "البند"), col("mean", "M", "المتوسط", "2"), col("sd", "SD", "الانحراف", "2"),
               col("scale_mean_if_deleted", "Scale M if deleted", "متوسط المقياس عند الحذف", "2"),
               col("scale_var_if_deleted", "Scale variance if deleted", "تباين المقياس عند الحذف", "2"),
               col("citc", "Corrected item-total r", "الارتباط المصحح", "3"), col("alpha_if_deleted", "α if deleted", "ألفا عند الحذف", "3"),
               col("delta_alpha", "Δα", "التغير في ألفا", "3"), col("loading", "λ (1-factor)", "التشبع (عامل واحد)", "3"),
               col("flag_en", "Flag", "ملاحظة")], items),
    ]
    ch = [charts.bar("alpha_bar", [s["dimension"] for s in summaries], [s["alpha"] for s in summaries], "Cronbach's α by dimension",
                     "ألفا كرونباخ لكل بعد", yrange=[0, 1])]
    return result("reliability", "Reliability analysis", "تحليل الثبات", params=params, n=len(df), tables=tables, charts=ch,
                  stats={"scales": summaries, "items": items}, warnings=warns, nature="psychometric")


def run_validity(df: pd.DataFrame, params: dict, ctx: dict) -> dict:
    """Convergent & discriminant validity from a CFA measurement model of the confirmed dimensions
    (falls back to separate one-factor solutions when the CFA cannot be estimated)."""
    from .factor import fit_cfa, measurement_syntax
    d = ctx["dictionary"]
    dims = [dm for dm in d.get("dimensions", []) if len([i for i in dm["items"] if i in df.columns]) >= 2]
    if not dims:
        raise AnalysisError("Validity analysis needs confirmed dimensions with ≥ 2 items each.", "يتطلب تحليل الصدق أبعاداً مؤكدة يحتوي كل منها بندين على الأقل.")
    items_by_dim = {dm["name"]: [i for i in dm["items"] if i in df.columns] for dm in dims}
    all_items = [i for v in items_by_dim.values() for i in v]
    data = df[all_items].apply(pd.to_numeric, errors="coerce").dropna()
    if len(data) < max(30, len(all_items) + 5):
        raise AnalysisError(f"Too few complete cases ({len(data)}) for validity analysis.", f"عدد الحالات المكتملة ({len(data)}) قليل جداً لتحليل الصدق.")
    warns, source = [], "CFA"
    loadings: dict[str, dict[str, float]] = {}
    latent_corr = None
    cfa = None
    if len(dims) >= 1 and all(len(v) >= 2 for v in items_by_dim.values()):
        try:
            cfa = fit_cfa(data, measurement_syntax(items_by_dim))
            for row in cfa["loadings"]:
                loadings.setdefault(row["factor"], {})[row["item"]] = row["std_loading"]
            latent_corr = cfa.get("factor_corr")
        except AnalysisError as e:
            warns.append(warn(f"CFA could not be estimated ({e.en}); loadings come from separate one-factor solutions.",
                              f"تعذر تقدير التحليل العاملي التوكيدي ({e.ar})؛ التشبعات مأخوذة من حلول أحادية العامل منفصلة."))
    if not loadings:
        source = "one-factor EFA per dimension"
        for name, its in items_by_dim.items():
            lam = one_factor_loadings(data[its])
            if lam is not None:
                loadings[name] = dict(zip(its, lam))
    rows = []
    ave = {}
    for name, its in items_by_dim.items():
        lam = np.array([loadings.get(name, {}).get(i, np.nan) for i in its], dtype=float)
        if np.isnan(lam).all():
            continue
        lam = lam[~np.isnan(lam)]
        theta = 1 - lam ** 2
        cr = lam.sum() ** 2 / (lam.sum() ** 2 + theta.sum())
        a = (lam ** 2).mean()
        ave[name] = a
        rows.append({"dimension": name, "items": len(its), "min_loading": lam.min(), "max_loading": lam.max(), "cr": cr, "ave": a,
                     "sqrt_ave": math.sqrt(a), "alpha": cronbach_alpha(data[its]), "convergent": bool(cr >= 0.7 and a >= 0.5),
                     "convergent_en": "supported" if cr >= 0.7 and a >= 0.5 else ("partially (CR ≥ .70, AVE < .50)" if cr >= 0.7 else "not supported"),
                     "convergent_ar": "متحقق" if cr >= 0.7 and a >= 0.5 else ("جزئياً (CR ≥ .70، AVE < .50)" if cr >= 0.7 else "غير متحقق")})
    # construct correlations: latent (CFA) or composite (fallback)
    if latent_corr is not None:
        corr = pd.DataFrame(latent_corr["matrix"], index=latent_corr["names"], columns=latent_corr["names"])
        corr_source = "latent (CFA)"
    else:
        corr = pd.DataFrame({k: data[v].mean(axis=1) for k, v in items_by_dim.items()}).corr()
        corr_source = "composite scores"
    fl = corr.copy()
    for n_ in fl.index:
        if n_ in ave:
            fl.loc[n_, n_] = math.sqrt(ave[n_])
    fl_rows, ht_rows = [], []
    for n_ in fl.index:
        r = {"dimension": n_}
        for m in fl.columns:
            r[m] = fl.loc[n_, m]
        fl_rows.append(r)
    fl_ok = all(math.sqrt(ave.get(a, 0)) > abs(corr.loc[a, b]) and math.sqrt(ave.get(b, 0)) > abs(corr.loc[a, b])
                for i, a in enumerate(corr.index) for b in corr.index[:i])
    tables = [table("convergent", "Convergent validity", "الصدق التقاربي",
                    [col("dimension", "Dimension", "البعد"), col("items", "k", "البنود"), col("min_loading", "Min λ", "أدنى تشبع", "3"),
                     col("max_loading", "Max λ", "أعلى تشبع", "3"), col("cr", "CR", "الثبات المركب", "3"), col("ave", "AVE", "متوسط التباين المستخلص", "3"),
                     col("sqrt_ave", "√AVE", "جذر AVE", "3"), col("alpha", "α", "ألفا", "3"), col("convergent_en", "Convergent validity", "الصدق التقاربي")],
                    rows, f"Standardized loadings from {source}. Criteria: CR ≥ .70 and AVE ≥ .50 (Fornell & Larcker, 1981; Hair et al.).",
                    f"التشبعات المعيارية من {source}. المعايير: CR ≥ .70 و AVE ≥ .50 (Fornell & Larcker, 1981؛ Hair وآخرون).")]
    fl_cols = [col("dimension", "", "")] + [col(m, m, m, "3") for m in fl.columns]
    tables.append(table("fornell_larcker", "Fornell–Larcker criterion", "معيار فورنل–لاركر", fl_cols, fl_rows,
                        f"Diagonal = √AVE; off-diagonal = {corr_source} correlations. Discriminant validity requires √AVE > correlations.",
                        "القطر = جذر AVE؛ وخارج القطر = الارتباطات بين البنى. يتحقق الصدق التمييزي عندما يكون جذر AVE أكبر من الارتباطات."))
    htmt_ok = None
    if len(items_by_dim) >= 2:
        H = htmt(items_by_dim, data)
        for n_ in H.index:
            r = {"dimension": n_}
            for m in H.columns:
                r[m] = H.loc[n_, m]
            ht_rows.append(r)
        vals = H.to_numpy()[~np.isnan(H.to_numpy())]
        htmt_ok = bool((vals < 0.85).all())
        tables.append(table("htmt", "HTMT ratios", "نسب HTMT", fl_cols, ht_rows,
                            "HTMT < .85 (strict) or < .90 (liberal) supports discriminant validity (Henseler et al., 2015).",
                            "قيم HTMT أقل من .85 (صارم) أو .90 (متساهل) تدعم الصدق التمييزي (Henseler وآخرون، 2015)."))
    kmo_items, kmo_all = calculate_kmo(data.to_numpy())
    chi, p = calculate_bartlett_sphericity(data.to_numpy())
    asum = [assumption("Sampling adequacy", "كفاية العينة", "KMO", kmo_all >= 0.6, f"KMO = {kmo_all:.3f}", f"KMO = {kmo_all:.3f}", kmo_all),
            assumption("Sphericity", "الكروية", "Bartlett", p < 0.05, f"χ² = {chi:.2f}, p {('< .001' if p < .001 else f'= {p:.3f}')}",
                       f"χ² = {chi:.2f}، p {('< .001' if p < .001 else f'= {p:.3f}')}", chi, p)]
    ch = []
    if len(items_by_dim) >= 2:
        ch.append(charts.heatmap("construct_corr", corr, "Construct correlations", "الارتباطات بين البنى"))
    return result("validity", "Construct validity", "الصدق البنائي", params=params, n=len(data), tables=tables, charts=ch,
                  assumptions=asum, warnings=warns + [warn("Validity is a cumulative argument: these indices support, but do not by themselves establish, construct validity.",
                                                           "الصدق حجة تراكمية: هذه المؤشرات تدعم صدق البناء لكنها لا تثبته وحدها.")],
                  stats={"convergent": rows, "fornell_larcker_ok": fl_ok, "htmt_ok": htmt_ok, "kmo": kmo_all, "bartlett_chi2": chi,
                         "bartlett_p": p, "loading_source": source, "cfa_fit": cfa["fit"] if cfa else None}, nature="psychometric")
