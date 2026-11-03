"""Advanced analyses: mediation, moderation, MANOVA, clustering, discriminant analysis,
categorical association tests and survival analysis."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pingouin as pg
import statsmodels.api as sm
from scipy import stats
from sklearn.cluster import AgglomerativeClustering, KMeans
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.metrics import confusion_matrix, silhouette_score
from sklearn.model_selection import cross_val_score
from statsmodels.multivariate.manova import MANOVA
from statsmodels.stats.contingency_tables import mcnemar

from . import charts
from .utils import AnalysisError, assumption, cohen_label, col, fp, require_columns, require_n, result, table, to_jsonable, warn


def _num(df, cols):
    require_columns(df, cols)
    return df[cols].apply(pd.to_numeric, errors="coerce").dropna()


def run_mediation(df, params, ctx):
    x, m, y = params["x"], params["mediator"], params["y"]
    covar = params.get("covariates") or []
    d = _num(df, [x, m, y] + covar)
    require_n(len(d), 30, "mediation")
    n_boot = int(params.get("n_boot", 5000))
    res = pg.mediation_analysis(data=d, x=x, m=m, y=y, covar=covar or None, n_boot=n_boot, seed=int(params.get("seed", 42)), return_dist=False)
    rows = []
    pcol = "pval" if "pval" in res.columns else ("p_val" if "p_val" in res.columns else "p-val")
    lo_c = next(c for c in res.columns if "CI" in c and ("2.5" in c or "low" in c.lower()))
    hi_c = next(c for c in res.columns if "CI" in c and ("97.5" in c or "high" in c.lower()))
    labels = {}
    for _, r in res.iterrows():
        path = r["path"]
        en = {"Total": "Total effect (c)", "Direct": "Direct effect (c')", "Indirect": "Indirect effect (a×b)"}.get(path, path)
        if path.startswith(m) and "~" in path and path.endswith(x) or path == f"{m} ~ X":
            en = "a path (X → M)"
        if path.startswith("Y ~") or path == f"Y ~ {m}":
            en = "b path (M → Y)"
        rows.append({"path": path, "label": en, "coef": r["coef"], "se": r["se"], "p": r[pcol], "ci_low": r[lo_c], "ci_high": r[hi_c], "sig": bool(r["sig"] == "Yes")})
    ind = next(r for r in rows if r["path"] == "Indirect")
    tot = next(r for r in rows if r["path"] == "Total")
    direct = next(r for r in rows if r["path"] == "Direct")
    ind_sig = not (ind["ci_low"] <= 0 <= ind["ci_high"])
    if ind_sig and not direct["sig"]:
        typ_en, typ_ar = "indirect-only (full) mediation", "وساطة كاملة (تأثير غير مباشر فقط)"
    elif ind_sig and direct["sig"]:
        typ_en, typ_ar = ("complementary (partial) mediation", "وساطة جزئية مكملة") if np.sign(ind["coef"]) == np.sign(direct["coef"]) else ("competitive mediation", "وساطة تنافسية")
    else:
        typ_en, typ_ar = "no mediation (indirect effect CI includes 0)", "لا توجد وساطة (فترة الثقة للتأثير غير المباشر تتضمن الصفر)"
    st = {"x": x, "m": m, "y": y, "paths": rows, "indirect": ind["coef"], "indirect_ci": [ind["ci_low"], ind["ci_high"]], "indirect_sig": ind_sig,
          "total": tot["coef"], "direct": direct["coef"], "prop_mediated": ind["coef"] / tot["coef"] if tot["coef"] else None,
          "type_en": typ_en, "type_ar": typ_ar, "n_boot": n_boot}
    return result("mediation", "Mediation analysis (bootstrap)", "تحليل الوساطة (بالإقلاع الإحصائي)", params=params, n=len(d),
                  tables=[table("paths", "Path estimates", "تقديرات المسارات",
                                [col("label", "Path", "المسار"), col("path", "Model", "النموذج"), col("coef", "b", "b", "3"), col("se", "SE", "الخطأ المعياري", "3"),
                                 col("p", "p", "p", "p"), col("ci_low", "95% CI low", "الحد الأدنى", "3"), col("ci_high", "95% CI high", "الحد الأعلى", "3")], rows,
                                f"Indirect effect CI: percentile bootstrap with {n_boot} resamples (seed fixed for reproducibility). Result: {typ_en}.",
                                f"فترة الثقة للتأثير غير المباشر: إقلاع مئيني بـ {n_boot} عينة (بذرة ثابتة لإعادة الإنتاج). النتيجة: {typ_ar}.")],
                  stats=st, warnings=[warn("Mediation with cross-sectional data cannot establish temporal or causal ordering.",
                                           "لا يمكن لتحليل الوساطة على بيانات مقطعية إثبات التسلسل الزمني أو السببي.")])


def run_moderation(df, params, ctx):
    x, w, y = params["x"], params["moderator"], params["y"]
    d = _num(df, [x, w, y])
    require_n(len(d), 30, "moderation")
    xc, wc = d[x] - d[x].mean(), d[w] - d[w].mean()
    X1 = pd.DataFrame({x: xc, w: wc})
    X2 = X1.assign(**{f"{x}×{w}": xc * wc})
    m1 = sm.OLS(d[y], sm.add_constant(X1)).fit()
    m2 = sm.OLS(d[y], sm.add_constant(X2)).fit()
    dr2 = m2.rsquared - m1.rsquared
    fch = dr2 / ((1 - m2.rsquared) / m2.df_resid)
    pch = stats.f.sf(fch, 1, m2.df_resid)
    ci = m2.conf_int()
    rows = [{"term": "(Intercept)" if k == "const" else k, "B": m2.params[k], "se": m2.bse[k], "t": m2.tvalues[k], "p": m2.pvalues[k],
             "ci_low": ci.loc[k, 0], "ci_high": ci.loc[k, 1]} for k in m2.params.index]
    cov = m2.cov_params()
    int_name = f"{x}×{w}"
    sd_w = d[w].std(ddof=1)
    slopes = []
    for lab_en, lab_ar, val in [("−1 SD", "−1 انحراف", -sd_w), ("Mean", "المتوسط", 0.0), ("+1 SD", "+1 انحراف", sd_w)]:
        b = m2.params[x] + m2.params[int_name] * val
        se = math.sqrt(cov.loc[x, x] + val ** 2 * cov.loc[int_name, int_name] + 2 * val * cov.loc[x, int_name])
        t = b / se
        p = 2 * stats.t.sf(abs(t), m2.df_resid)
        q = stats.t.ppf(0.975, m2.df_resid)
        slopes.append({"level_en": f"{w} at {lab_en}", "level_ar": f"{w} عند {lab_ar}", "w_value": val + d[w].mean(), "slope": b, "se": se, "t": t, "p": p,
                       "ci_low": b - q * se, "ci_high": b + q * se})
    xs = [float(xc.min()), float(xc.max())]
    fig = {"id": "simple_slopes", "title_en": "Simple slopes", "title_ar": "الميول البسيطة",
           "figure": {"data": [{"type": "scatter", "mode": "lines", "name": s["level_en"], "x": [v + d[x].mean() for v in xs],
                                "y": [m2.params["const"] + m2.params[w] * (s["w_value"] - d[w].mean()) + s["slope"] * v for v in xs]} for s in slopes],
                      "layout": {"xaxis": {"title": {"text": x}}, "yaxis": {"title": {"text": y}}}}}
    st = {"x": x, "w": w, "y": y, "interaction_b": m2.params[int_name], "interaction_p": m2.pvalues[int_name], "delta_r2": dr2, "F_change": fch,
          "p_change": pch, "r2": m2.rsquared, "slopes": slopes, "coefficients": rows}
    return result("moderation", "Moderation analysis", "تحليل التعديل (الدور المعدِّل)", params=params, n=len(d),
                  tables=[table("coef", "Regression with interaction (mean-centred)", "الانحدار مع حد التفاعل (بعد التمركز)",
                                [col("term", "Term", "الحد"), col("B", "B", "B", "3"), col("se", "SE", "الخطأ المعياري", "3"), col("t", "t", "ت", "3"), col("p", "p", "p", "p"),
                                 col("ci_low", "95% CI low", "الحد الأدنى", "3"), col("ci_high", "95% CI high", "الحد الأعلى", "3")], rows,
                                f"ΔR² due to interaction = {dr2:.3f}, F(1, {m2.df_resid:.0f}) = {fch:.3f}, p {fp(pch)}.",
                                f"ΔR² الناتج عن التفاعل = {dr2:.3f}، ف(1، {m2.df_resid:.0f}) = {fch:.3f}، p {fp(pch)}."),
                          table("slopes", "Simple slopes", "الميول البسيطة",
                                [col("level_en", "Moderator level", "مستوى المعدِّل"), col("slope", "Slope", "الميل", "3"), col("se", "SE", "الخطأ المعياري", "3"), col("t", "t", "ت", "3"),
                                 col("p", "p", "p", "p"), col("ci_low", "95% CI low", "الحد الأدنى", "3"), col("ci_high", "95% CI high", "الحد الأعلى", "3")], slopes)],
                  charts=[to_jsonable(fig)], stats=st)


def run_manova(df, params, ctx):
    dvs, group = params["dvs"], params["group"]
    if len(dvs) < 2:
        raise AnalysisError("MANOVA requires ≥ 2 dependent variables.", "يتطلب تحليل التباين المتعدد متغيرين تابعين على الأقل.")
    require_columns(df, dvs + [group])
    d = df[dvs].apply(pd.to_numeric, errors="coerce")
    d["G"] = df[group].astype(str).where(df[group].notna())
    d = d.dropna()
    safe = {v: f"y{i}" for i, v in enumerate(dvs)}
    dd = d.rename(columns=safe)
    mv = MANOVA.from_formula(" + ".join(safe.values()) + " ~ C(G)", data=dd).mv_test()
    tab = mv.results["C(G)"]["stat"]
    rows = [{"test": idx, "value": r["Value"], "F": r["F Value"], "df1": r["Num DF"], "df2": r["Den DF"], "p": r["Pr > F"]} for idx, r in tab.iterrows()]
    wilks = tab.loc["Wilks' lambda"]
    s = min(len(dvs), d["G"].nunique() - 1)
    pe2 = 1 - wilks["Value"] ** (1 / s)
    try:
        bm = pg.box_m(d, dvs=dvs, group="G")
        box = assumption("Homogeneity of covariance matrices", "تجانس مصفوفات التغاير", "Box's M", bool(bm["pval"].iloc[0] >= 0.001),
                         f"χ² = {bm['Chi2'].iloc[0]:.3f}, p {fp(bm['pval'].iloc[0])} (α = .001)", f"χ² = {bm['Chi2'].iloc[0]:.3f}، p {fp(bm['pval'].iloc[0])} (α = .001)")
        asum = [box]
    except Exception:  # noqa: BLE001
        asum = []
    uni = []
    for v in dvs:
        groups = [g[v] for _, g in d.groupby("G")]
        F, p = stats.f_oneway(*groups)
        uni.append({"dv": v, "F": F, "p": p, "p_bonf": min(1, p * len(dvs))})
    return result("manova", "One-way MANOVA", "تحليل التباين المتعدد (MANOVA)", params=params, n=len(d),
                  tables=[table("mv", "Multivariate tests", "الاختبارات متعددة المتغيرات", [col("test", "Test", "الاختبار"), col("value", "Value", "القيمة", "3"), col("F", "F", "ف", "3"),
                                                                                            col("df1", "df1", "د.ح1", "0"), col("df2", "df2", "د.ح2", "2"), col("p", "p", "p", "p")], rows,
                                f"Partial η² (from Wilks' Λ) = {pe2:.3f}.", f"η² الجزئي (من لامدا ويلكس) = {pe2:.3f}."),
                          table("uni", "Follow-up univariate ANOVAs", "تحليلات التباين الأحادية اللاحقة", [col("dv", "DV", "التابع"), col("F", "F", "ف", "3"), col("p", "p", "p", "p"),
                                                                                                         col("p_bonf", "p (Bonferroni)", "p (بونفيروني)", "p")], uni)],
                  assumptions=asum, stats={"tests": rows, "partial_eta2": pe2, "wilks": wilks["Value"], "p": wilks["Pr > F"], "univariate": uni})


def run_cluster(df, params, ctx):
    vars_ = params["variables"]
    d = _num(df, vars_)
    require_n(len(d), 10, "clustering")
    Z = (d - d.mean()) / d.std(ddof=1)
    method = params.get("method", "kmeans")
    sil = []
    ks = range(2, min(9, len(d) - 1))
    for k in ks:
        lab = KMeans(n_clusters=k, n_init=20, random_state=42).fit_predict(Z) if method == "kmeans" else AgglomerativeClustering(n_clusters=k, linkage="ward").fit_predict(Z)
        sil.append({"k": k, "silhouette": silhouette_score(Z, lab)})
    k = int(params.get("k") or max(sil, key=lambda r: r["silhouette"])["k"])
    model = KMeans(n_clusters=k, n_init=20, random_state=42) if method == "kmeans" else AgglomerativeClustering(n_clusters=k, linkage="ward")
    labels = model.fit_predict(Z)
    d = d.assign(cluster=labels + 1)
    prof = d.groupby("cluster")[vars_].mean().reset_index()
    sizes = d["cluster"].value_counts().sort_index()
    prof["n"] = prof["cluster"].map(sizes)
    prof["pct"] = 100 * prof["n"] / len(d)
    fig = {"id": "profiles", "title_en": "Cluster profiles (means)", "title_ar": "ملامح العناقيد (المتوسطات)",
           "figure": {"data": [{"type": "bar", "name": f"Cluster {int(r['cluster'])}", "x": vars_, "y": [r[v] for v in vars_]} for _, r in prof.iterrows()],
                      "layout": {"barmode": "group"}}}
    return result("cluster", f"Cluster analysis ({method})", "التحليل العنقودي", params={**params, "k": k}, n=len(d),
                  tables=[table("profiles", "Cluster profiles", "ملامح العناقيد", [col("cluster", "Cluster", "العنقود"), col("n", "N", "العدد"), col("pct", "%", "%", "1")] +
                                [col(v, v, v, "2") for v in vars_], prof.to_dict(orient="records"),
                                "Variables standardized before clustering; profile means in original units.", "وُحِّدت المتغيرات معيارياً قبل التجميع؛ والمتوسطات بالوحدات الأصلية."),
                          table("silhouette", "Silhouette by k", "معامل الصورة الظلية حسب k", [col("k", "k", "k"), col("silhouette", "Silhouette", "الصورة الظلية", "3")], sil)],
                  charts=[to_jsonable(fig), charts.line("sil", [r["k"] for r in sil], {"Silhouette": [r["silhouette"] for r in sil]}, "Silhouette by number of clusters", "الصورة الظلية حسب عدد العناقيد", "k", "Silhouette")],
                  stats={"k": k, "silhouette": next(r["silhouette"] for r in sil if r["k"] == k) if k in ks else None, "sizes": sizes.to_dict()}, nature="exploratory",
                  warnings=[warn("Clusters are data-driven groupings; validate their meaning and stability before interpreting them as types.",
                                 "العناقيد تجميعات مستمدة من البيانات؛ ويجب التحقق من معناها وثباتها قبل تفسيرها كأنماط.")])


def run_discriminant(df, params, ctx):
    group, preds = params["group"], params["predictors"]
    require_columns(df, [group] + preds)
    d = df[preds].apply(pd.to_numeric, errors="coerce")
    d["G"] = df[group].astype(str).where(df[group].notna())
    d = d.dropna()
    if d["G"].nunique() < 2:
        raise AnalysisError("Need ≥ 2 groups.", "يلزم وجود مجموعتين على الأقل.")
    lda = LinearDiscriminantAnalysis().fit(d[preds], d["G"])
    acc = lda.score(d[preds], d["G"])
    folds = min(5, int(d["G"].value_counts().min()))
    cv = cross_val_score(LinearDiscriminantAnalysis(), d[preds], d["G"], cv=folds).mean() if folds >= 2 else None
    cm = confusion_matrix(d["G"], lda.predict(d[preds]), labels=lda.classes_)
    nf = lda.scalings_.shape[1] if lda.scalings_.ndim > 1 else 1
    coef = [{"predictor": p, **{f"LD{j + 1}": lda.scalings_[i, j] for j in range(min(nf, len(lda.classes_) - 1))}} for i, p in enumerate(preds)]
    cm_rows = [{"observed": c, **{f"pred_{k}": int(cm[i, j]) for j, k in enumerate(lda.classes_)}} for i, c in enumerate(lda.classes_)]
    prior = d["G"].value_counts(normalize=True).max()
    return result("discriminant", "Linear discriminant analysis", "التحليل التمييزي الخطي", params=params, n=len(d),
                  tables=[table("coef", "Discriminant function coefficients", "معاملات الدالة التمييزية", [col("predictor", "Predictor", "المتغير")] +
                                [col(f"LD{j + 1}", f"LD{j + 1}", f"LD{j + 1}", "3") for j in range(min(nf, len(lda.classes_) - 1))], coef),
                          table("class", "Classification results", "نتائج التصنيف", [col("observed", "Observed", "الفعلي")] + [col(f"pred_{k}", f"Pred. {k}", f"متنبأ {k}") for k in lda.classes_], cm_rows,
                                f"Accuracy = {acc:.3f}" + (f"; {folds}-fold cross-validated = {cv:.3f}" if cv is not None else "") + f"; proportional chance (largest group) = {prior:.3f}.",
                                f"الدقة = {acc:.3f}" + (f"؛ بالتحقق المتقاطع ({folds} أجزاء) = {cv:.3f}" if cv is not None else "") + f"؛ نسبة الصدفة (أكبر مجموعة) = {prior:.3f}.")],
                  stats={"accuracy": acc, "cv_accuracy": cv, "explained_variance_ratio": list(getattr(lda, "explained_variance_ratio_", []))})


def run_chisquare(df, params, ctx):
    a, b = params["var1"], params["var2"]
    require_columns(df, [a, b])
    d = df[[a, b]].dropna().astype(str)
    ct = pd.crosstab(d[a], d[b])
    if ct.shape[0] < 2 or ct.shape[1] < 2:
        raise AnalysisError("Each variable needs ≥ 2 categories.", "يحتاج كل متغير إلى فئتين على الأقل.")
    chi, p, dof, exp = stats.chi2_contingency(ct, correction=False)
    n = ct.to_numpy().sum()
    low = float((exp < 5).mean() * 100)
    v = math.sqrt(chi / (n * (min(ct.shape) - 1)))
    st = {"chi2": chi, "df": dof, "p": p, "n": int(n), "cramers_v": v, "pct_expected_lt5": low, "min_expected": float(exp.min())}
    if ct.shape == (2, 2):
        chi_y, p_y, _, _ = stats.chi2_contingency(ct, correction=True)
        odds, p_f = stats.fisher_exact(ct.to_numpy())
        st.update({"yates_chi2": chi_y, "yates_p": p_y, "fisher_p": p_f, "odds_ratio": odds, "phi": math.sqrt(chi / n)})
    lr, lr_p, _, _ = stats.chi2_contingency(ct, correction=False, lambda_="log-likelihood")
    st.update({"lr_chi2": lr, "lr_p": lr_p})
    use_fisher = ct.shape == (2, 2) and low > 0
    mag = cohen_label(v * math.sqrt(min(ct.shape) - 1), "w")
    st.update({"recommended": "Fisher's exact test" if use_fisher else "Pearson χ²", "effect_label_en": mag[0], "effect_label_ar": mag[1]})
    rows = []
    for idx in ct.index:
        r = {"row": idx}
        for c in ct.columns:
            r[str(c)] = f"{ct.loc[idx, c]} ({100 * ct.loc[idx, c] / ct.loc[idx].sum():.1f}%)"
        r["total"] = int(ct.loc[idx].sum())
        rows.append(r)
    tests = [{"test_en": "Pearson χ²", "test_ar": "كاي تربيع بيرسون", "value": chi, "df": dof, "p": p},
             {"test_en": "Likelihood ratio", "test_ar": "نسبة الأرجحية", "value": lr, "df": dof, "p": lr_p}]
    if ct.shape == (2, 2):
        tests += [{"test_en": "Continuity correction (Yates)", "test_ar": "تصحيح ييتس", "value": st["yates_chi2"], "df": 1, "p": st["yates_p"]},
                  {"test_en": "Fisher's exact test (2-sided)", "test_ar": "اختبار فيشر الدقيق (ثنائي الطرف)", "value": None, "df": None, "p": st["fisher_p"]}]
    fig = {"id": "stacked", "title_en": f"{a} × {b}", "title_ar": f"{a} × {b}",
           "figure": {"data": [{"type": "bar", "name": str(c), "x": [str(i) for i in ct.index], "y": [100 * ct.loc[i, c] / ct.loc[i].sum() for i in ct.index]} for c in ct.columns],
                      "layout": {"barmode": "stack", "yaxis": {"title": {"text": "% within row"}}}}}
    return result("chisquare", "Chi-square test of independence", "اختبار كاي تربيع للاستقلالية", params=params, n=int(n),
                  tables=[table("crosstab", "Crosstabulation (row %)", "جدول التقاطع (النسبة من الصف)", [col("row", a, a)] + [col(str(c), str(c), str(c)) for c in ct.columns] + [col("total", "Total", "المجموع")], rows),
                          table("tests", "Tests", "الاختبارات", [col("test_en", "Test", "الاختبار"), col("value", "Value", "القيمة", "3"), col("df", "df", "د.ح", "0"), col("p", "p", "p", "p")], tests,
                                f"Cramér's V = {v:.3f}. {low:.1f}% of cells have expected count < 5 (minimum {exp.min():.2f}).",
                                f"V كرامر = {v:.3f}. {low:.1f}% من الخلايا تكرارها المتوقع أقل من 5 (الأدنى {exp.min():.2f}).")],
                  charts=[to_jsonable(fig)],
                  assumptions=[assumption("Expected frequencies", "التكرارات المتوقعة", "≤ 20% of cells < 5, none < 1", low <= 20 and exp.min() >= 1,
                                          f"{low:.1f}% of cells < 5", f"{low:.1f}% من الخلايا < 5")], stats=st,
                  warnings=[warn("Expected-count assumption violated: use Fisher's exact test (2×2) or merge sparse categories.",
                                 "افتراض التكرارات المتوقعة غير متحقق: استخدم اختبار فيشر الدقيق (2×2) أو ادمج الفئات قليلة التكرار.")] if low > 20 else [])


def run_mcnemar(df, params, ctx):
    a, b = params["var1"], params["var2"]
    d = df[[a, b]].dropna().astype(str)
    ct = pd.crosstab(d[a], d[b])
    if ct.shape != (2, 2):
        raise AnalysisError("McNemar's test needs two paired binary variables with the same two categories.", "يتطلب اختبار ماكنمار متغيرين ثنائيين مترابطين بنفس الفئتين.")
    disc = int(ct.iloc[0, 1] + ct.iloc[1, 0])
    exact = disc < 25
    r = mcnemar(ct.to_numpy(), exact=exact, correction=True)
    st = {"statistic": r.statistic, "p": r.pvalue, "exact": exact, "discordant": disc, "n": len(d)}
    rows = [{"row": i, **{str(c): int(ct.loc[i, c]) for c in ct.columns}} for i in ct.index]
    return result("mcnemar", "McNemar test", "اختبار ماكنمار", params=params, n=len(d),
                  tables=[table("ct", "Paired table", "الجدول المزدوج", [col("row", a, a)] + [col(str(c), str(c), str(c)) for c in ct.columns], rows),
                          table("test", "Test", "الاختبار", [col("statistic", "Statistic", "الإحصاءة", "3"), col("p", "p", "p", "p"), col("discordant", "Discordant pairs", "الأزواج المتعارضة")], [st],
                                "Exact binomial test when discordant pairs < 25; otherwise χ² with continuity correction.", "اختبار ذي الحدين الدقيق عند أقل من 25 زوجاً متعارضاً؛ وإلا كاي تربيع مع تصحيح الاستمرارية.")],
                  stats=st)


def run_fisher(df, params, ctx):
    r = run_chisquare(df, params, ctx)
    if "fisher_p" not in r["stats"]:
        raise AnalysisError("Fisher's exact test is implemented for 2×2 tables; merge categories or use χ².", "اختبار فيشر الدقيق متاح لجداول 2×2؛ ادمج الفئات أو استخدم كاي تربيع.")
    r["kind"], r["title_en"], r["title_ar"] = "fisher", "Fisher's exact test", "اختبار فيشر الدقيق"
    r["stats"]["p"] = r["stats"]["fisher_p"]
    return r


def _km(t, e):
    order = np.argsort(t)
    t, e = t[order], e[order]
    times = np.unique(t[e == 1])
    s, out = 1.0, [{"time": 0.0, "survival": 1.0, "at_risk": len(t), "events": 0}]
    for tt in times:
        n = (t >= tt).sum()
        dth = ((t == tt) & (e == 1)).sum()
        s *= 1 - dth / n
        out.append({"time": float(tt), "survival": s, "at_risk": int(n), "events": int(dth)})
    median = next((r["time"] for r in out if r["survival"] <= 0.5), None)
    return out, median


def run_survival(df, params, ctx):
    tcol, ecol, group = params["time"], params["event"], params.get("group")
    require_columns(df, [tcol, ecol] + ([group] if group else []))
    d = pd.DataFrame({"t": pd.to_numeric(df[tcol], errors="coerce"), "e": pd.to_numeric(df[ecol], errors="coerce")})
    if group:
        d["g"] = df[group].astype(str).where(df[group].notna())
    d = d.dropna()
    if not set(d["e"].unique()) <= {0, 1}:
        raise AnalysisError("The event variable must be coded 0 = censored, 1 = event.", "يجب ترميز متغير الحدث 0 = مراقَب، 1 = حدث.")
    require_n(len(d), 10, "survival analysis")
    groups = [("All", d)] if not group else list(d.groupby("g"))
    rows, data = [], []
    for g, sub in groups:
        curve, med = _km(sub["t"].to_numpy(), sub["e"].to_numpy())
        rows.append({"group": g, "n": len(sub), "events": int(sub["e"].sum()), "censored": int((sub["e"] == 0).sum()), "median": med})
        data.append({"type": "scatter", "mode": "lines", "line": {"shape": "hv"}, "name": str(g), "x": [c["time"] for c in curve], "y": [c["survival"] for c in curve]})
    st = {"groups": rows}
    tables = [table("km", "Kaplan–Meier summary", "ملخص كابلان–ماير", [col("group", "Group", "المجموعة"), col("n", "N", "العدد"), col("events", "Events", "الأحداث"),
                                                                     col("censored", "Censored", "المراقَبة"), col("median", "Median survival", "الوسيط", "2")], rows)]
    if group and len(groups) >= 2:
        # log-rank test
        times = np.sort(d.loc[d["e"] == 1, "t"].unique())
        levels = [g for g, _ in groups]
        O = np.zeros(len(levels)); E = np.zeros(len(levels)); V = np.zeros((len(levels), len(levels)))
        for tt in times:
            at = np.array([(d.loc[d["g"] == g, "t"] >= tt).sum() for g in levels], dtype=float)
            ev = np.array([((d["g"] == g) & (d["t"] == tt) & (d["e"] == 1)).sum() for g in levels], dtype=float)
            N, D = at.sum(), ev.sum()
            if N <= 1:
                continue
            O += ev; E += D * at / N
            V += (D * (N - D) / (N - 1)) * (np.diag(at / N) - np.outer(at / N, at / N))
        k = len(levels) - 1
        diff = (O - E)[:k]
        chi = float(diff @ np.linalg.pinv(V[:k, :k]) @ diff)
        p = float(stats.chi2.sf(chi, k))
        st.update({"logrank_chi2": chi, "df": k, "p": p})
        tables.append(table("logrank", "Log-rank test", "اختبار اللوغاريتم الرتبي", [col("logrank_chi2", "χ²", "χ²", "3"), col("df", "df", "د.ح", "0"), col("p", "p", "p", "p")], [st]))
    return result("survival", "Survival analysis (Kaplan–Meier)", "تحليل البقاء (كابلان–ماير)", params=params, n=len(d), tables=tables,
                  charts=[{"id": "km", "title_en": "Kaplan–Meier curves", "title_ar": "منحنيات كابلان–ماير",
                           "figure": {"data": data, "layout": {"xaxis": {"title": {"text": tcol}}, "yaxis": {"title": {"text": "S(t)"}, "range": [0, 1.05]}}}}], stats=st)
