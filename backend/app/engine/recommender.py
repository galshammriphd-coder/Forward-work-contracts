"""Statistical test selection engine.

Given the research question's variables and purpose, it identifies the IV/DV, their
measurement levels, the number of groups, checks the relevant assumptions on the
actual data, then recommends a test with its rationale and alternatives. The test is
only executed after the researcher approves it.
"""
from __future__ import annotations

import pandas as pd
from scipy import stats

from .descriptive import normality
from .utils import AnalysisError, fp, to_jsonable

PURPOSES = {
    "difference": ("Compare groups", "مقارنة مجموعات"),
    "relationship": ("Relationship between variables", "العلاقة بين متغيرات"),
    "prediction": ("Predict an outcome", "التنبؤ بمتغير"),
    "association": ("Association between categorical variables", "الارتباط بين متغيرات فئوية"),
    "repeated": ("Compare related measures (same participants)", "مقارنة قياسات مترابطة لنفس المشاركين"),
    "mediation": ("Mediation (indirect effect)", "الوساطة (التأثير غير المباشر)"),
    "moderation": ("Moderation (interaction)", "التعديل (التفاعل)"),
    "multivariate": ("Groups on several DVs", "مقارنة مجموعات على عدة متغيرات تابعة"),
}


def _level(ctx, v):
    var = ctx["var"](v)
    if ctx["is_composite"](v):
        return "interval"
    return var.get("level", "nominal")


def _kind(ctx, v):
    lvl = _level(ctx, v)
    if lvl in ("interval", "ratio"):
        return "continuous"
    if lvl == "ordinal":
        # single Likert items or ordered codes with few levels
        return "ordinal" if ctx["n_unique"](v) <= 11 else "continuous"
    return "categorical"


def _rec(kind, params, en, ar, title_en, title_ar):
    return {"analysis": kind, "params": params, "title_en": title_en, "title_ar": title_ar, "reason_en": en, "reason_ar": ar}


def recommend(df: pd.DataFrame, req: dict, ctx: dict) -> dict:
    purpose = req.get("purpose")
    dv, ivs = req.get("dv"), req.get("ivs") or ([req["iv"]] if req.get("iv") else [])
    checks, alts = [], []
    ident = {"purpose": purpose, "dv": dv, "ivs": ivs}
    if dv:
        ident["dv_level"] = _level(ctx, dv)
        ident["dv_kind"] = _kind(ctx, dv)
    ident["iv_levels"] = {v: _level(ctx, v) for v in ivs}

    def chk(name_en, name_ar, ok, en, ar):
        checks.append({"name_en": name_en, "name_ar": name_ar, "met": ok, "detail_en": en, "detail_ar": ar})

    if purpose == "difference":
        if not dv or len(ivs) < 1:
            raise AnalysisError("Choose the outcome (DV) and the grouping variable (IV).", "اختر المتغير التابع ومتغير التجميع (المستقل).")
        if len(ivs) == 2:
            rec = _rec("anova_twoway", {"dv": dv, "factor_a": ivs[0], "factor_b": ivs[1]},
                       "Two categorical factors and one continuous outcome: two-way ANOVA tests both main effects and their interaction.",
                       "عاملان فئويان ومتغير تابع متصل: يختبر تحليل التباين الثنائي التأثيرين الرئيسيين والتفاعل بينهما.", "Two-way ANOVA", "تحليل التباين الثنائي")
            return to_jsonable({"identified": ident, "checks": checks, "recommended": rec, "alternatives": alts})
        g = ivs[0]
        d = pd.DataFrame({"y": pd.to_numeric(df[dv], errors="coerce"), "g": df[g]}).dropna()
        groups = d["g"].astype(str).value_counts()
        k = len(groups)
        ident.update({"groups": int(k), "group_sizes": groups.to_dict(), "n": len(d)})
        if k < 2:
            raise AnalysisError("The grouping variable has fewer than 2 groups in the data.", "متغير التجميع يحتوي أقل من مجموعتين في البيانات.")
        if k > 10:
            chk("Grouping variable", "متغير التجميع", False, f"{k} distinct values — is this really a grouping variable?", f"{k} قيمة مختلفة — هل هذا متغير تجميع فعلاً؟")
        dvk = _kind(ctx, dv)
        normal_all = True
        for name, sub in d.groupby(d["g"].astype(str)):
            r = normality(sub["y"])
            if "error" in r:
                continue
            normal_all &= r["approximately_normal"]
            chk(f"Normality in group {name}", f"الاعتدالية في المجموعة {name}", r["approximately_normal"],
                f"n = {r['n']}; skew = {r['skewness']:.2f}; " + (f"S–W p {fp(r['shapiro_p'])}" if r.get("shapiro_p") is not None else ""),
                f"n = {r['n']}؛ الالتواء = {r['skewness']:.2f}؛ " + (f"ش–و p {fp(r['shapiro_p'])}" if r.get("shapiro_p") is not None else ""))
        samples = [sub["y"].to_numpy() for _, sub in d.groupby(d["g"].astype(str))]
        lev = stats.levene(*samples, center="mean")
        eq = lev.pvalue >= 0.05
        chk("Homogeneity of variance", "تجانس التباين", eq, f"Levene F = {lev.statistic:.2f}, p {fp(lev.pvalue)}", f"ليفين F = {lev.statistic:.2f}، p {fp(lev.pvalue)}")
        min_n = int(groups.min())
        clt = min_n >= 30
        if clt and not normal_all:
            chk("Large groups (CLT)", "مجموعات كبيرة (نظرية النهاية المركزية)", True, f"smallest group n = {min_n} ≥ 30: t/F tests are robust to moderate non-normality",
                f"أصغر مجموعة n = {min_n} ≥ 30: اختبارات t/F متينة أمام الانحراف المعتدل عن الاعتدالية")
        parametric = dvk == "continuous" and (normal_all or clt)
        if dvk == "ordinal":
            chk("Measurement level", "مستوى القياس", False, "DV is ordinal (single Likert item): rank-based test preferred", "المتغير التابع رتبي (بند ليكرت مفرد): يُفضّل اختبار رتبي")
        if k == 2:
            if parametric:
                rec = _rec("ttest_ind", {"dv": dv, "group": g},
                           f"Two independent groups, continuous outcome, assumptions acceptable. {'Student' if eq else 'Welch'}'s t-test will be reported (Levene).",
                           f"مجموعتان مستقلتان ومتغير تابع متصل والافتراضات مقبولة. سيُعتمد اختبار {'ستيودنت' if eq else 'ويلش'} (بناءً على ليفين).",
                           "Independent-samples t-test", "اختبار (ت) لعينتين مستقلتين")
                alts.append(_rec("mannwhitney", {"dv": dv, "group": g}, "Non-parametric alternative (robust to outliers/non-normality).", "بديل لامعلمي (متين أمام القيم المتطرفة وعدم الاعتدالية).", "Mann–Whitney U", "مان–ويتني"))
            else:
                rec = _rec("mannwhitney", {"dv": dv, "group": g}, "Two independent groups; outcome is ordinal or normality is doubtful with small groups → Mann–Whitney U.",
                           "مجموعتان مستقلتان؛ المتغير التابع رتبي أو الاعتدالية موضع شك مع مجموعات صغيرة ← اختبار مان–ويتني.", "Mann–Whitney U test", "اختبار مان–ويتني")
                alts.append(_rec("ttest_ind", {"dv": dv, "group": g}, "Parametric alternative (Welch) if the mean is the parameter of interest.", "البديل المعلمي (ويلش) إذا كان المتوسط هو موضع الاهتمام.", "Welch's t-test", "اختبار ويلش"))
        else:
            if parametric:
                rec = _rec("anova", {"dv": dv, "group": g, "posthoc": "tukey" if eq else "games_howell"},
                           f"{k} independent groups, continuous outcome. " + ("Variances equal → classic ANOVA + Tukey HSD." if eq else "Variances unequal → Welch's ANOVA + Games–Howell."),
                           f"{k} مجموعات مستقلة ومتغير تابع متصل. " + ("التباين متجانس ← تحليل التباين التقليدي + توكي." if eq else "التباين غير متجانس ← تحليل ويلش + جيمس–هاول."),
                           "One-way ANOVA" if eq else "Welch's ANOVA", "تحليل التباين الأحادي" if eq else "تحليل ويلش للتباين")
                alts.append(_rec("kruskal", {"dv": dv, "group": g}, "Rank-based alternative.", "البديل الرتبي.", "Kruskal–Wallis", "كروسكال–واليس"))
            else:
                rec = _rec("kruskal", {"dv": dv, "group": g}, f"{k} independent groups; ordinal outcome or doubtful normality → Kruskal–Wallis with Dunn post-hoc.",
                           f"{k} مجموعات مستقلة؛ متغير تابع رتبي أو اعتدالية موضع شك ← كروسكال–واليس مع مقارنات دن.", "Kruskal–Wallis H test", "اختبار كروسكال–واليس")
                alts.append(_rec("anova", {"dv": dv, "group": g}, "Parametric alternative (Welch's ANOVA if variances differ).", "البديل المعلمي.", "One-way ANOVA", "تحليل التباين الأحادي"))
    elif purpose == "relationship":
        vars_ = ([dv] if dv else []) + ivs
        if len(vars_) < 2:
            raise AnalysisError("Choose at least two variables.", "اختر متغيرين على الأقل.")
        kinds = {v: _kind(ctx, v) for v in vars_}
        if all(k_ == "categorical" for k_ in kinds.values()) and len(vars_) == 2:
            return recommend(df, {**req, "purpose": "association", "dv": vars_[0], "ivs": [vars_[1]]}, ctx)
        normal = True
        for v in vars_:
            r = normality(df[v])
            if "error" in r:
                continue
            normal &= r["approximately_normal"]
            chk(f"Normality ({v})", f"الاعتدالية ({v})", r["approximately_normal"], r["basis_en"], r["basis_ar"])
        any_ord = any(k_ == "ordinal" for k_ in kinds.values())
        if any_ord:
            chk("Measurement level", "مستوى القياس", False, "At least one variable is ordinal", "متغير واحد على الأقل رتبي")
        if not any_ord and normal:
            rec = _rec("correlation", {"variables": vars_, "method": "pearson"}, "Continuous variables, approximately normal: Pearson's r (linear association).",
                       "متغيرات متصلة قريبة من الاعتدالية: معامل ارتباط بيرسون (علاقة خطية).", "Pearson correlation", "ارتباط بيرسون")
            alts.append(_rec("correlation", {"variables": vars_, "method": "spearman"}, "Rank-based alternative for monotonic relationships.", "بديل رتبي للعلاقات الرتيبة.", "Spearman's rho", "سبيرمان"))
        else:
            rec = _rec("correlation", {"variables": vars_, "method": "spearman"}, "Ordinal data or non-normal distributions: Spearman's rank correlation.",
                       "بيانات رتبية أو توزيعات غير اعتدالية: ارتباط سبيرمان للرتب.", "Spearman correlation", "ارتباط سبيرمان")
            alts.append(_rec("correlation", {"variables": vars_, "method": "kendall"}, "Kendall's τb: preferable with many ties / small samples.", "كندال τb: مفضل مع كثرة الرتب المتساوية أو صغر العينة.", "Kendall's tau-b", "كندال"))
            alts.append(_rec("correlation", {"variables": vars_, "method": "pearson"}, "Pearson (if linearity holds and n is large).", "بيرسون (إن تحققت الخطية وكانت العينة كبيرة).", "Pearson", "بيرسون"))
        if len(vars_) > 2:
            chk("Multiple testing", "تعدد الاختبارات", None, "Several correlations: consider Holm adjustment", "عدة ارتباطات: يُنصح بتصحيح هولم")
            rec["params"]["adjust"] = "holm"
    elif purpose == "prediction":
        if not dv or not ivs:
            raise AnalysisError("Choose the outcome and at least one predictor.", "اختر المتغير التابع ومتنبئاً واحداً على الأقل.")
        dvk = _kind(ctx, dv)
        nlev = ctx["n_unique"](dv)
        n = len(df[[dv] + ivs].dropna())
        ident["n"] = n
        chk("Cases per predictor", "عدد الحالات لكل متنبئ", n >= 10 * len(ivs) + 50 if dvk == "continuous" else n >= 10 * len(ivs),
            f"n = {n} for {len(ivs)} predictor(s) (guideline: N ≥ 50 + 8m, Green 1991)", f"n = {n} لعدد {len(ivs)} متنبئ (القاعدة: N ≥ 50 + 8m، Green 1991)")
        if dvk == "continuous":
            rec = _rec("linear", {"dv": dv, "ivs": ivs}, "Continuous outcome: OLS linear regression with residual diagnostics (normality, homoscedasticity, VIF, Cook's D).",
                       "متغير تابع متصل: انحدار خطي بالمربعات الصغرى مع تشخيص البواقي (الاعتدالية، تجانس التباين، VIF، مسافة كوك).",
                       "Simple linear regression" if len(ivs) == 1 else "Multiple linear regression", "الانحدار الخطي البسيط" if len(ivs) == 1 else "الانحدار الخطي المتعدد")
            if len(ivs) >= 2:
                alts.append(_rec("hierarchical", {"dv": dv, "blocks": [ivs[:1], ivs[1:]]}, "Enter predictors in theory-driven blocks to test ΔR².", "إدخال المتنبئات في كتل نظرية لاختبار ΔR².", "Hierarchical regression", "الانحدار الهرمي"))
        elif nlev == 2:
            rec = _rec("logistic", {"dv": dv, "ivs": ivs}, "Binary outcome: binary logistic regression (odds ratios).", "متغير تابع ثنائي: الانحدار اللوجستي الثنائي (نسب الأرجحية).",
                       "Binary logistic regression", "الانحدار اللوجستي الثنائي")
        elif dvk == "ordinal":
            rec = _rec("ordinal", {"dv": dv, "ivs": ivs}, "Ordered categorical outcome: proportional-odds ordinal logistic regression.",
                       "متغير تابع رتبي: الانحدار اللوجستي الرتبي (الأرجحيات التناسبية).", "Ordinal logistic regression", "الانحدار اللوجستي الرتبي")
            alts.append(_rec("linear", {"dv": dv, "ivs": ivs}, "Linear regression treating the outcome as interval (only with ≥ 5–7 categories).",
                             "انحدار خطي بمعاملة التابع كفتري (فقط مع 5–7 فئات فأكثر).", "Linear regression", "الانحدار الخطي"))
        else:
            rec = _rec("discriminant", {"group": dv, "predictors": ivs}, "Nominal outcome with > 2 categories: discriminant analysis (or multinomial logistic regression).",
                       "متغير تابع اسمي بأكثر من فئتين: التحليل التمييزي (أو الانحدار اللوجستي متعدد الحدود).", "Discriminant analysis", "التحليل التمييزي")
    elif purpose == "association":
        a, b = dv, ivs[0] if ivs else None
        if not a or not b:
            raise AnalysisError("Choose two categorical variables.", "اختر متغيرين فئويين.")
        ct = pd.crosstab(df[a].dropna().astype(str), df[b].dropna().astype(str))
        if ct.size:
            exp = stats.contingency.expected_freq(ct)
            low = (exp < 5).mean() * 100
            ok = low <= 20 and exp.min() >= 1
            chk("Expected counts", "التكرارات المتوقعة", ok, f"{low:.0f}% of cells < 5", f"{low:.0f}% من الخلايا < 5")
            if ct.shape == (2, 2) and not ok:
                rec = _rec("fisher", {"var1": a, "var2": b}, "2×2 table with small expected counts: Fisher's exact test.", "جدول 2×2 بتكرارات متوقعة صغيرة: اختبار فيشر الدقيق.", "Fisher's exact test", "اختبار فيشر الدقيق")
            else:
                rec = _rec("chisquare", {"var1": a, "var2": b}, "Two categorical variables: χ² test of independence with Cramér's V.", "متغيران فئويان: اختبار كاي تربيع للاستقلالية مع V كرامر.",
                           "Chi-square test", "اختبار كاي تربيع")
                if not ok:
                    chk("Recommendation", "توصية", False, "Merge sparse categories before interpreting χ²", "ادمج الفئات قليلة التكرار قبل تفسير كاي تربيع")
        else:
            raise AnalysisError("No overlapping data.", "لا توجد بيانات مشتركة.")
    elif purpose == "repeated":
        vars_ = ([dv] if dv else []) + ivs
        if len(vars_) < 2:
            raise AnalysisError("Choose ≥ 2 related measures.", "اختر قياسين مترابطين أو أكثر.")
        d = df[vars_].apply(pd.to_numeric, errors="coerce").dropna()
        normal = True
        if len(vars_) == 2:
            r = normality(d[vars_[0]] - d[vars_[1]])
            normal = r.get("approximately_normal", False)
            chk("Normality of differences", "اعتدالية الفروق", normal, r.get("basis_en", ""), r.get("basis_ar", ""))
            rec = (_rec("ttest_paired", {"var1": vars_[0], "var2": vars_[1]}, "Two related measures, normal differences: paired t-test.", "قياسان مترابطان وفروق اعتدالية: اختبار (ت) للعينات المترابطة.",
                        "Paired-samples t-test", "اختبار (ت) للعينات المترابطة") if normal else
                   _rec("wilcoxon", {"var1": vars_[0], "var2": vars_[1]}, "Two related measures, non-normal differences: Wilcoxon signed-rank.", "قياسان مترابطان وفروق غير اعتدالية: اختبار ويلكوكسون.",
                        "Wilcoxon signed-rank test", "اختبار ويلكوكسون"))
            alts.append(_rec("wilcoxon" if normal else "ttest_paired", {"var1": vars_[0], "var2": vars_[1]}, "Alternative", "بديل", "Alternative", "بديل"))
        else:
            rec = _rec("rm_anova", {"variables": vars_}, "≥ 3 related measures: repeated-measures ANOVA (Mauchly + Greenhouse–Geisser).",
                       "ثلاثة قياسات مترابطة فأكثر: تحليل التباين للقياسات المتكررة (موكلي + جرينهاوس–جيسر).", "Repeated-measures ANOVA", "تحليل التباين للقياسات المتكررة")
            alts.append(_rec("friedman", {"variables": vars_}, "Rank-based alternative.", "البديل الرتبي.", "Friedman test", "اختبار فريدمان"))
    elif purpose == "mediation":
        rec = _rec("mediation", {"x": req.get("iv") or ivs[0], "mediator": req["mediator"], "y": dv}, "Indirect effect X → M → Y with percentile-bootstrap CI.",
                   "التأثير غير المباشر X ← M ← Y بفترة ثقة بالإقلاع.", "Mediation analysis", "تحليل الوساطة")
    elif purpose == "moderation":
        rec = _rec("moderation", {"x": req.get("iv") or ivs[0], "moderator": req["moderator"], "y": dv}, "Interaction X × W on Y (mean-centred) with simple slopes.",
                   "التفاعل X × W على Y (بعد التمركز) مع الميول البسيطة.", "Moderation analysis", "تحليل التعديل")
    elif purpose == "multivariate":
        rec = _rec("manova", {"dvs": req.get("dvs") or [dv], "group": ivs[0]}, "Several correlated continuous DVs compared across groups: MANOVA.",
                   "عدة متغيرات تابعة متصلة مترابطة تقارن عبر مجموعات: تحليل التباين المتعدد.", "MANOVA", "تحليل التباين المتعدد")
    else:
        raise AnalysisError("Unknown purpose.", "غرض غير معروف.")
    return to_jsonable({"identified": ident, "checks": checks, "recommended": rec, "alternatives": alts})
