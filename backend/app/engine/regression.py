"""Correlation and regression models."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats
from statsmodels.miscmodels.ordinal_model import OrderedModel
from statsmodels.stats.diagnostic import het_breuschpagan
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.outliers_influence import variance_inflation_factor
from statsmodels.stats.stattools import durbin_watson

from . import charts
from .utils import AnalysisError, assumption, cohen_label, col, fp, require_columns, require_n, result, table, to_jsonable, warn

# --------------------------------------------------------------------------------------------
# Correlation
# --------------------------------------------------------------------------------------------


def corr_ci(r: float, n: int, method: str, conf: float = 0.95) -> tuple[float, float]:
    if n <= 4 or r is None or abs(r) >= 1:
        return float("nan"), float("nan")
    z = math.atanh(r)
    if method == "pearson":
        se = 1 / math.sqrt(n - 3)
    elif method == "spearman":
        se = math.sqrt((1 + r ** 2 / 2) / (n - 3))  # Bonett & Wright (2000)
    else:
        se = math.sqrt(0.437 / (n - 4))  # Fieller et al. (1957)
    q = stats.norm.ppf(0.5 + conf / 2)
    return math.tanh(z - q * se), math.tanh(z + q * se)


def correlate(x: pd.Series, y: pd.Series, method: str) -> dict:
    d = pd.DataFrame({"x": pd.to_numeric(x, errors="coerce"), "y": pd.to_numeric(y, errors="coerce")}).dropna()
    n = len(d)
    if n < 3 or d["x"].std() == 0 or d["y"].std() == 0:
        return {"r": None, "p": None, "n": n}
    if method == "pearson":
        r, p = stats.pearsonr(d["x"], d["y"])
    elif method == "spearman":
        r, p = stats.spearmanr(d["x"], d["y"])
    else:
        r, p = stats.kendalltau(d["x"], d["y"], variant="b")
    lo, hi = corr_ci(r, n, method)
    return {"r": float(r), "p": float(p), "n": n, "ci_low": lo, "ci_high": hi}


def run_correlation(df, params, ctx):
    vars_ = params.get("variables") or []
    if len(vars_) < 2:
        raise AnalysisError("Select at least two numeric variables.", "اختر متغيرين رقميين على الأقل.")
    require_columns(df, vars_)
    method = params.get("method", "pearson")
    adjust = params.get("adjust", "none")
    pairs = []
    R = pd.DataFrame(np.eye(len(vars_)), index=vars_, columns=vars_)
    P = pd.DataFrame(np.nan, index=vars_, columns=vars_)
    for i, a in enumerate(vars_):
        for b in vars_[:i]:
            c = correlate(df[a], df[b], method)
            R.loc[a, b] = R.loc[b, a] = c["r"] if c["r"] is not None else np.nan
            pairs.append({"var1": b, "var2": a, **c})
    if adjust != "none" and pairs:
        valid = [p for p in pairs if p["p"] is not None]
        adj = multipletests([p["p"] for p in valid], method={"holm": "holm", "bonferroni": "bonferroni", "fdr": "fdr_bh"}[adjust])[1]
        for p_, a_ in zip(valid, adj):
            p_["p_adj"] = a_
    for p_ in pairs:
        if p_["r"] is not None:
            lab = cohen_label(p_["r"], "r")
            p_["strength_en"] = f"{lab[0]} {'positive' if p_['r'] > 0 else 'negative'}"
            p_["strength_ar"] = f"{lab[1]} {'موجب' if p_['r'] > 0 else 'سالب'}"
        pv = p_.get("p_adj", p_["p"])
        p_["sig"] = "***" if pv is not None and pv < .001 else "**" if pv is not None and pv < .01 else "*" if pv is not None and pv < .05 else ""
    mrows = []
    for a in vars_:
        row = {"variable": a}
        for b in vars_:
            pr = next((p for p in pairs if {p["var1"], p["var2"]} == {a, b}), None)
            row[b] = 1.0 if a == b else (f"{pr['r']:.3f}{pr['sig']}" if pr and pr["r"] is not None else "—")
        mrows.append(row)
    sym = {"pearson": ("r", "Pearson"), "spearman": ("rs", "Spearman"), "kendall": ("τb", "Kendall")}[method]
    tables = [table("matrix", f"{sym[1]} correlation matrix", f"مصفوفة ارتباط {sym[1]}", [col("variable", "", "")] + [col(v, v, v) for v in vars_], mrows,
                    "* p < .05, ** p < .01, *** p < .001" + (f" ({adjust}-adjusted)" if adjust != "none" else "") + ". Pairwise deletion.",
                    "* p < .05، ** p < .01، *** p < .001" + (f" (معدلة بطريقة {adjust})" if adjust != "none" else "") + ". حذف زوجي للقيم المفقودة."),
              table("pairs", "Pairwise correlations", "الارتباطات الثنائية",
                    [col("var1", "Variable 1", "المتغير 1"), col("var2", "Variable 2", "المتغير 2"), col("n", "N", "العدد"), col("r", sym[0], sym[0], "3"),
                     col("ci_low", "95% CI low", "الحد الأدنى", "3"), col("ci_high", "95% CI high", "الحد الأعلى", "3"), col("p", "p", "p", "p")] +
                    ([col("p_adj", "p (adj.)", "p معدلة", "p")] if adjust != "none" else []) + [col("strength_en", "Strength", "القوة")], pairs,
                    "Correlation does not imply causation.", "الارتباط لا يعني السببية.")]
    ch = [charts.heatmap("heatmap", R, f"{sym[1]} correlation heatmap", f"خريطة حرارية لارتباط {sym[1]}")]
    if len(vars_) == 2:
        ch.append(charts.scatter("scatter", df[vars_[0]], df[vars_[1]], vars_[0], vars_[1]))
    asum = []
    if method == "pearson" and len(vars_) == 2:
        from .descriptive import normality
        for v in vars_:
            nr = normality(df[v])
            if "error" not in nr:
                asum.append(assumption(f"Normality ({v})", f"الاعتدالية ({v})", "Shapiro–Wilk / skew–kurtosis", nr["approximately_normal"],
                                       nr["basis_en"], nr["basis_ar"], nr.get("shapiro_w"), nr.get("shapiro_p")))
    return result("correlation", f"{sym[1]} correlation", f"ارتباط {sym[1]}", params=params, n=len(df), tables=tables, charts=ch,
                  assumptions=asum, stats={"pairs": pairs, "method": method, "adjust": adjust})


# --------------------------------------------------------------------------------------------
# Regression helpers
# --------------------------------------------------------------------------------------------


def _design(df: pd.DataFrame, dv: str, ivs: list[str], ctx, poly: int = 1) -> tuple[pd.Series, pd.DataFrame, dict]:
    require_columns(df, [dv] + ivs)
    cols = {}
    sources = {}
    for v in ivs:
        if ctx["is_numeric"](v):
            x = pd.to_numeric(df[v], errors="coerce")
            cols[v] = x
            sources[v] = v
            if poly > 1 and len(ivs) == 1:
                xc = x - x.mean()
                cols[v] = xc
                for k in range(2, poly + 1):
                    cols[f"{v}^{k}"] = xc ** k
                    sources[f"{v}^{k}"] = v
        else:
            s = df[v].map(lambda z: None if z is None or (isinstance(z, float) and np.isnan(z)) else str(z))
            dummies = pd.get_dummies(s, prefix=v, prefix_sep="=", drop_first=True, dtype=float)
            dummies[s.isna()] = np.nan
            for c in dummies.columns:
                cols[c] = dummies[c]
                sources[c] = v
    X = pd.DataFrame(cols, index=df.index)
    y = df[dv]
    d = pd.concat([y.rename("__y__"), X], axis=1).dropna()
    return d["__y__"], d.drop(columns="__y__"), sources


def _ols(y, X):
    return sm.OLS(pd.to_numeric(y), sm.add_constant(X, has_constant="add")).fit()


def _coef_rows(model, X, y, standardized=True):
    rows = []
    ci = model.conf_int()
    sdy = y.std(ddof=1)
    for name in model.params.index:
        beta = model.params[name] * X[name].std(ddof=1) / sdy if standardized and name != "const" else None
        rows.append({"term": "(Intercept)" if name == "const" else name, "B": model.params[name], "se": model.bse[name], "beta": beta,
                     "t": model.tvalues[name], "p": model.pvalues[name], "ci_low": ci.loc[name, 0], "ci_high": ci.loc[name, 1]})
    if X.shape[1] > 1:
        Xc = sm.add_constant(X, has_constant="add").to_numpy()
        for i, name in enumerate(X.columns, start=1):
            vif = variance_inflation_factor(Xc, i)
            for r in rows:
                if r["term"] == name:
                    r["vif"] = vif
                    r["tolerance"] = 1 / vif if vif else None
    return rows


COEF_COLS = [col("term", "Predictor", "المتغير المستقل"), col("B", "B", "B", "3"), col("se", "SE", "الخطأ المعياري", "3"), col("beta", "β", "β", "3"),
             col("t", "t", "ت", "3"), col("p", "p", "p", "p"), col("ci_low", "95% CI low", "الحد الأدنى", "3"), col("ci_high", "95% CI high", "الحد الأعلى", "3"),
             col("vif", "VIF", "VIF", "2")]


def _diagnostics(model, X) -> tuple[list, dict]:
    resid = model.resid
    out, info = [], {}
    if len(resid) <= 5000 and len(resid) >= 3:
        w, p = stats.shapiro(resid)
        out.append(assumption("Normality of residuals", "اعتدالية البواقي", "Shapiro–Wilk", p >= 0.05 or len(resid) > 300,
                              f"W = {w:.3f}, p {fp(p)}" + (" (large n: rely on Q-Q plot)" if len(resid) > 300 else ""),
                              f"W = {w:.3f}، p {fp(p)}" + (" (عينة كبيرة: يُعتمد على مخطط Q-Q)" if len(resid) > 300 else ""), w, p))
        info["shapiro_resid_p"] = p
    lm, lmp, _, _ = het_breuschpagan(resid, sm.add_constant(X, has_constant="add"))
    out.append(assumption("Homoscedasticity", "تجانس تباين البواقي", "Breusch–Pagan", lmp >= 0.05, f"LM = {lm:.3f}, p {fp(lmp)}", f"LM = {lm:.3f}، p {fp(lmp)}", lm, lmp))
    dw = durbin_watson(resid)
    out.append(assumption("Independence of errors", "استقلالية الأخطاء", "Durbin–Watson", 1.5 <= dw <= 2.5, f"DW = {dw:.3f} (≈ 2 ideal)", f"DW = {dw:.3f} (القيمة المثلى ≈ 2)", dw))
    infl = model.get_influence()
    cooks = infl.cooks_distance[0]
    n_infl = int((cooks > 4 / len(resid)).sum())
    out.append(assumption("Influential cases", "الحالات المؤثرة", "Cook's distance", bool(cooks.max() < 1),
                          f"max D = {cooks.max():.3f}; {n_infl} case(s) > 4/n", f"أكبر D = {cooks.max():.3f}؛ {n_infl} حالة > 4/n", float(cooks.max())))
    if X.shape[1] > 1:
        Xc = sm.add_constant(X, has_constant="add").to_numpy()
        vifs = [variance_inflation_factor(Xc, i) for i in range(1, Xc.shape[1])]
        out.append(assumption("Multicollinearity", "التعدد الخطي", "VIF", max(vifs) < 5, f"max VIF = {max(vifs):.2f} (< 5)", f"أكبر VIF = {max(vifs):.2f} (< 5)", max(vifs)))
    info.update({"durbin_watson": dw, "max_cooks": float(cooks.max())})
    return out, info


def _resid_charts(model):
    fitted, resid = model.fittedvalues, model.resid
    sres = model.get_influence().resid_studentized_internal
    return [
        {"id": "resid_fitted", "title_en": "Residuals vs fitted", "title_ar": "البواقي مقابل القيم المتنبأ بها",
         "figure": {"data": [{"type": "scatter", "mode": "markers", "x": list(map(float, fitted)), "y": list(map(float, resid)), "marker": {"size": 5, "opacity": 0.6}}],
                    "layout": {"xaxis": {"title": {"text": "Fitted"}}, "yaxis": {"title": {"text": "Residual"}, "zeroline": True}, "showlegend": False}}},
        charts.qq_plot("resid_qq", pd.Series(sres), "standardized residuals"),
    ]


def run_linear(df, params, ctx):
    dv, ivs = params["dv"], params.get("ivs") or []
    if not ivs:
        raise AnalysisError("Select at least one predictor.", "اختر متغيراً مستقلاً واحداً على الأقل.")
    poly = int(params.get("polynomial", 1))
    if not ctx["is_numeric"](dv):
        raise AnalysisError("Linear regression needs a numeric (interval/ratio) dependent variable; use logistic/ordinal regression otherwise.",
                            "يتطلب الانحدار الخطي متغيراً تابعاً رقمياً (فتري/نسبي)؛ وإلا فاستخدم الانحدار اللوجستي أو الرتبي.")
    y, X, src = _design(df, dv, ivs, ctx, poly)
    y = pd.to_numeric(y)
    require_n(len(y), X.shape[1] + 3, "regression")
    m = _ols(y, X)
    asum, diag = _diagnostics(m, X)
    f2 = m.rsquared / (1 - m.rsquared) if m.rsquared < 1 else float("nan")
    mag = cohen_label(f2, "f2")
    st = {"dv": dv, "ivs": ivs, "n": int(m.nobs), "r": math.sqrt(max(m.rsquared, 0)), "r2": m.rsquared, "adj_r2": m.rsquared_adj, "F": m.fvalue,
          "df1": m.df_model, "df2": m.df_resid, "p": m.f_pvalue, "se_estimate": math.sqrt(m.mse_resid), "f2": f2,
          "coefficients": _coef_rows(m, X, y), "aic": m.aic, "bic": m.bic, **diag, "effect_label_en": mag[0], "effect_label_ar": mag[1],
          "polynomial": poly}
    kind = "polynomial" if poly > 1 else ("linear_simple" if len(ivs) == 1 and X.shape[1] == 1 else "linear_multiple")
    titles = {"polynomial": ("Polynomial regression", "الانحدار متعدد الحدود"), "linear_simple": ("Simple linear regression", "الانحدار الخطي البسيط"),
              "linear_multiple": ("Multiple linear regression", "الانحدار الخطي المتعدد")}[kind]
    tables = [table("summary", "Model summary", "ملخص النموذج",
                    [col("r", "R", "R", "3"), col("r2", "R²", "R²", "3"), col("adj_r2", "Adjusted R²", "R² المعدل", "3"), col("se_estimate", "SE of estimate", "الخطأ المعياري للتقدير", "3"),
                     col("F", "F", "ف", "3"), col("df1", "df1", "د.ح1", "0"), col("df2", "df2", "د.ح2", "0"), col("p", "p", "p", "p"), col("f2", "Cohen's f²", "f² كوهين", "3"),
                     col("durbin_watson", "Durbin–Watson", "دربن–واتسون", "3")], [st]),
              table("coefficients", "Coefficients", "المعاملات", COEF_COLS, st["coefficients"],
                    "β = standardized coefficient. Categorical predictors are dummy-coded against the first category." + (" Polynomial terms use the mean-centred predictor." if poly > 1 else ""),
                    "β = المعامل المعياري. المتغيرات الفئوية مرمّزة وهمياً مقارنة بالفئة الأولى." + (" حدود كثيرة الحدود محسوبة على المتغير بعد تمركزه حول المتوسط." if poly > 1 else ""))]
    ch = _resid_charts(m)
    if len(ivs) == 1 and ctx["is_numeric"](ivs[0]):
        ch.insert(0, charts.scatter("fit", df[ivs[0]], df[dv], ivs[0], dv))
    return result(kind, titles[0], titles[1], params=params, n=int(m.nobs), tables=tables, charts=ch, assumptions=asum, stats=st)


def run_hierarchical(df, params, ctx):
    dv, blocks = params["dv"], params.get("blocks") or []
    if len(blocks) < 2:
        raise AnalysisError("Define at least two blocks of predictors.", "حدد كتلتين على الأقل من المتغيرات المستقلة.")
    all_iv = [v for b in blocks for v in b]
    y_all, X_all, _ = _design(df, dv, all_iv, ctx)
    idx = X_all.index
    steps, prev, cum = [], None, []
    final = None
    for i, b in enumerate(blocks, 1):
        cum += b
        _, X, _ = _design(df.loc[idx], dv, cum, ctx)
        y = pd.to_numeric(y_all.loc[X.index])
        m = _ols(y, X)
        if prev is None:
            dr2, fch, df1, pch = m.rsquared, m.fvalue, m.df_model, m.f_pvalue
        else:
            dr2 = m.rsquared - prev.rsquared
            df1 = m.df_model - prev.df_model
            fch = (dr2 / df1) / ((1 - m.rsquared) / m.df_resid)
            pch = stats.f.sf(fch, df1, m.df_resid)
        steps.append({"step": i, "added": ", ".join(b), "r2": m.rsquared, "adj_r2": m.rsquared_adj, "delta_r2": dr2, "F_change": fch, "df1": df1,
                      "df2": m.df_resid, "p_change": pch, "F": m.fvalue, "p": m.f_pvalue})
        prev, final, Xf, yf = m, m, X, y
    return result("hierarchical", "Hierarchical regression", "الانحدار الهرمي", params=params, n=int(final.nobs),
                  tables=[table("steps", "Model comparison", "مقارنة النماذج",
                                [col("step", "Step", "الخطوة"), col("added", "Predictors added", "المتغيرات المضافة"), col("r2", "R²", "R²", "3"), col("adj_r2", "Adj. R²", "R² المعدل", "3"),
                                 col("delta_r2", "ΔR²", "ΔR²", "3"), col("F_change", "F change", "ف التغير", "3"), col("df1", "df1", "د.ح1", "0"), col("df2", "df2", "د.ح2", "0"),
                                 col("p_change", "p (change)", "p للتغير", "p")], steps),
                          table("coefficients", "Coefficients (final model)", "المعاملات (النموذج النهائي)", COEF_COLS, _coef_rows(final, Xf, yf))],
                  assumptions=_diagnostics(final, Xf)[0], stats={"steps": steps, "dv": dv})


def _pseudo_r2(llf, llnull, n):
    mcf = 1 - llf / llnull
    cs = 1 - math.exp(2 * (llnull - llf) / n)
    nag = cs / (1 - math.exp(2 * llnull / n))
    return mcf, cs, nag


def run_logistic(df, params, ctx):
    dv, ivs = params["dv"], params.get("ivs") or []
    require_columns(df, [dv] + ivs)
    s = df[dv].map(lambda v: None if v is None or (isinstance(v, float) and np.isnan(v)) else (str(int(v)) if isinstance(v, float) and v.is_integer() else str(v)))
    levels = sorted(s.dropna().unique())
    if len(levels) != 2:
        raise AnalysisError(f"Binary logistic regression needs a DV with exactly 2 categories (found {len(levels)}).",
                            f"يتطلب الانحدار اللوجستي الثنائي متغيراً تابعاً بفئتين فقط (وُجد {len(levels)}).")
    event = str(params.get("event") or levels[1])
    tmp = df.copy()
    tmp["__dv__"] = (s == event).astype(float).where(s.notna())
    y, X, _ = _design(tmp, "__dv__", ivs, ctx)
    require_n(len(y), X.shape[1] * 10, "logistic regression (≈10 cases per predictor)")
    try:
        m = sm.Logit(y, sm.add_constant(X, has_constant="add")).fit(disp=False, maxiter=200)
    except Exception as exc:  # noqa: BLE001
        raise AnalysisError(f"Model did not converge: {exc}", f"لم يتقارب النموذج: {exc}") from exc
    mcf, cs, nag = _pseudo_r2(m.llf, m.llnull, m.nobs)
    ci = m.conf_int()
    rows = [{"term": "(Intercept)" if k == "const" else k, "B": m.params[k], "se": m.bse[k], "wald": (m.params[k] / m.bse[k]) ** 2, "p": m.pvalues[k],
             "OR": math.exp(m.params[k]), "or_low": math.exp(ci.loc[k, 0]), "or_high": math.exp(ci.loc[k, 1])} for k in m.params.index]
    pred = (m.predict() >= 0.5).astype(int)
    acc = float((pred == y.to_numpy()).mean())
    # Hosmer–Lemeshow (deciles of risk)
    prob = pd.Series(m.predict(), index=y.index)
    groups = pd.qcut(prob.rank(method="first"), 10, labels=False, duplicates="drop")
    obs = y.groupby(groups).sum()
    exp = prob.groupby(groups).sum()
    cnt = y.groupby(groups).count()
    hl = float((((obs - exp) ** 2) / (exp * (1 - exp / cnt))).sum())
    hl_df = int(groups.nunique() - 2)
    hl_p = float(stats.chi2.sf(hl, hl_df)) if hl_df > 0 else None
    tp = int(((pred == 1) & (y == 1)).sum()); tn = int(((pred == 0) & (y == 0)).sum())
    fp_ = int(((pred == 1) & (y == 0)).sum()); fn = int(((pred == 0) & (y == 1)).sum())
    st = {"dv": dv, "event": event, "reference": [l for l in levels if l != event][0], "n": int(m.nobs), "llr_chi2": m.llr, "llr_df": m.df_model, "llr_p": m.llr_pvalue,
          "minus2ll": -2 * m.llf, "mcfadden_r2": mcf, "coxsnell_r2": cs, "nagelkerke_r2": nag, "accuracy": acc, "hl_chi2": hl, "hl_df": hl_df, "hl_p": hl_p,
          "coefficients": rows, "confusion": {"tp": tp, "tn": tn, "fp": fp_, "fn": fn}}
    return result("logistic", "Binary logistic regression", "الانحدار اللوجستي الثنائي", params=params, n=int(m.nobs),
                  tables=[table("fit", "Model fit", "جودة النموذج",
                                [col("llr_chi2", "LR χ²", "χ² نسبة الأرجحية", "3"), col("llr_df", "df", "د.ح", "0"), col("llr_p", "p", "p", "p"), col("minus2ll", "−2LL", "−2LL", "2"),
                                 col("coxsnell_r2", "Cox & Snell R²", "R² كوكس وسنيل", "3"), col("nagelkerke_r2", "Nagelkerke R²", "R² ناجيلكيرك", "3"),
                                 col("mcfadden_r2", "McFadden R²", "R² ماكفادن", "3"), col("hl_chi2", "Hosmer–Lemeshow χ²", "هوزمر–ليمشو χ²", "3"), col("hl_p", "H–L p", "p (H–L)", "p"),
                                 col("accuracy", "Accuracy (cut .5)", "الدقة (عتبة .5)", "3")], [st], f"Event = '{event}'.", f"الحدث = '{event}'."),
                          table("coefficients", "Variables in the equation", "المتغيرات في المعادلة",
                                [col("term", "Predictor", "المتغير"), col("B", "B", "B", "3"), col("se", "SE", "الخطأ المعياري", "3"), col("wald", "Wald", "والد", "3"),
                                 col("p", "p", "p", "p"), col("OR", "Exp(B)", "نسبة الأرجحية", "3"), col("or_low", "95% CI low", "الحد الأدنى", "3"),
                                 col("or_high", "95% CI high", "الحد الأعلى", "3")], rows),
                          table("classification", "Classification table", "جدول التصنيف",
                                [col("observed", "Observed", "الفعلي"), col("pred0", "Predicted: other", "متنبأ: أخرى"), col("pred1", f"Predicted: {event}", f"متنبأ: {event}")],
                                [{"observed": "other", "pred0": tn, "pred1": fp_}, {"observed": event, "pred0": fn, "pred1": tp}])], stats=st)


def run_ordinal(df, params, ctx):
    dv, ivs = params["dv"], params.get("ivs") or []
    y_raw = pd.to_numeric(df[dv], errors="coerce")
    if y_raw.notna().sum() == 0:
        cats = sorted(df[dv].dropna().astype(str).unique())
        order = params.get("order") or cats
        y_raw = df[dv].astype(str).map({c: i for i, c in enumerate(order)})
    tmp = df.copy()
    tmp["__dv__"] = y_raw
    y, X, _ = _design(tmp, "__dv__", ivs, ctx)
    if y.nunique() < 3:
        raise AnalysisError("Ordinal regression needs an ordered DV with ≥ 3 categories.", "يتطلب الانحدار الرتبي متغيراً تابعاً مرتباً بثلاث فئات فأكثر.")
    yc = pd.Categorical(y, ordered=True)
    try:
        m = OrderedModel(yc, X, distr="logit").fit(method="bfgs", disp=False, maxiter=1000)
    except Exception as exc:  # noqa: BLE001
        raise AnalysisError(f"Model did not converge: {exc}", f"لم يتقارب النموذج: {exc}") from exc
    # null model log-likelihood from category proportions
    props = pd.Series(yc).value_counts(normalize=True)
    ll0 = float((pd.Series(yc).value_counts() * np.log(props)).sum())
    lr = 2 * (m.llf - ll0)
    k = X.shape[1]
    mcf, cs, nag = _pseudo_r2(m.llf, ll0, len(y))
    ci = m.conf_int()
    rows = []
    for name in m.params.index:
        is_thr = name not in X.columns
        rows.append({"term": f"threshold {name}" if is_thr else name, "B": m.params[name], "se": m.bse[name], "z": m.tvalues[name], "p": m.pvalues[name],
                     "OR": None if is_thr else math.exp(m.params[name]), "or_low": None if is_thr else math.exp(ci.loc[name, 0]),
                     "or_high": None if is_thr else math.exp(ci.loc[name, 1])})
    st = {"dv": dv, "n": len(y), "lr_chi2": lr, "lr_df": k, "lr_p": stats.chi2.sf(lr, k), "mcfadden_r2": mcf, "nagelkerke_r2": nag, "coefficients": rows, "aic": m.aic}
    return result("ordinal", "Ordinal logistic regression (proportional odds)", "الانحدار اللوجستي الرتبي (الأرجحيات التناسبية)", params=params, n=len(y),
                  tables=[table("fit", "Model fit", "جودة النموذج", [col("lr_chi2", "LR χ²", "χ²", "3"), col("lr_df", "df", "د.ح", "0"), col("lr_p", "p", "p", "p"),
                                                                     col("nagelkerke_r2", "Nagelkerke R²", "R² ناجيلكيرك", "3"), col("mcfadden_r2", "McFadden R²", "R² ماكفادن", "3"), col("aic", "AIC", "AIC", "1")], [st]),
                          table("coefficients", "Parameter estimates", "تقديرات المعلمات",
                                [col("term", "Term", "الحد"), col("B", "B", "B", "3"), col("se", "SE", "الخطأ المعياري", "3"), col("z", "z", "z", "3"), col("p", "p", "p", "p"),
                                 col("OR", "OR", "نسبة الأرجحية", "3"), col("or_low", "95% CI low", "الحد الأدنى", "3"), col("or_high", "95% CI high", "الحد الأعلى", "3")], rows,
                                "Thresholds are reported in statsmodels' parametrisation (first cut-point, then log-increments).",
                                "العتبات معروضة وفق صيغة statsmodels (نقطة القطع الأولى ثم الزيادات اللوغاريتمية).")],
                  stats=st, warnings=[warn("The proportional-odds assumption is not formally tested here (no Brant test); interpret ORs as averaged across cut-points.",
                                           "لم يُختبر افتراض الأرجحيات التناسبية رسمياً (اختبار برانت غير متاح)؛ وتُفسَّر نسب الأرجحية كمتوسط عبر نقاط القطع.")])
