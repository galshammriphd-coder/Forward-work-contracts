"""Rule-based academic interpretation (APA 7) built strictly from computed values.

No language model is involved and no number is ever invented: every value inserted in
the text is read from the analysis result. If a value is missing, the sentence is omitted.
"""
from __future__ import annotations

from .utils import fnum, fp, fr

LIMITS = {
    "correlational": ("Correlation does not establish causation; unmeasured variables may explain the association.",
                      "الارتباط لا يثبت السببية؛ وقد تفسر متغيرات غير مقيسة هذه العلاقة."),
    "sample": ("Generalisation depends on how the sample was selected; non-probability samples limit inference to similar populations.",
               "يعتمد التعميم على طريقة اختيار العينة؛ والعينات غير الاحتمالية تحد من التعميم إلى مجتمعات مماثلة."),
    "self_report": ("Self-report questionnaire data may be affected by social desirability and common-method bias.",
                    "قد تتأثر بيانات الاستبانة الذاتية بالمرغوبية الاجتماعية وتحيز الطريقة المشتركة."),
    "significance": ("Statistical significance does not by itself indicate practical importance; consider the effect size and CI.",
                     "الدلالة الإحصائية لا تعني بالضرورة أهمية عملية؛ ويجب النظر إلى حجم الأثر وفترة الثقة."),
    "nonsig": ("A non-significant result is not evidence that the effect is zero (absence of evidence ≠ evidence of absence); power may be insufficient.",
               "النتيجة غير الدالة ليست دليلاً على انعدام الأثر؛ فقد تكون القوة الإحصائية غير كافية."),
    "exploratory": ("Exploratory analysis: findings should be confirmed on independent data.", "تحليل استكشافي: ينبغي تأكيد النتائج على بيانات مستقلة."),
}


def _out(en, ar, apa_en, apa_ar, sig=None, effect_en=None, effect_ar=None, limits=()):
    lim = [{"en": LIMITS[k][0], "ar": LIMITS[k][1]} for k in limits]
    return {"summary_en": en, "summary_ar": ar, "apa_en": apa_en, "apa_ar": apa_ar, "significant": sig,
            "effect_en": effect_en, "effect_ar": effect_ar, "limitations": lim}


def interpret(res: dict, alpha: float = 0.05) -> dict:
    k, s = res["kind"], res.get("stats", {})
    fn = globals().get(f"_i_{k}")
    if fn is None:
        return _out(f"{res['title_en']} completed (n = {res.get('n')}). See the tables for the computed values.",
                    f"اكتمل {res['title_ar']} (n = {res.get('n')}). راجع الجداول للاطلاع على القيم المحسوبة.", "", "")
    return fn(res, s, alpha)


def _sig(p, alpha):
    return p is not None and p < alpha


def _i_ttest_ind(res, s, a):
    g = s["groups"]
    g1, g2 = g[0], g[1]
    sig = _sig(s["p"], a)
    t = f"t({fnum(s['df'], 2 if s['test_used'] == 'Welch' else 0)}) = {fnum(s['t'])}"
    ci = f"95% CI [{fnum(s['ci_low'])}, {fnum(s['ci_high'])}]"
    apa_en = (f"An independent-samples {'Welch ' if s['test_used'] == 'Welch' else ''}t-test showed that {s['dv']} "
              f"{'differed significantly' if sig else 'did not differ significantly'} between {g1['group']} (M = {fnum(g1['mean'])}, SD = {fnum(g1['sd'])}) "
              f"and {g2['group']} (M = {fnum(g2['mean'])}, SD = {fnum(g2['sd'])}), {t}, p {fp(s['p'])}, mean difference = {fnum(s['mean_diff'])}, {ci}, "
              f"Cohen's d = {fnum(s['cohens_d'])} ({s['effect_label_en']} effect).")
    apa_ar = (f"أظهرت نتائج اختبار (ت) لعينتين مستقلتين{' (تصحيح ويلش)' if s['test_used'] == 'Welch' else ''} "
              f"{'وجود فروق ذات دلالة إحصائية' if sig else 'عدم وجود فروق ذات دلالة إحصائية'} في {s['dv']} بين {g1['group']} (م = {fnum(g1['mean'])}، ع = {fnum(g1['sd'])}) "
              f"و{g2['group']} (م = {fnum(g2['mean'])}، ع = {fnum(g2['sd'])})، {t}، p {fp(s['p'])}، وبلغ فرق المتوسطين {fnum(s['mean_diff'])}، {ci}، "
              f"وحجم الأثر d كوهين = {fnum(s['cohens_d'])} (أثر {s['effect_label_ar']}).")
    return _out(apa_en, apa_ar, apa_en, apa_ar, sig, f"d = {fnum(s['cohens_d'])} ({s['effect_label_en']})", f"d = {fnum(s['cohens_d'])} ({s['effect_label_ar']})",
                ("significance" if sig else "nonsig", "sample"))


def _i_mannwhitney(res, s, a):
    g = s["groups"]
    sig = _sig(s["p"], a)
    en = (f"A Mann–Whitney U test indicated that {s['dv']} was {'significantly' if sig else 'not significantly'} different between {g[0]['group']} (Mdn = {fnum(g[0]['median'])}, mean rank = {fnum(g[0]['mean_rank'])}) "
          f"and {g[1]['group']} (Mdn = {fnum(g[1]['median'])}, mean rank = {fnum(g[1]['mean_rank'])}), U = {fnum(s['U'], 1)}, z = {fnum(s['z'])}, p {fp(s['p'])}, r = {fr(s['r'])} ({s['effect_label_en']} effect).")
    ar = (f"أشارت نتائج اختبار مان–ويتني إلى {'وجود' if sig else 'عدم وجود'} فروق دالة إحصائياً في {s['dv']} بين {g[0]['group']} (الوسيط = {fnum(g[0]['median'])}، متوسط الرتب = {fnum(g[0]['mean_rank'])}) "
          f"و{g[1]['group']} (الوسيط = {fnum(g[1]['median'])}، متوسط الرتب = {fnum(g[1]['mean_rank'])})، U = {fnum(s['U'], 1)}، z = {fnum(s['z'])}، p {fp(s['p'])}، r = {fr(s['r'])} (أثر {s['effect_label_ar']}).")
    return _out(en, ar, en, ar, sig, f"r = {fr(s['r'])}", f"r = {fr(s['r'])}", ("significance" if sig else "nonsig",))


def _i_ttest_paired(res, s, a):
    sig = _sig(s["p"], a)
    en = (f"A paired-samples t-test showed a {'significant' if sig else 'non-significant'} difference between {s['var1']} (M = {fnum(s['mean1'])}, SD = {fnum(s['sd1'])}) and {s['var2']} "
          f"(M = {fnum(s['mean2'])}, SD = {fnum(s['sd2'])}), t({fnum(s['df'], 0)}) = {fnum(s['t'])}, p {fp(s['p'])}, mean difference = {fnum(s['mean_diff'])}, "
          f"95% CI [{fnum(s['ci_low'])}, {fnum(s['ci_high'])}], dz = {fnum(s['cohens_dz'])}.")
    ar = (f"أظهر اختبار (ت) للعينات المترابطة {'وجود' if sig else 'عدم وجود'} فرق دال إحصائياً بين {s['var1']} (م = {fnum(s['mean1'])}، ع = {fnum(s['sd1'])}) و{s['var2']} "
          f"(م = {fnum(s['mean2'])}، ع = {fnum(s['sd2'])})، ت({fnum(s['df'], 0)}) = {fnum(s['t'])}، p {fp(s['p'])}، فرق المتوسطين = {fnum(s['mean_diff'])}، "
          f"فترة الثقة 95% [{fnum(s['ci_low'])}، {fnum(s['ci_high'])}]، dz = {fnum(s['cohens_dz'])}.")
    return _out(en, ar, en, ar, sig, f"dz = {fnum(s['cohens_dz'])}", f"dz = {fnum(s['cohens_dz'])}", ("significance" if sig else "nonsig",))


def _i_wilcoxon(res, s, a):
    sig = _sig(s["p"], a)
    en = f"A Wilcoxon signed-rank test indicated a {'significant' if sig else 'non-significant'} difference between {s['var1']} (Mdn = {fnum(s['median1'])}) and {s['var2']} (Mdn = {fnum(s['median2'])}), z = {fnum(s['z'])}, p {fp(s['p'])}, r = {fr(s['r'])}."
    ar = f"أشار اختبار ويلكوكسون إلى {'وجود' if sig else 'عدم وجود'} فرق دال بين {s['var1']} (الوسيط = {fnum(s['median1'])}) و{s['var2']} (الوسيط = {fnum(s['median2'])})، z = {fnum(s['z'])}، p {fp(s['p'])}، r = {fr(s['r'])}."
    return _out(en, ar, en, ar, sig, f"r = {fr(s['r'])}", f"r = {fr(s['r'])}", ("significance" if sig else "nonsig",))


def _i_anova(res, s, a):
    welch = s["test_used"] == "Welch"
    p = s["welch_p"] if welch else s["p"]
    sig = _sig(p, a)
    F = f"F({fnum(s['welch_df1'], 0)}, {fnum(s['welch_df2'], 2)}) = {fnum(s['welch_F'])}" if welch else f"F({fnum(s['df1'], 0)}, {fnum(s['df2'], 0)}) = {fnum(s['F'])}"
    ph_en = ph_ar = ""
    if s.get("posthoc"):
        sig_pairs = [r for r in s["posthoc"] if r["p"] is not None and r["p"] < a]
        meth = {"tukey": "Tukey HSD", "games_howell": "Games–Howell", "bonferroni": "Bonferroni"}.get(s.get("posthoc_method"), "")
        if sig_pairs:
            ph_en = f" {meth} post-hoc comparisons showed significant differences between " + "; ".join(f"{r['A']} and {r['B']} (p {fp(r['p'])})" for r in sig_pairs) + "."
            ph_ar = f" وأظهرت المقارنات البعدية ({meth}) فروقاً دالة بين " + "؛ ".join(f"{r['A']} و{r['B']} (p {fp(r['p'])})" for r in sig_pairs) + "."
        else:
            ph_en, ph_ar = f" No pairwise {meth} comparison reached significance.", f" ولم تصل أي مقارنة ثنائية ({meth}) إلى الدلالة."
    means_en = ", ".join(f"{g['group']} (M = {fnum(g['mean'])}, SD = {fnum(g['sd'])})" for g in s["groups"])
    means_ar = "، ".join(f"{g['group']} (م = {fnum(g['mean'])}، ع = {fnum(g['sd'])})" for g in s["groups"])
    en = (f"A one-way {'Welch ' if welch else ''}ANOVA revealed {'a statistically significant' if sig else 'no statistically significant'} effect of {s['group']} on {s['dv']}, {F}, p {fp(p)}, "
          f"η² = {fr(s['eta2'], 3)}, ω² = {fr(s['omega2'], 3)} ({s['effect_label_en']} effect). Group means: {means_en}.{ph_en}")
    ar = (f"كشفت نتائج تحليل التباين الأحادي{' (ويلش)' if welch else ''} عن {'وجود' if sig else 'عدم وجود'} أثر دال إحصائياً لـ {s['group']} في {s['dv']}، {F}، p {fp(p)}، "
          f"η² = {fr(s['eta2'], 3)}، ω² = {fr(s['omega2'], 3)} (أثر {s['effect_label_ar']}). متوسطات المجموعات: {means_ar}.{ph_ar}")
    return _out(en, ar, en, ar, sig, f"η² = {fr(s['eta2'], 3)}", f"η² = {fr(s['eta2'], 3)}", ("significance" if sig else "nonsig",))


def _i_kruskal(res, s, a):
    sig = _sig(s["p"], a)
    en = f"A Kruskal–Wallis test showed {'a significant' if sig else 'no significant'} difference in {s['dv']} across {s['group']} groups, H({s['df']}) = {fnum(s['H'])}, p {fp(s['p'])}, ε² = {fr(s['epsilon2'], 3)}."
    ar = f"أظهر اختبار كروسكال–واليس {'وجود' if sig else 'عدم وجود'} فروق دالة في {s['dv']} تبعاً لـ {s['group']}، H({s['df']}) = {fnum(s['H'])}، p {fp(s['p'])}، ε² = {fr(s['epsilon2'], 3)}."
    if s.get("posthoc"):
        sp = [r for r in s["posthoc"] if r["p"] < a]
        if sp:
            en += " Dunn's tests (Bonferroni) located differences between " + "; ".join(f"{r['A']}–{r['B']} (p {fp(r['p'])})" for r in sp) + "."
            ar += " وحددت اختبارات دن (بونفيروني) الفروق بين " + "؛ ".join(f"{r['A']}–{r['B']} (p {fp(r['p'])})" for r in sp) + "."
    return _out(en, ar, en, ar, sig, f"ε² = {fr(s['epsilon2'], 3)}", f"ε² = {fr(s['epsilon2'], 3)}", ("significance" if sig else "nonsig",))


def _i_correlation(res, s, a):
    sym = {"pearson": "r", "spearman": "rs", "kendall": "τb"}[s["method"]]
    name_en = {"pearson": "Pearson", "spearman": "Spearman", "kendall": "Kendall"}[s["method"]]
    name_ar = {"pearson": "بيرسون", "spearman": "سبيرمان", "kendall": "كندال"}[s["method"]]
    en_parts, ar_parts, any_sig = [], [], False
    for p in s["pairs"]:
        if p["r"] is None:
            continue
        pv = p.get("p_adj", p["p"])
        sig = _sig(pv, a)
        any_sig |= sig
        direction_en = "positive" if p["r"] > 0 else "negative"
        direction_ar = "موجبة (طردية)" if p["r"] > 0 else "سالبة (عكسية)"
        en_parts.append(f"{p['var1']} and {p['var2']} were {'significantly ' if sig else 'not significantly '}{'' if not sig else direction_en + 'ly '}correlated, "
                        f"{sym}({p['n'] - 2}) = {fr(p['r'])}, 95% CI [{fr(p['ci_low'])}, {fr(p['ci_high'])}], p {fp(pv)}" + (f" ({p['strength_en']})" if sig else "") + ".")
        ar_parts.append(f"{'وُجدت' if sig else 'لم تُوجد'} علاقة ارتباطية {direction_ar if sig else ''} دالة إحصائياً بين {p['var1']} و{p['var2']}، إذ بلغ معامل ارتباط {name_ar} "
                        f"({sym} = {fr(p['r'])})، فترة الثقة 95% [{fr(p['ci_low'])}، {fr(p['ci_high'])}]، بمستوى دلالة (p {fp(pv)})" + (f" (علاقة {p['strength_ar']})" if sig else "") + ".")
    en = f"{name_en} correlation analysis: " + " ".join(en_parts)
    ar = f"تحليل ارتباط {name_ar}: " + " ".join(ar_parts)
    return _out(en, ar, en, ar, any_sig, None, None, ("correlational", "significance" if any_sig else "nonsig"))


def _reg_text(s, kind_en, kind_ar):
    sig_preds_en = "; ".join(f"{c['term']} (B = {fnum(c['B'], 3)}, β = {fr(c['beta'])}, t = {fnum(c['t'])}, p {fp(c['p'])})" for c in s["coefficients"] if c["term"] != "(Intercept)" and c["p"] < 0.05)
    sig_preds_ar = "؛ ".join(f"{c['term']} (B = {fnum(c['B'], 3)}، β = {fr(c['beta'])}، ت = {fnum(c['t'])}، p {fp(c['p'])})" for c in s["coefficients"] if c["term"] != "(Intercept)" and c["p"] < 0.05)
    sig = _sig(s["p"], 0.05)
    en = (f"{kind_en} indicated that the model {'significantly' if sig else 'did not significantly'} predict{'ed' if sig else ''} {s['dv']}, F({fnum(s['df1'], 0)}, {fnum(s['df2'], 0)}) = {fnum(s['F'])}, "
          f"p {fp(s['p'])}, R² = {fr(s['r2'], 3)}, adjusted R² = {fr(s['adj_r2'], 3)} (f² = {fnum(s['f2'], 3)}). "
          + (f"Significant predictors: {sig_preds_en}." if sig_preds_en else "No individual predictor was significant at p < .05."))
    ar = (f"أظهرت نتائج {kind_ar} أن النموذج {'يتنبأ تنبؤاً دالاً إحصائياً' if sig else 'لا يتنبأ تنبؤاً دالاً إحصائياً'} بـ {s['dv']}، ف({fnum(s['df1'], 0)}، {fnum(s['df2'], 0)}) = {fnum(s['F'])}، "
          f"p {fp(s['p'])}، وفسّر النموذج ما نسبته {fnum(100 * s['r2'], 1)}% من التباين (R² = {fr(s['r2'], 3)}، R² المعدل = {fr(s['adj_r2'], 3)}). "
          + (f"المتنبئات الدالة: {sig_preds_ar}." if sig_preds_ar else "لم يكن أي متنبئ منفرد دالاً عند مستوى .05."))
    return _out(en, ar, en, ar, sig, f"R² = {fr(s['r2'], 3)}, f² = {fnum(s['f2'], 3)}", f"R² = {fr(s['r2'], 3)}، f² = {fnum(s['f2'], 3)}",
                ("correlational", "significance" if sig else "nonsig"))


def _i_linear_simple(res, s, a):
    return _reg_text(s, "Simple linear regression", "الانحدار الخطي البسيط")


def _i_linear_multiple(res, s, a):
    return _reg_text(s, "Multiple linear regression", "الانحدار الخطي المتعدد")


def _i_polynomial(res, s, a):
    return _reg_text(s, "Polynomial regression", "الانحدار متعدد الحدود")


def _i_hierarchical(res, s, a):
    parts_en = [f"Step {r['step']} ({r['added']}): R² = {fr(r['r2'], 3)}, ΔR² = {fr(r['delta_r2'], 3)}, F change({fnum(r['df1'], 0)}, {fnum(r['df2'], 0)}) = {fnum(r['F_change'])}, p {fp(r['p_change'])}" for r in s["steps"]]
    parts_ar = [f"الخطوة {r['step']} ({r['added']}): R² = {fr(r['r2'], 3)}، ΔR² = {fr(r['delta_r2'], 3)}، ف للتغير({fnum(r['df1'], 0)}، {fnum(r['df2'], 0)}) = {fnum(r['F_change'])}، p {fp(r['p_change'])}" for r in s["steps"]]
    last = s["steps"][-1]
    sig = _sig(last["p_change"], a)
    en = f"Hierarchical regression on {s['dv']}. " + "; ".join(parts_en) + f". The final block {'added' if sig else 'did not add'} significant explained variance."
    ar = f"الانحدار الهرمي للمتغير {s['dv']}. " + "؛ ".join(parts_ar) + f". {'أضافت' if sig else 'لم تضف'} الكتلة الأخيرة تبايناً مفسراً دالاً."
    return _out(en, ar, en, ar, sig, f"ΔR² = {fr(last['delta_r2'], 3)}", f"ΔR² = {fr(last['delta_r2'], 3)}", ("correlational",))


def _i_logistic(res, s, a):
    sig = _sig(s["llr_p"], a)
    preds_en = "; ".join(f"{c['term']} (OR = {fnum(c['OR'])}, 95% CI [{fnum(c['or_low'])}, {fnum(c['or_high'])}], p {fp(c['p'])})" for c in s["coefficients"] if c["term"] != "(Intercept)" and c["p"] < a)
    preds_ar = "؛ ".join(f"{c['term']} (نسبة الأرجحية = {fnum(c['OR'])}، [{fnum(c['or_low'])}، {fnum(c['or_high'])}]، p {fp(c['p'])})" for c in s["coefficients"] if c["term"] != "(Intercept)" and c["p"] < a)
    en = (f"Binary logistic regression for {s['dv']} = '{s['event']}': the model was {'statistically significant' if sig else 'not statistically significant'}, χ²({fnum(s['llr_df'], 0)}) = {fnum(s['llr_chi2'])}, p {fp(s['llr_p'])}, "
          f"Nagelkerke R² = {fr(s['nagelkerke_r2'], 3)}, classification accuracy = {fnum(100 * s['accuracy'], 1)}%. " + (f"Significant predictors: {preds_en}." if preds_en else ""))
    ar = (f"الانحدار اللوجستي الثنائي للمتغير {s['dv']} = '{s['event']}': كان النموذج {'دالاً' if sig else 'غير دال'} إحصائياً، χ²({fnum(s['llr_df'], 0)}) = {fnum(s['llr_chi2'])}، p {fp(s['llr_p'])}، "
          f"R² ناجيلكيرك = {fr(s['nagelkerke_r2'], 3)}، ودقة التصنيف = {fnum(100 * s['accuracy'], 1)}%. " + (f"المتنبئات الدالة: {preds_ar}." if preds_ar else ""))
    return _out(en, ar, en, ar, sig, None, None, ("correlational",))


def _i_ordinal(res, s, a):
    sig = _sig(s["lr_p"], a)
    en = f"Ordinal logistic regression for {s['dv']}: LR χ²({s['lr_df']}) = {fnum(s['lr_chi2'])}, p {fp(s['lr_p'])}, Nagelkerke R² = {fr(s['nagelkerke_r2'], 3)}."
    ar = f"الانحدار اللوجستي الرتبي للمتغير {s['dv']}: χ²({s['lr_df']}) = {fnum(s['lr_chi2'])}، p {fp(s['lr_p'])}، R² ناجيلكيرك = {fr(s['nagelkerke_r2'], 3)}."
    return _out(en, ar, en, ar, sig, None, None, ("correlational",))


def _i_reliability(res, s, a):
    en_parts, ar_parts = [], []
    for sc in s["scales"]:
        en_parts.append(f"{sc['dimension']} ({sc['items']} items): α = {fr(sc['alpha'], 2)} [95% CI {fr(sc['alpha_ci_low'], 2)}, {fr(sc['alpha_ci_high'], 2)}], ω = {fr(sc['omega'], 2)} ({sc['label_en']})")
        ar_parts.append(f"{sc['dimension']} ({sc['items']} بنود): ألفا = {fr(sc['alpha'], 2)} [فترة الثقة 95%: {fr(sc['alpha_ci_low'], 2)}، {fr(sc['alpha_ci_high'], 2)}]، أوميغا = {fr(sc['omega'], 2)} ({sc['label_ar']})")
    weak = [i for i in s["items"] if i["citc"] is not None and i["citc"] < 0.3]
    en = "Internal consistency: " + "; ".join(en_parts) + "."
    ar = "الاتساق الداخلي: " + "؛ ".join(ar_parts) + "."
    if weak:
        en += " Items with corrected item-total correlation < .30: " + ", ".join(f"{i['item']} (r = {fr(i['citc'])})" for i in weak) + " — review their wording/fit before deciding to drop them."
        ar += " بنود ارتباطها المصحح بالدرجة الكلية أقل من .30: " + "، ".join(f"{i['item']} (r = {fr(i['citc'])})" for i in weak) + " — تُراجع صياغتها وملاءمتها قبل تقرير حذفها."
    lim = [{"en": "Cronbach's α assumes tau-equivalence and does not demonstrate unidimensionality; ω and factor analysis complement it.",
            "ar": "يفترض ألفا كرونباخ تكافؤ التشبعات ولا يثبت أحادية البعد؛ وتكمّله أوميغا والتحليل العاملي."}]
    o = _out(en, ar, en, ar, None)
    o["limitations"] = lim
    return o


def _i_validity(res, s, a):
    conv = s["convergent"]
    en = ("Convergent validity: " + "; ".join(f"{r['dimension']} CR = {fr(r['cr'], 3)}, AVE = {fr(r['ave'], 3)} ({r['convergent_en']})" for r in conv) +
          f". Discriminant validity — Fornell–Larcker: {'supported' if s['fornell_larcker_ok'] else 'not supported'}" +
          (f"; HTMT < .85: {'supported' if s['htmt_ok'] else 'not supported'}" if s.get("htmt_ok") is not None else "") + f". KMO = {fr(s['kmo'], 3)}.")
    ar = ("الصدق التقاربي: " + "؛ ".join(f"{r['dimension']}: CR = {fr(r['cr'], 3)}، AVE = {fr(r['ave'], 3)} ({r['convergent_ar']})" for r in conv) +
          f". الصدق التمييزي — معيار فورنل–لاركر: {'متحقق' if s['fornell_larcker_ok'] else 'غير متحقق'}" +
          (f"؛ HTMT < .85: {'متحقق' if s['htmt_ok'] else 'غير متحقق'}" if s.get("htmt_ok") is not None else "") + f". KMO = {fr(s['kmo'], 3)}.")
    o = _out(en, ar, en, ar, None)
    o["limitations"] = [{"en": "No single index establishes validity; integrate content, response-process and external evidence.",
                         "ar": "لا يثبت مؤشر واحد الصدق؛ يجب دمج أدلة المحتوى وعمليات الاستجابة والأدلة الخارجية."}]
    return o


def _i_efa(res, s, a):
    cum = s["variance"][-1]["cumulative"] if s.get("variance") else None
    en = (f"Exploratory factor analysis ({res['params'].get('method')}, {res['params'].get('rotation') or 'no'} rotation): KMO = {fr(s['kmo'], 3)}, Bartlett's χ² = {fnum(s['bartlett_chi2'])}, p {fp(s['bartlett_p'])}. "
          f"Parallel analysis suggested {s['n_parallel']} factor(s) (Kaiser: {s['n_kaiser']}); {s['n_factors']} factor(s) were extracted, explaining {fnum(cum, 1)}% of the variance.")
    ar = (f"التحليل العاملي الاستكشافي ({res['params'].get('method')}، تدوير {res['params'].get('rotation') or 'بدون'}): KMO = {fr(s['kmo'], 3)}، χ² بارتليت = {fnum(s['bartlett_chi2'])}، p {fp(s['bartlett_p'])}. "
          f"اقترح التحليل الموازي {s['n_parallel']} عامل/عوامل (كايزر: {s['n_kaiser']})؛ واستُخرج {s['n_factors']} عامل/عوامل تفسر {fnum(cum, 1)}% من التباين.")
    return _out(en, ar, en, ar, None, limits=("exploratory",))


def _i_pca(res, s, a):
    en = f"PCA retained {s['n_components']} component(s); KMO = {fr(s['kmo'], 3)}, Bartlett p {fp(s['bartlett_p'])}."
    ar = f"احتفظ تحليل المكونات الرئيسية بـ {s['n_components']} مكون/مكونات؛ KMO = {fr(s['kmo'], 3)}، p بارتليت {fp(s['bartlett_p'])}."
    return _out(en, ar, en, ar, None, limits=("exploratory",))


def _i_cfa(res, s, a):
    f = s["fit"]
    good = sum([(f.get("cfi") or 0) >= .95, (f.get("tli") or 0) >= .95, (f.get("rmsea") or 1) <= .06, (f.get("srmr") or 1) <= .08])
    acceptable = sum([(f.get("cfi") or 0) >= .90, (f.get("tli") or 0) >= .90, (f.get("rmsea") or 1) <= .08, (f.get("srmr") or 1) <= .08])
    verdict_en = "good" if good >= 3 else "acceptable" if acceptable >= 3 else "poor"
    verdict_ar = {"good": "جيدة", "acceptable": "مقبولة", "poor": "ضعيفة"}[verdict_en]
    en = (f"The pre-specified model showed {verdict_en} fit: χ²({fnum(f['df'], 0)}) = {fnum(f['chi2'])}, p {fp(f['p'])}, CFI = {fr(f['cfi'], 3)}, TLI = {fr(f['tli'], 3)}, "
          f"RMSEA = {fr(f['rmsea'], 3)}, SRMR = {fr(f['srmr'], 3)}. Standardized loadings ranged from {fr(min(l['std_loading'] for l in s['loadings']), 2)} to {fr(max(l['std_loading'] for l in s['loadings']), 2)}.")
    ar = (f"أظهر النموذج المحدد مسبقاً مطابقة {verdict_ar}: χ²({fnum(f['df'], 0)}) = {fnum(f['chi2'])}، p {fp(f['p'])}، CFI = {fr(f['cfi'], 3)}، TLI = {fr(f['tli'], 3)}، "
          f"RMSEA = {fr(f['rmsea'], 3)}، SRMR = {fr(f['srmr'], 3)}. وتراوحت التشبعات المعيارية بين {fr(min(l['std_loading'] for l in s['loadings']), 2)} و{fr(max(l['std_loading'] for l in s['loadings']), 2)}.")
    o = _out(en, ar, en, ar, None)
    o["limitations"] = [{"en": "Fit cut-offs are heuristics; also inspect residuals, loadings and theoretical plausibility.",
                         "ar": "معايير المطابقة إرشادية؛ ويجب فحص البواقي والتشبعات والمعقولية النظرية."}]
    return o


_i_sem = _i_cfa


def _i_chisquare(res, s, a):
    p = s["fisher_p"] if s.get("recommended") == "Fisher's exact test" else s["p"]
    sig = _sig(p, a)
    v1, v2 = res["params"]["var1"], res["params"]["var2"]
    en = f"A χ² test of independence showed {'a significant' if sig else 'no significant'} association between {v1} and {v2}, χ²({s['df']}, N = {s['n']}) = {fnum(s['chi2'])}, p {fp(s['p'])}, Cramér's V = {fr(s['cramers_v'], 3)}."
    ar = f"أظهر اختبار كاي تربيع للاستقلالية {'وجود' if sig else 'عدم وجود'} علاقة دالة بين {v1} و{v2}، χ²({s['df']}، N = {s['n']}) = {fnum(s['chi2'])}، p {fp(s['p'])}، V كرامر = {fr(s['cramers_v'], 3)}."
    if s.get("fisher_p") is not None:
        en += f" Fisher's exact test: p {fp(s['fisher_p'])}."
        ar += f" اختبار فيشر الدقيق: p {fp(s['fisher_p'])}."
    return _out(en, ar, en, ar, sig, f"V = {fr(s['cramers_v'], 3)}", f"V = {fr(s['cramers_v'], 3)}", ("correlational",))


_i_fisher = _i_chisquare


def _i_mediation(res, s, a):
    lo, hi = s["indirect_ci"]
    en = (f"The indirect effect of {s['x']} on {s['y']} through {s['m']} was b = {fnum(s['indirect'], 3)}, 95% bootstrap CI [{fnum(lo, 3)}, {fnum(hi, 3)}] ({s['n_boot']} resamples); "
          f"total effect c = {fnum(s['total'], 3)}, direct effect c' = {fnum(s['direct'], 3)}. Interpretation: {s['type_en']}.")
    ar = (f"بلغ التأثير غير المباشر لـ {s['x']} في {s['y']} عبر {s['m']} (b = {fnum(s['indirect'], 3)})، بفترة ثقة إقلاعية 95% [{fnum(lo, 3)}، {fnum(hi, 3)}] ({s['n_boot']} عينة)؛ "
          f"والتأثير الكلي c = {fnum(s['total'], 3)}، والتأثير المباشر c' = {fnum(s['direct'], 3)}. التفسير: {s['type_ar']}.")
    return _out(en, ar, en, ar, s["indirect_sig"], None, None, ("correlational",))


def _i_moderation(res, s, a):
    sig = _sig(s["interaction_p"], a)
    en = (f"The {s['x']} × {s['w']} interaction on {s['y']} was {'significant' if sig else 'not significant'}, b = {fnum(s['interaction_b'], 3)}, p {fp(s['interaction_p'])}, ΔR² = {fr(s['delta_r2'], 3)}. "
          + " ".join(f"Simple slope at {sl['level_en'].split(' at ')[-1]}: b = {fnum(sl['slope'], 3)}, p {fp(sl['p'])}." for sl in s["slopes"]))
    ar = (f"كان التفاعل {s['x']} × {s['w']} في {s['y']} {'دالاً' if sig else 'غير دال'} إحصائياً، b = {fnum(s['interaction_b'], 3)}، p {fp(s['interaction_p'])}، ΔR² = {fr(s['delta_r2'], 3)}. "
          + " ".join(f"الميل البسيط عند {sl['level_ar'].split(' عند ')[-1]}: b = {fnum(sl['slope'], 3)}، p {fp(sl['p'])}." for sl in s["slopes"]))
    return _out(en, ar, en, ar, sig, f"ΔR² = {fr(s['delta_r2'], 3)}", f"ΔR² = {fr(s['delta_r2'], 3)}", ("correlational",))


def _i_manova(res, s, a):
    sig = _sig(s["p"], a)
    w = next(r for r in s["tests"] if r["test"] == "Wilks' lambda")
    en = f"MANOVA: {'a significant' if sig else 'no significant'} multivariate effect, Wilks' Λ = {fnum(w['value'], 3)}, F({fnum(w['df1'], 0)}, {fnum(w['df2'], 1)}) = {fnum(w['F'])}, p {fp(w['p'])}, partial η² = {fr(s['partial_eta2'], 3)}."
    ar = f"تحليل التباين المتعدد: {'وُجد' if sig else 'لم يوجد'} أثر متعدد المتغيرات دال، لامدا ويلكس = {fnum(w['value'], 3)}، ف({fnum(w['df1'], 0)}، {fnum(w['df2'], 1)}) = {fnum(w['F'])}، p {fp(w['p'])}، η² الجزئي = {fr(s['partial_eta2'], 3)}."
    return _out(en, ar, en, ar, sig)


def _i_likert(res, s, a):
    dims = s["dimensions"]
    top, bottom = s["top"], s["bottom"]
    en = (f"Overall, responses averaged M = {fnum(s['overall_mean'])} (SD = {fnum(s['overall_sd'])}) on a {s['scale'][0]}–{s['scale'][1]} scale, a {str(s['overall_level_en']).lower()} level. "
          + ("Dimensions ranked: " + "; ".join(f"{d['rank']}. {d['dimension']} (M = {fnum(d['mean'])}, {d['level_en']})" for d in sorted(dims, key=lambda d: d["rank"])) + ". " if dims else "")
          + (f"Highest-rated item: {top[0]['item']} (M = {fnum(top[0]['mean'])}); lowest: {bottom[0]['item']} (M = {fnum(bottom[0]['mean'])})." if top and bottom else ""))
    ar = (f"بلغ المتوسط العام للاستجابات (م = {fnum(s['overall_mean'])}، ع = {fnum(s['overall_sd'])}) على مقياس {s['scale'][0]}–{s['scale'][1]}، بمستوى {s['overall_level_ar']}. "
          + ("ترتيب الأبعاد: " + "؛ ".join(f"{d['rank']}. {d['dimension']} (م = {fnum(d['mean'])}، {d['level_ar']})" for d in sorted(dims, key=lambda d: d["rank"])) + ". " if dims else "")
          + (f"أعلى البنود تقديراً: {top[0]['item']} (م = {fnum(top[0]['mean'])})؛ وأدناها: {bottom[0]['item']} (م = {fnum(bottom[0]['mean'])})." if top and bottom else ""))
    return _out(en, ar, en, ar, None, limits=("self_report", "sample"))


def _i_normality(res, s, a):
    en = " ".join(f"{r['variable']}{' (' + r['group'] + ')' if r.get('group') else ''}: {r['decision_en']} (n = {r['n']}, skew = {fnum(r.get('skewness'))}, kurtosis = {fnum(r.get('kurtosis'))}"
                  + (f", W = {fnum(r.get('shapiro_w'), 3)}, p {fp(r.get('shapiro_p'))}" if r.get("shapiro_w") is not None else "") + ")." for r in s["rows"])
    ar = " ".join(f"{r['variable']}{' (' + r['group'] + ')' if r.get('group') else ''}: {r['decision_ar']} (n = {r['n']}، الالتواء = {fnum(r.get('skewness'))}، التفلطح = {fnum(r.get('kurtosis'))}"
                  + (f"، W = {fnum(r.get('shapiro_w'), 3)}، p {fp(r.get('shapiro_p'))}" if r.get("shapiro_w") is not None else "") + ")." for r in s["rows"])
    return _out(en, ar, en, ar, None)


def _i_rm_anova(res, s, a):
    p = s["p_used"]
    sig = _sig(p, a)
    en = f"Repeated-measures ANOVA: {'significant' if sig else 'no significant'} differences across {', '.join(s['variables'])}, F({fnum(s['df1'], 0)}, {fnum(s['df2'], 0)}) = {fnum(s['F'])}, p {fp(p)}, η²G = {fr(s.get('ng2'), 3)}."
    ar = f"تحليل التباين للقياسات المتكررة: {'توجد' if sig else 'لا توجد'} فروق دالة بين {'، '.join(s['variables'])}، ف({fnum(s['df1'], 0)}، {fnum(s['df2'], 0)}) = {fnum(s['F'])}، p {fp(p)}، η²G = {fr(s.get('ng2'), 3)}."
    return _out(en, ar, en, ar, sig)


def _i_friedman(res, s, a):
    sig = _sig(s["p"], a)
    en = f"Friedman test: χ²({s['df']}) = {fnum(s['chi2'])}, p {fp(s['p'])}, Kendall's W = {fr(s['kendall_w'], 3)}."
    ar = f"اختبار فريدمان: χ²({s['df']}) = {fnum(s['chi2'])}، p {fp(s['p'])}، W كندال = {fr(s['kendall_w'], 3)}."
    return _out(en, ar, en, ar, sig)


def _i_ttest_one(res, s, a):
    sig = _sig(s["p"], a)
    en = f"A one-sample t-test compared {s['variable']} (M = {fnum(s['mean'])}, SD = {fnum(s['sd'])}) with {fnum(s['test_value'])}: t({fnum(s['df'], 0)}) = {fnum(s['t'])}, p {fp(s['p'])}, d = {fnum(s['cohens_d'])}."
    ar = f"قارن اختبار (ت) لعينة واحدة متوسط {s['variable']} (م = {fnum(s['mean'])}، ع = {fnum(s['sd'])}) بالقيمة {fnum(s['test_value'])}: ت({fnum(s['df'], 0)}) = {fnum(s['t'])}، p {fp(s['p'])}، d = {fnum(s['cohens_d'])}."
    return _out(en, ar, en, ar, sig)


def _i_anova_twoway(res, s, a):
    en = "Two-way ANOVA: " + "; ".join(f"{e['source_en']}: F({fnum(e['df'], 0)}) = {fnum(e['F'])}, p {fp(e['p'])}, partial η² = {fr(e['partial_eta2'], 3)}" for e in s["effects"] if e["F"] is not None) + "."
    ar = "تحليل التباين الثنائي: " + "؛ ".join(f"{e['source_ar']}: ف({fnum(e['df'], 0)}) = {fnum(e['F'])}، p {fp(e['p'])}، η² الجزئي = {fr(e['partial_eta2'], 3)}" for e in s["effects"] if e["F"] is not None) + "."
    return _out(en, ar, en, ar, any(_sig(e["p"], a) for e in s["effects"] if e["p"] is not None))


def _i_cluster(res, s, a):
    en = f"Cluster analysis identified k = {s['k']} cluster(s) (silhouette = {fnum(s.get('silhouette'), 3)}); sizes: {', '.join(f'{k}: {v}' for k, v in s['sizes'].items())}."
    ar = f"حدد التحليل العنقودي k = {s['k']} عنقود/عناقيد (الصورة الظلية = {fnum(s.get('silhouette'), 3)})؛ الأحجام: {'، '.join(f'{k}: {v}' for k, v in s['sizes'].items())}."
    return _out(en, ar, en, ar, None, limits=("exploratory",))


def _i_text(res, s, a):
    en = f"{s['n_responses']} open-ended responses analysed; " + (f"{len(s['topics'])} candidate topic(s) identified. " if s["topics"] else "") + "Top terms: " + ", ".join(k["term"] for k in s["keywords"][:8]) + "."
    ar = f"حُللت {s['n_responses']} إجابة مفتوحة؛ " + (f"وحُدد {len(s['topics'])} موضوع/موضوعات مرشحة. " if s["topics"] else "") + "أكثر المصطلحات: " + "، ".join(k["term"] for k in s["keywords"][:8]) + "."
    return _out(en, ar, en, ar, None, limits=("exploratory",))


def hypothesis_decision(res: dict, interp: dict, alpha: float) -> dict:
    sig = interp.get("significant")
    if sig is None:
        return {"decision": "descriptive", "en": "Not a significance test — evaluate against the stated criteria.", "ar": "ليس اختباراً للدلالة — يُقيَّم وفق المعايير المحددة."}
    if sig:
        return {"decision": "supported", "en": f"Supported by the data at α = {alpha} (the null hypothesis is rejected).",
                "ar": f"الفرضية مدعومة إحصائياً عند مستوى α = {alpha} (رُفضت الفرضية الصفرية)."}
    return {"decision": "not_supported", "en": f"Not supported at α = {alpha} (failed to reject the null hypothesis; this does not prove the null).",
            "ar": f"الفرضية غير مدعومة إحصائياً عند مستوى α = {alpha} (لم تُرفض الفرضية الصفرية، ولا يعني ذلك إثباتها)."}
