"""Factor analysis: EFA, PCA (with parallel analysis), and CFA/SEM via semopy.

CFA is only run on an explicitly specified measurement model (the researcher-confirmed
dimensions or custom lavaan-style syntax). It is never inferred from EFA/PCA output.
"""
from __future__ import annotations

import re
import warnings as _w

import numpy as np
import pandas as pd
from factor_analyzer import FactorAnalyzer, Rotator
from factor_analyzer.factor_analyzer import calculate_bartlett_sphericity, calculate_kmo

from . import charts
from .utils import AnalysisError, assumption, col, result, table, to_jsonable, warn


def _safe(name: str) -> str:
    s = re.sub(r"\W", "_", str(name), flags=re.UNICODE)
    return s if re.match(r"^[A-Za-z_]", s) else f"v_{s}"


def parallel_analysis(data: np.ndarray, iterations: int = 100, seed: int = 2024, percentile: float = 95) -> np.ndarray:
    """Horn's parallel analysis on PCA eigenvalues of random normal data with the same n and p."""
    rng = np.random.default_rng(seed)
    n, p = data.shape
    eig = np.empty((iterations, p))
    for i in range(iterations):
        r = np.corrcoef(rng.standard_normal((n, p)), rowvar=False)
        eig[i] = np.sort(np.linalg.eigvalsh(r))[::-1]
    return np.percentile(eig, percentile, axis=0)


def _prep(df: pd.DataFrame, items: list[str]) -> pd.DataFrame:
    if len(items) < 3:
        raise AnalysisError("Factor analysis requires at least 3 items.", "يتطلب التحليل العاملي 3 بنود على الأقل.")
    data = df[items].apply(pd.to_numeric, errors="coerce").dropna()
    data = data.loc[:, data.std() > 0]
    if len(data) < len(items) + 5:
        raise AnalysisError(f"Too few complete cases ({len(data)}) for {len(items)} items.", f"عدد الحالات المكتملة ({len(data)}) قليل لعدد {len(items)} بنود.")
    return data


def _common(data: pd.DataFrame) -> tuple[list, dict, np.ndarray, np.ndarray]:
    kmo_items, kmo_all = calculate_kmo(data.to_numpy())
    chi, p = calculate_bartlett_sphericity(data.to_numpy())
    asum = [assumption("Sampling adequacy (KMO)", "كفاية العينة (KMO)", "KMO", kmo_all >= 0.6,
                       f"KMO = {kmo_all:.3f} (≥ .60 acceptable, ≥ .80 meritorious)", f"KMO = {kmo_all:.3f} (≥ .60 مقبول، ≥ .80 جيد)", kmo_all),
            assumption("Bartlett's test of sphericity", "اختبار بارتليت للكروية", "Bartlett", p < 0.05,
                       f"χ²({data.shape[1] * (data.shape[1] - 1) // 2}) = {chi:.2f}, p {'< .001' if p < .001 else f'= {p:.3f}'}",
                       f"χ²({data.shape[1] * (data.shape[1] - 1) // 2}) = {chi:.2f}، p {'< .001' if p < .001 else f'= {p:.3f}'}", chi, p),
            assumption("Sample size", "حجم العينة", "N:p ratio", len(data) >= 5 * data.shape[1],
                       f"N = {len(data)}, p = {data.shape[1]} (ratio {len(data) / data.shape[1]:.1f}:1)",
                       f"N = {len(data)}، عدد البنود = {data.shape[1]} (النسبة {len(data) / data.shape[1]:.1f}:1)")]
    eig = np.sort(np.linalg.eigvalsh(np.corrcoef(data.to_numpy(), rowvar=False)))[::-1]
    pa = parallel_analysis(data.to_numpy())
    return asum, {"kmo": kmo_all, "kmo_items": dict(zip(data.columns, kmo_items)), "bartlett_chi2": chi, "bartlett_p": p}, eig, pa


def _scree(eig, pa, cid="scree") -> dict:
    x = list(range(1, len(eig) + 1))
    return charts.line(cid, x, {"Observed eigenvalues": list(map(float, eig)), "Parallel analysis (95th pct)": list(map(float, pa))},
                       "Scree plot with parallel analysis", "مخطط الانحدار (Scree) مع التحليل الموازي", "Factor", "Eigenvalue",
                       dash={"Parallel analysis (95th pct)": "dash"})


def _loading_table(L: np.ndarray, items, names, communal, title_en, title_ar, threshold=0.4):
    rows = []
    for i, it in enumerate(items):
        r = {"item": it}
        big = []
        for j, f in enumerate(names):
            r[f] = L[i, j]
            if abs(L[i, j]) >= threshold:
                big.append(f)
        r["h2"] = communal[i]
        r["flag_en"] = "no loading ≥ .40" if not big else ("cross-loading" if len(big) > 1 else "")
        r["flag_ar"] = "لا يوجد تشبع ≥ .40" if not big else ("تشبع متقاطع" if len(big) > 1 else "")
        rows.append(r)
    cols = [col("item", "Item", "البند")] + [col(f, f, f, "3") for f in names] + [col("h2", "h²", "الاشتراكيات", "3"), col("flag_en", "Flag", "ملاحظة")]
    return table("loadings", title_en, title_ar, cols, rows, f"Loadings with |λ| ≥ {threshold:.2f} considered salient.", f"تُعد التشبعات |λ| ≥ {threshold:.2f} جوهرية.")


def _loading_chart(L, items, names):
    data = [{"type": "bar", "orientation": "h", "y": list(items), "x": [float(v) for v in L[:, j]], "name": f} for j, f in enumerate(names)]
    return {"id": "loading_plot", "title_en": "Factor loadings", "title_ar": "تشبعات العوامل",
            "figure": {"data": data, "layout": {"barmode": "group", "yaxis": {"autorange": "reversed", "automargin": True},
                                                "xaxis": {"range": [-1, 1]}, "margin": {"l": 120, "r": 20, "t": 40, "b": 40}}}}


def run_efa(df: pd.DataFrame, params: dict, ctx: dict) -> dict:
    items = params.get("items") or [v["name"] for v in ctx["dictionary"]["variables"] if v.get("is_likert")]
    data = _prep(df, items)
    asum, info, eig, pa = _common(data)
    n_pa = int(np.sum(eig > pa)) if np.any(eig > pa) else 1
    n_kaiser = int(np.sum(eig > 1))
    nf = int(params.get("n_factors") or max(1, n_pa))
    nf = min(nf, data.shape[1] - 1)
    method = params.get("method", "minres")
    rotation = params.get("rotation", "oblimin" if nf > 1 else None)
    if nf == 1:
        rotation = None
    with _w.catch_warnings():
        _w.simplefilter("ignore")
        fa = FactorAnalyzer(n_factors=nf, rotation=rotation, method=method)
        fa.fit(data.to_numpy())
    L = fa.loadings_
    names = [f"F{j + 1}" for j in range(nf)]
    ss, prop, cum = fa.get_factor_variance()
    var_rows = [{"factor": names[j], "ss_loadings": ss[j], "proportion": 100 * prop[j], "cumulative": 100 * cum[j]} for j in range(nf)]
    eig_rows = [{"factor": i + 1, "eigenvalue": float(e), "parallel_95": float(p_), "retain_pa": bool(e > p_),
                 "pct_variance": 100 * e / len(eig)} for i, (e, p_) in enumerate(zip(eig, pa))]
    tables = [
        table("eigen", "Eigenvalues and parallel analysis", "الجذور الكامنة والتحليل الموازي",
              [col("factor", "Factor", "العامل"), col("eigenvalue", "Eigenvalue", "الجذر الكامن", "3"), col("pct_variance", "% variance", "% التباين", "2"),
               col("parallel_95", "Random 95th pct", "المئين 95 العشوائي", "3"), col("retain_pa", "Retain (PA)", "يُستبقى (PA)")], eig_rows,
              f"Parallel analysis suggests {n_pa} factor(s); Kaiser criterion suggests {n_kaiser}. Extracted: {nf}.",
              f"يقترح التحليل الموازي {n_pa} عامل/عوامل؛ ومعيار كايزر {n_kaiser}. عدد العوامل المستخرجة: {nf}."),
        _loading_table(L, data.columns, names, fa.get_communalities(), f"Factor loadings ({method}, {rotation or 'unrotated'})",
                       f"تشبعات العوامل ({method}، {rotation or 'دون تدوير'})"),
        table("variance", "Variance explained", "التباين المفسر",
              [col("factor", "Factor", "العامل"), col("ss_loadings", "SS loadings", "مجموع مربعات التشبعات", "3"),
               col("proportion", "% variance", "% التباين", "2"), col("cumulative", "Cumulative %", "% التراكمي", "2")], var_rows),
    ]
    if rotation in ("oblimin", "promax", "quartimin", "geomin_obl") and getattr(fa, "phi_", None) is not None:
        phi = pd.DataFrame(fa.phi_, index=names, columns=names)
        tables.append(table("phi", "Factor correlations", "الارتباطات بين العوامل", [col("factor", "", "")] + [col(n, n, n, "3") for n in names],
                            [{"factor": i, **{c: phi.loc[i, c] for c in names}} for i in names]))
    return result("efa", "Exploratory factor analysis", "التحليل العاملي الاستكشافي", params={**params, "n_factors": nf, "rotation": rotation, "method": method},
                  n=len(data), tables=tables, charts=[_scree(eig, pa), _loading_chart(L, data.columns, names)], assumptions=asum,
                  stats={**info, "n_factors": nf, "n_parallel": n_pa, "n_kaiser": n_kaiser, "variance": var_rows,
                         "loadings": {it: dict(zip(names, map(float, L[i]))) for i, it in enumerate(data.columns)}},
                  warnings=[warn("EFA is exploratory; confirm the structure with CFA on an independent sample where possible.",
                                 "التحليل العاملي الاستكشافي ذو طبيعة استكشافية؛ ويُفضل تأكيد البنية بتحليل توكيدي على عينة مستقلة.")],
                  nature="exploratory")


def run_pca(df: pd.DataFrame, params: dict, ctx: dict) -> dict:
    items = params.get("items") or [v["name"] for v in ctx["dictionary"]["variables"] if v.get("is_likert")]
    data = _prep(df, items)
    asum, info, eig, pa = _common(data)
    R = np.corrcoef(data.to_numpy(), rowvar=False)
    vals, vecs = np.linalg.eigh(R)
    order = np.argsort(vals)[::-1]
    vals, vecs = vals[order], vecs[:, order]
    n_pa = int(np.sum(eig > pa)) or 1
    nc = min(int(params.get("n_components") or n_pa), data.shape[1])
    L = vecs[:, :nc] * np.sqrt(vals[:nc])
    L = L * np.sign(L.sum(axis=0))
    rotation = params.get("rotation", "varimax" if nc > 1 else None)
    if rotation and nc > 1:
        L = Rotator(method=rotation).fit_transform(L)
    names = [f"PC{j + 1}" for j in range(nc)]
    comm = (L ** 2).sum(axis=1)
    rows = [{"component": i + 1, "eigenvalue": float(e), "pct_variance": 100 * e / len(vals), "cumulative": 100 * vals[:i + 1].sum() / len(vals)}
            for i, e in enumerate(vals)]
    tables = [table("pca_var", "Total variance explained", "إجمالي التباين المفسر",
                    [col("component", "Component", "المكون"), col("eigenvalue", "Eigenvalue", "الجذر الكامن", "3"),
                     col("pct_variance", "% variance", "% التباين", "2"), col("cumulative", "Cumulative %", "% التراكمي", "2")], rows),
              _loading_table(L, data.columns, names, comm, f"Component loadings ({rotation or 'unrotated'})", f"تشبعات المكونات ({rotation or 'دون تدوير'})")]
    return result("pca", "Principal component analysis", "تحليل المكونات الرئيسية", params={**params, "n_components": nc}, n=len(data),
                  tables=tables, charts=[_scree(eig, pa, "pca_scree"), _loading_chart(L, data.columns, names)], assumptions=asum,
                  stats={**info, "n_components": nc, "eigenvalues": list(map(float, vals))},
                  warnings=[warn("PCA is a data-reduction technique, not a latent-variable model; it is not a substitute for CFA.",
                                 "تحليل المكونات الرئيسية أسلوب لاختزال البيانات وليس نموذجاً للمتغيرات الكامنة، ولا يغني عن التحليل التوكيدي.")],
                  nature="exploratory")


# --------------------------------------------------------------------------------------------
# CFA / SEM
# --------------------------------------------------------------------------------------------


def measurement_syntax(items_by_dim: dict[str, list[str]]) -> str:
    return "\n".join(f"{_safe(f)} =~ " + " + ".join(_safe(i) for i in its) for f, its in items_by_dim.items())


def _srmr(model, data: pd.DataFrame) -> float:
    sigma, _ = model.calc_sigma()
    obs = model.vars["observed"]
    S = data[obs].cov().to_numpy()
    sd = np.sqrt(np.diag(S))
    resid = (S - sigma) / np.outer(sd, sd)
    idx = np.tril_indices(len(obs))
    return float(np.sqrt(np.mean(resid[idx] ** 2)))


def fit_cfa(data: pd.DataFrame, syntax: str) -> dict:
    import semopy
    rename = {c: _safe(c) for c in data.columns}
    inverse = {v: k for k, v in rename.items()}
    d = data.rename(columns=rename)
    d = d.loc[:, ~d.columns.duplicated()]
    try:
        model = semopy.Model(syntax)
        with _w.catch_warnings():
            _w.simplefilter("ignore")
            model.fit(d, obj="MLW")
            st = semopy.calc_stats(model).T.iloc[:, 0].to_dict()
            est = model.inspect(std_est=True)
    except Exception as exc:  # noqa: BLE001
        raise AnalysisError(f"Model could not be estimated: {exc}", f"تعذر تقدير النموذج: {exc}") from exc
    lat_set = set(model.vars["latent"])
    latents = [v for v in dict.fromkeys(re.findall(r"^\s*(\S+)\s*=~", syntax, flags=re.M)) if v in lat_set]
    latents += sorted(lat_set - set(latents))
    load = est[(est["op"] == "~") & est["rval"].isin(latents) & ~est["lval"].isin(latents)]
    loadings = [{"factor": inverse.get(r["rval"], r["rval"]), "item": inverse.get(r["lval"], r["lval"]), "estimate": r["Estimate"],
                 "std_loading": r["Est. Std"], "se": _num(r.get("Std. Err")), "z": _num(r.get("z-value")), "p": _num(r.get("p-value"))}
                for _, r in load.iterrows()]
    paths = est[(est["op"] == "~") & est["rval"].isin(list(model.vars["observed"]) + latents) & est["lval"].isin(latents)]
    structural = [{"dv": inverse.get(r["lval"], r["lval"]), "iv": inverse.get(r["rval"], r["rval"]), "estimate": r["Estimate"],
                   "std": r["Est. Std"], "se": _num(r.get("Std. Err")), "z": _num(r.get("z-value")), "p": _num(r.get("p-value"))}
                  for _, r in paths.iterrows()]
    # semopy encodes the measurement part as "item ~ factor"; structural regressions also as "~".
    cov = est[(est["op"] == "~~") & est["lval"].isin(latents) & est["rval"].isin(latents) & (est["lval"] != est["rval"])]
    names = [inverse.get(l, l) for l in latents]
    M = np.eye(len(latents))
    for _, r in cov.iterrows():
        i, j = latents.index(r["lval"]), latents.index(r["rval"])
        M[i, j] = M[j, i] = r["Est. Std"]
    cfi = st.get("CFI")
    cfi = None if cfi is None else float(min(1.0, max(0.0, cfi)))  # CFI is bounded to [0, 1] by definition
    fit = {"chi2": st.get("chi2"), "df": st.get("DoF"), "p": st.get("chi2 p-value"), "cfi": cfi, "tli": st.get("TLI"),
           "rmsea": st.get("RMSEA"), "srmr": _srmr(model, d), "gfi": st.get("GFI"), "agfi": st.get("AGFI"), "nfi": st.get("NFI"),
           "aic": st.get("AIC"), "bic": st.get("BIC"), "n": len(d)}
    return to_jsonable({"fit": fit, "loadings": loadings, "structural": structural,
                        "factor_corr": {"names": names, "matrix": M.tolist()} if len(latents) > 1 else None, "syntax": syntax})


def _num(v):
    try:
        f = float(v)
        return None if np.isnan(f) else f
    except (TypeError, ValueError):
        return None


def fit_assessment(fit: dict) -> list[dict]:
    """Hu & Bentler (1999) cut-offs, shown as guidelines rather than strict rules."""
    def a(name, ok, en, ar, val):
        return assumption(name, name, name, ok, en, ar, val)
    out = []
    if fit.get("cfi") is not None:
        out.append(a("CFI", fit["cfi"] >= 0.95, f"CFI = {fit['cfi']:.3f} (≥ .95 good, ≥ .90 acceptable)", f"CFI = {fit['cfi']:.3f} (≥ .95 جيد، ≥ .90 مقبول)", fit["cfi"]))
    if fit.get("tli") is not None:
        out.append(a("TLI", fit["tli"] >= 0.95, f"TLI = {fit['tli']:.3f} (≥ .95 good, ≥ .90 acceptable)", f"TLI = {fit['tli']:.3f} (≥ .95 جيد، ≥ .90 مقبول)", fit["tli"]))
    if fit.get("rmsea") is not None:
        out.append(a("RMSEA", fit["rmsea"] <= 0.06, f"RMSEA = {fit['rmsea']:.3f} (≤ .06 good, ≤ .08 acceptable)", f"RMSEA = {fit['rmsea']:.3f} (≤ .06 جيد، ≤ .08 مقبول)", fit["rmsea"]))
    if fit.get("srmr") is not None:
        out.append(a("SRMR", fit["srmr"] <= 0.08, f"SRMR = {fit['srmr']:.3f} (≤ .08 good)", f"SRMR = {fit['srmr']:.3f} (≤ .08 جيد)", fit["srmr"]))
    return out


FIT_COLS = [col("chi2", "χ²", "χ²", "2"), col("df", "df", "درجات الحرية", "0"), col("p", "p", "p", "p"), col("cfi", "CFI", "CFI", "3"),
            col("tli", "TLI", "TLI", "3"), col("rmsea", "RMSEA", "RMSEA", "3"), col("srmr", "SRMR", "SRMR", "3"),
            col("gfi", "GFI", "GFI", "3"), col("aic", "AIC", "AIC", "1"), col("bic", "BIC", "BIC", "1"), col("n", "N", "العدد", "0")]


def run_cfa(df: pd.DataFrame, params: dict, ctx: dict) -> dict:
    syntax = (params.get("syntax") or "").strip()
    if syntax:
        names = set(re.findall(r"[^\s=~+*]+", syntax.replace("=~", " ").replace("~~", " ").replace("~", " ")))
        cols = [c for c in df.columns if _safe(c) in names]
        source_en, source_ar = "custom model syntax supplied by the researcher", "صيغة نموذج مخصصة أدخلها الباحث"
    else:
        dims = [dm for dm in ctx["dictionary"].get("dimensions", []) if not params.get("dimensions") or dm["name"] in params["dimensions"]]
        items_by_dim = {dm["name"]: [i for i in dm["items"] if i in df.columns] for dm in dims}
        items_by_dim = {k: v for k, v in items_by_dim.items() if len(v) >= 2}
        if not items_by_dim:
            raise AnalysisError("CFA needs a pre-specified measurement model: confirm dimensions (≥ 2 items each) or enter model syntax.",
                                "يتطلب التحليل التوكيدي نموذج قياس محدداً مسبقاً: أكّد الأبعاد (بندان على الأقل لكل بعد) أو أدخل صيغة النموذج.")
        if len(items_by_dim) == 1 and len(next(iter(items_by_dim.values()))) < 3:
            raise AnalysisError("A single-factor CFA needs at least 3 items to be identified.", "يتطلب نموذج العامل الواحد 3 بنود على الأقل ليكون معرَّفاً.")
        syntax = measurement_syntax(items_by_dim)
        cols = [i for v in items_by_dim.values() for i in v]
        source_en, source_ar = "confirmed questionnaire dimensions", "أبعاد الاستبانة المؤكدة"
    data = df[cols].apply(pd.to_numeric, errors="coerce").dropna()
    if len(data) < max(50, len(cols) * 3):
        raise AnalysisError(f"CFA needs more complete cases (have {len(data)}).", f"يحتاج التحليل التوكيدي إلى حالات مكتملة أكثر (المتاح {len(data)}).")
    res = fit_cfa(data, syntax)
    kind = params.get("_kind", "cfa")
    tables = [table("fit", "Model fit", "مؤشرات جودة المطابقة", FIT_COLS, [res["fit"]],
                    "ML estimation (semopy, Wishart likelihood). Guideline cut-offs: CFI/TLI ≥ .95, RMSEA ≤ .06, SRMR ≤ .08 (Hu & Bentler, 1999). χ² is sensitive to large samples.",
                    "التقدير بالاحتمال الأقصى (semopy). معايير استرشادية: CFI/TLI ≥ .95، RMSEA ≤ .06، SRMR ≤ .08 (Hu & Bentler, 1999). اختبار χ² حساس للعينات الكبيرة."),
              table("cfa_loadings", "Factor loadings", "التشبعات",
                    [col("factor", "Factor", "العامل"), col("item", "Indicator", "المؤشر"), col("estimate", "Unstd.", "غير معياري", "3"),
                     col("std_loading", "Std. λ", "التشبع المعياري", "3"), col("se", "SE", "الخطأ المعياري", "3"), col("z", "z", "z", "2"),
                     col("p", "p", "p", "p")], res["loadings"], "One loading per factor fixed to 1 for identification (no SE).",
                    "يُثبت تشبع واحد لكل عامل عند 1 لأغراض التعريف (دون خطأ معياري).")]
    if res["structural"]:
        tables.append(table("paths", "Structural paths", "المسارات البنائية",
                            [col("dv", "Outcome", "التابع"), col("iv", "Predictor", "المستقل"), col("estimate", "B", "B", "3"), col("std", "β", "β", "3"),
                             col("se", "SE", "الخطأ المعياري", "3"), col("z", "z", "z", "2"), col("p", "p", "p", "p")], res["structural"]))
    if res.get("factor_corr"):
        fc = res["factor_corr"]
        tables.append(table("factor_corr", "Latent correlations", "الارتباطات بين العوامل الكامنة",
                            [col("factor", "", "")] + [col(n, n, n, "3") for n in fc["names"]],
                            [{"factor": n, **{m: fc["matrix"][i][j] for j, m in enumerate(fc["names"])}} for i, n in enumerate(fc["names"])]))
    title = ("Structural equation model", "نمذجة المعادلات البنائية") if kind == "sem" else ("Confirmatory factor analysis", "التحليل العاملي التوكيدي")
    return result(kind, title[0], title[1], params={**params, "syntax": syntax}, n=len(data), tables=tables,
                  assumptions=fit_assessment(res["fit"]), stats=res, nature="confirmatory",
                  warnings=[warn(f"Model specified from {source_en}. Item-level Likert data treated as continuous (ML); with < 5 categories or strong non-normality consider WLSMV/robust estimation in specialised software.",
                                 f"النموذج محدد من {source_ar}. عوملت بنود ليكرت كبيانات متصلة (ML)؛ ومع أقل من 5 فئات أو انحراف كبير عن الاعتدالية يُنصح بتقديرات متينة (WLSMV) في برمجيات متخصصة.")])


def run_sem(df: pd.DataFrame, params: dict, ctx: dict) -> dict:
    if not (params.get("syntax") or "").strip():
        raise AnalysisError("SEM requires model syntax (measurement '=~' and structural '~' lines).",
                            "تتطلب نمذجة المعادلات البنائية إدخال صيغة النموذج (أسطر القياس '=~' والأسطر البنائية '~').")
    return run_cfa(df, {**params, "_kind": "sem"}, ctx)


def run_multigroup_cfa(df: pd.DataFrame, params: dict, ctx: dict) -> dict:
    group = params.get("group")
    if not group:
        raise AnalysisError("Select a grouping variable.", "اختر متغير التجميع.")
    rows, warns = [], []
    for g, sub in df.groupby(group, observed=True):
        try:
            r = run_cfa(sub, {k: v for k, v in params.items() if k != "group"}, ctx)
            rows.append({"group": str(g), **r["stats"]["fit"]})
        except AnalysisError as e:
            warns.append(warn(f"Group {g}: {e.en}", f"المجموعة {g}: {e.ar}"))
    if not rows:
        raise AnalysisError("The model could not be estimated in any group.", "تعذر تقدير النموذج في أي مجموعة.")
    return result("multigroup", "Multi-group CFA (configural, per group)", "التحليل التوكيدي متعدد المجموعات (الشكلي، لكل مجموعة)",
                  params=params, n=len(df), tables=[table("mg_fit", "Fit by group", "المطابقة لكل مجموعة", [col("group", "Group", "المجموعة")] + FIT_COLS, rows)],
                  stats={"groups": rows}, nature="confirmatory",
                  warnings=warns + [warn("This compares configural fit across groups estimated separately. Metric/scalar invariance (equality-constrained models) is not tested here.",
                                         "يقارن هذا التحليل المطابقة الشكلية بين مجموعات مقدرة منفصلة، ولا يختبر التكافؤ القياسي (المتري/العددي).")])
