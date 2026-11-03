"""Builds a format-neutral report document from the project's actual data and saved analyses.

Document = {title, subtitle, lang, notice, sections: [{heading, blocks: [...]}]}
Block types: {"type": "p", "text"}, {"type": "table", "table"}, {"type": "figure", "chart"}, {"type": "bullets", "items"}
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..demo.synthetic import SYNTHETIC_NOTICE_AR, SYNTHETIC_NOTICE_EN
from ..engine.runner import run_analysis
from ..engine.utils import AnalysisError
from ..services import current_dataset, frames, project_quality

REPORT_TYPES = {
    "comprehensive": ("Comprehensive statistical report", "التقرير الإحصائي الشامل"),
    "apa": ("Academic report (APA 7)", "التقرير الأكاديمي وفق APA 7"),
    "executive": ("Executive summary", "التقرير التنفيذي المختصر"),
    "quality": ("Data quality report", "تقرير جودة البيانات"),
    "hypotheses": ("Hypothesis-testing report", "تقرير اختبار الفرضيات"),
}

CATEGORY_SECTIONS = [
    ("difference", "Group differences", "اختبارات الفروق"),
    ("relationship", "Correlation analysis", "تحليل الارتباط"),
    ("regression", "Regression analysis", "تحليل الانحدار"),
    ("factor", "Factor analysis", "التحليل العاملي"),
    ("association", "Associations between categorical variables", "العلاقات بين المتغيرات الفئوية"),
    ("advanced", "Advanced analyses", "التحليلات المتقدمة"),
    ("qualitative", "Open-ended responses", "الإجابات المفتوحة"),
]


def _t(lang, en, ar):
    return ar if lang == "ar" else en


def _p(text):
    return {"type": "p", "text": text}


def _res_blocks(res: dict, lang: str, apa_only=False, max_charts=2) -> list[dict]:
    b = []
    it = res.get("interpretation") or {}
    txt = it.get("apa_ar" if lang == "ar" else "apa_en") or it.get("summary_ar" if lang == "ar" else "summary_en")
    if txt:
        b.append(_p(txt))
    for tb in res.get("tables", [])[: (2 if apa_only else 6)]:
        b.append({"type": "table", "table": tb})
    if not apa_only:
        for ch in res.get("charts", [])[:max_charts]:
            b.append({"type": "figure", "chart": ch})
    for a in res.get("assumptions", []):
        mark = "✓" if a.get("met") else ("✗" if a.get("met") is False else "•")
        b.append(_p(f"{mark} {_t(lang, a['name_en'], a['name_ar'])} ({a['test']}): {_t(lang, a['detail_en'], a['detail_ar'])}"))
    for w in res.get("warnings", []):
        b.append(_p("⚠ " + _t(lang, w["en"], w["ar"])))
    lims = it.get("limitations") or []
    if lims and not apa_only:
        b.append({"type": "bullets", "items": [_t(lang, l["en"], l["ar"]) for l in lims]})
    return b


def _safe_run(kind, df, d, params, alpha):
    try:
        return run_analysis(kind, df, d, params, alpha)
    except AnalysisError:
        return None


def build_report(project, report_type: str = "comprehensive", lang: str = "ar", hypothesis_id: str | None = None) -> dict:
    if report_type not in REPORT_TYPES:
        raise AnalysisError("Unknown report type.", "نوع تقرير غير معروف.")
    f = frames(project)
    d = project.dictionary
    df = f.analysis
    ds = current_dataset(project)
    settings = project.settings or {}
    alpha = float(settings.get("alpha", 0.05))
    q = project_quality(project)
    comps = df.attrs.get("composites", {})
    comp_cols = [c for k, c in comps.items() if k != "__overall__"]
    title = settings.get("study_title") or project.name
    sections = []
    saved = [a for a in project.analyses if a.in_report]
    is_current = lambda a: a.data_fingerprint == f.fingerprint  # noqa: E731

    # 1-2. Dataset description
    desc = [_p(_t(lang,
                  f"Data file: {ds.filename} (version {ds.version}; SHA-256 {ds.sha256[:16]}…; encoding {ds.encoding}; delimiter '{ds.delimiter}'). "
                  f"The original file contained {len(f.raw)} responses and {f.raw.shape[1]} variables; after the approved cleaning steps, {len(df)} responses were analysed.",
                  f"ملف البيانات: {ds.filename} (الإصدار {ds.version}؛ بصمة SHA-256 ‏{ds.sha256[:16]}…؛ الترميز {ds.encoding}؛ الفاصل '{ds.delimiter}'). "
                  f"تضمّن الملف الأصلي {len(f.raw)} استجابة و{f.raw.shape[1]} متغيراً؛ وبعد خطوات التنظيف المعتمدة حُللت {len(df)} استجابة."))]
    var_rows = [{"name": v["name"], "label": v.get("label"), "dtype": v["dtype"], "level": v["level"], "role": v["role"], "dimension": v.get("dimension") or "",
                 "reverse": "✓" if v.get("reverse") else ""} for v in d["variables"]]
    desc.append({"type": "table", "table": {"id": "dictionary", "title_en": "Data dictionary", "title_ar": "قاموس البيانات",
                                            "columns": [{"key": "name", "en": "Variable", "ar": "المتغير"}, {"key": "label", "en": "Label", "ar": "الوصف"},
                                                        {"key": "dtype", "en": "Type", "ar": "النوع"}, {"key": "level", "en": "Level", "ar": "مستوى القياس"},
                                                        {"key": "role", "en": "Role", "ar": "الدور"}, {"key": "dimension", "en": "Dimension", "ar": "البعد"},
                                                        {"key": "reverse", "en": "Reverse", "ar": "عكسي"}], "rows": var_rows}})
    if report_type != "executive":
        sections.append({"heading": _t(lang, "Description of the dataset", "وصف قاعدة البيانات"), "blocks": desc})

    # 3. Data processing methodology
    ops = project.cleaning_ops or []
    op_rows = [{"op": _t(lang, o["label_en"], o["label_ar"]), "reason": _t(lang, o["reason_en"], o["reason_ar"]), "status": o["status"],
                "affected": o.get("affected")} for o in ops]
    method = [_p(_t(lang,
                    f"Data quality index: {q['quality_score']}/100; completeness {q['completeness_pct']}%; {q['duplicates']['count']} duplicate(s). "
                    "Every cleaning operation was proposed by the platform and individually accepted or rejected by the researcher; the original file is kept unchanged and all steps are logged for reproducibility.",
                    f"مؤشر جودة البيانات: {q['quality_score']}/100؛ نسبة الاكتمال {q['completeness_pct']}%؛ عدد السجلات المكررة {q['duplicates']['count']}. "
                    "اقترحت المنصة كل عملية تنظيف، وقبلها الباحث أو رفضها منفردة؛ ويُحتفظ بالملف الأصلي دون تعديل، وتُسجَّل جميع الخطوات لضمان إمكانية إعادة الإنتاج."))]
    if op_rows:
        method.append({"type": "table", "table": {"id": "ops", "title_en": "Data-processing log", "title_ar": "سجل معالجة البيانات",
                                                  "columns": [{"key": "op", "en": "Operation", "ar": "العملية"}, {"key": "reason", "en": "Reason", "ar": "السبب"},
                                                              {"key": "affected", "en": "Affected", "ar": "المتأثر"}, {"key": "status", "en": "Decision", "ar": "القرار"}],
                                                  "rows": op_rows}})
    if f.notes:
        method.append({"type": "bullets", "items": [_t(lang, n["en"], n["ar"]) for n in f.notes]})
    lk = d.get("likert", {})
    method.append(_p(_t(lang, f"Likert scale: {lk.get('min')}–{lk.get('max')} ({lk.get('points')} points). Interpretation bands: " +
                        "; ".join(f"{b['from']:.2f}–{b['to']:.2f} {b['en']}" for b in lk.get("interpretation", [])),
                        f"مقياس ليكرت: {lk.get('min')}–{lk.get('max')} ({lk.get('points')} نقاط). حدود التفسير: " +
                        "؛ ".join(f"{b['from']:.2f}–{b['to']:.2f} {b['ar']}" for b in lk.get("interpretation", [])))))
    if report_type in ("comprehensive", "apa", "quality"):
        sections.append({"heading": _t(lang, "Data processing methodology", "منهجية معالجة البيانات"), "blocks": method})

    if report_type == "quality":
        qb = [{"type": "table", "table": {"id": "issues", "title_en": "Detected issues", "title_ar": "المشكلات المكتشفة",
                                          "columns": [{"key": "sev", "en": "Severity", "ar": "الخطورة"}, {"key": "issue", "en": "Issue", "ar": "المشكلة"}, {"key": "count", "en": "Count", "ar": "العدد"}],
                                          "rows": [{"sev": i["severity"], "issue": _t(lang, i["en"], i["ar"]), "count": i["count"]} for i in q["issues"]]}},
              {"type": "table", "table": {"id": "missing", "title_en": "Missing values by variable", "title_ar": "القيم المفقودة لكل متغير",
                                          "columns": [{"key": "variable", "en": "Variable", "ar": "المتغير"}, {"key": "missing", "en": "Missing", "ar": "المفقود"},
                                                      {"key": "missing_pct", "en": "%", "ar": "%", "fmt": "1"}], "rows": q["per_variable"]}},
              _p(_t(lang, q["score_note_en"], q["score_note_ar"]))]
        sections.append({"heading": _t(lang, "Data quality", "جودة البيانات"), "blocks": qb})
        return _doc(project, report_type, lang, title, sections)

    # 4. Sample characteristics
    demo = [v["name"] for v in d["variables"] if v.get("role") == "demographic" and v["name"] in df.columns]
    if demo:
        r = _safe_run("descriptive", df, d, {"variables": demo}, alpha)
        if r:
            sb = [{"type": "table", "table": t} for t in r["tables"]]
            sb += [{"type": "figure", "chart": c} for c in r["charts"][:3]] if report_type == "comprehensive" else []
            sections.append({"heading": _t(lang, "Sample characteristics", "وصف العينة وخصائص المشاركين"), "blocks": sb})

    # 5. Descriptive statistics (Likert)
    lik = _safe_run("likert", df, d, {}, alpha)
    if lik:
        sections.append({"heading": _t(lang, "Descriptive statistics", "الإحصاء الوصفي"), "blocks": _res_blocks(lik, lang, report_type == "apa")})

    # 6. Reliability & validity
    rv = []
    rel = _safe_run("reliability", df, d, {}, alpha) if d.get("dimensions") else None
    if rel:
        rv += _res_blocks(rel, lang, report_type == "apa", 1)
    val = next((a.result for a in reversed(saved) if a.kind == "validity" and is_current(a)), None)
    if val is None and len(d.get("dimensions", [])) >= 2 and report_type in ("comprehensive", "apa"):
        val = _safe_run("validity", df, d, {}, alpha)
    if val:
        rv += _res_blocks(val, lang, report_type == "apa", 1)
    if rv and report_type != "executive":
        sections.append({"heading": _t(lang, "Validity and reliability", "الصدق والثبات"), "blocks": rv})

    # 7. Normality
    if comp_cols and report_type in ("comprehensive", "apa"):
        nr = _safe_run("normality", df, d, {"variables": comp_cols}, alpha)
        if nr:
            sections.append({"heading": _t(lang, "Normality assessment", "نتائج اختبارات التوزيع الطبيعي"), "blocks": _res_blocks(nr, lang, report_type == "apa", 2)})

    # 8. Hypotheses
    hyps = project.hypotheses or []
    if hypothesis_id:
        hyps = [h for h in hyps if h["id"] == hypothesis_id]
    hb, hrows = [], []
    for h in hyps:
        a = next((x for x in project.analyses if x.id == h.get("analysis_id")), None)
        dec = h.get("decision") or {}
        hrows.append({"code": h.get("code"), "text": h.get("text"), "test": (a.result.get("title_ar" if lang == "ar" else "title_en") if a else "—"),
                      "p": (a.result.get("stats", {}).get("p") if a else None), "p_adj": h.get("p_adjusted"),
                      "decision": _t(lang, dec.get("en", "Not tested"), dec.get("ar", "لم تُختبر"))})
        if a and report_type in ("comprehensive", "apa", "hypotheses"):
            hb.append(_p(f"{h.get('code')}: {h.get('text')}"))
            hb += _res_blocks(a.result, lang, report_type == "apa")
            if a.data_fingerprint != f.fingerprint:
                hb.append(_p(_t(lang, "⚠ This result was computed on an earlier version of the data/cleaning steps; re-run it.",
                                "⚠ حُسبت هذه النتيجة على نسخة سابقة من البيانات أو خطوات التنظيف؛ يُرجى إعادة تنفيذها.")))
    if hrows:
        summary_tbl = {"type": "table", "table": {"id": "hyp_summary", "title_en": "Summary of hypothesis tests", "title_ar": "ملخص نتائج اختبار الفرضيات",
                                                  "columns": [{"key": "code", "en": "H", "ar": "الفرضية"}, {"key": "text", "en": "Hypothesis", "ar": "النص"},
                                                              {"key": "test", "en": "Test", "ar": "الاختبار"}, {"key": "p", "en": "p", "ar": "p", "fmt": "p"},
                                                              {"key": "p_adj", "en": "p (Holm)", "ar": "p (هولم)", "fmt": "p"},
                                                              {"key": "decision", "en": "Decision", "ar": "القرار"}], "rows": hrows}}
        sections.append({"heading": _t(lang, "Hypothesis testing", "نتائج اختبار الفرضيات"), "blocks": [summary_tbl] + hb})
    if report_type == "hypotheses":
        return _doc(project, report_type, lang, title, sections)

    # 9-12. Saved analyses by category
    used = {h.get("analysis_id") for h in hyps}
    for cat, en, ar in CATEGORY_SECTIONS:
        items = [a for a in saved if a.result.get("category") == cat and a.id not in used and is_current(a)]
        if not items:
            continue
        blocks = []
        for a in items:
            blocks.append(_p(f"— {_t(lang, a.result['title_en'], a.result['title_ar'])}"))
            if report_type == "executive":
                it = a.result.get("interpretation") or {}
                blocks.append(_p(_t(lang, it.get("summary_en", ""), it.get("summary_ar", ""))))
            else:
                blocks += _res_blocks(a.result, lang, report_type == "apa")
        sections.append({"heading": _t(lang, en, ar), "blocks": blocks})

    # Discussion scaffold, conclusions, limitations
    findings = []
    for a in saved:
        if not is_current(a):
            continue
        it = a.result.get("interpretation") or {}
        if it.get("significant") is not None:
            findings.append((a, it))
    lit = settings.get("literature") or []
    disc = []
    if findings:
        disc.append(_p(_t(lang, "The following points summarise the statistically supported findings and provide a scaffold for discussing them against the literature supplied by the researcher. The comparison with prior studies must be written and verified by the researcher.",
                          "تلخص النقاط التالية النتائج المدعومة إحصائياً، وتقدم إطاراً لمناقشتها في ضوء الأدبيات التي زوّد بها الباحث المنصة. ويجب أن يكتب الباحث المقارنة بالدراسات السابقة ويتحقق منها.")))
        for a, it in findings:
            disc.append(_p("• " + _t(lang, it.get("summary_en", ""), it.get("summary_ar", ""))))
            for ref in lit:
                kw = [k.strip().lower() for k in (ref.get("keywords") or "").split(",") if k.strip()]
                vars_ = " ".join(str(v) for v in a.params.values()).lower()
                if kw and any(k in vars_ or k in a.kind for k in kw):
                    disc.append(_p(_t(lang, f"   ↳ Compare with {ref.get('citation')}: “{ref.get('finding', '')}”.",
                                      f"   ↳ قارن مع {ref.get('citation')}: «{ref.get('finding', '')}».")))
    if disc and report_type in ("comprehensive", "apa"):
        sections.append({"heading": _t(lang, "Discussion", "مناقشة النتائج"), "blocks": disc})
    concl = []
    sig = [it for _, it in findings if it.get("significant")]
    nsig = [it for _, it in findings if it.get("significant") is False]
    concl.append(_p(_t(lang, f"{len(sig)} of {len(findings)} inferential analyses reached statistical significance at α = {alpha}.",
                       f"وصل {len(sig)} من أصل {len(findings)} تحليلاً استدلالياً إلى الدلالة الإحصائية عند α = {alpha}.")))
    recs = []
    if lik and lik["stats"].get("bottom"):
        b = lik["stats"]["bottom"][0]
        recs.append(_t(lang, f"Prioritise improvement on the lowest-rated item ({b['item']}, M = {b['mean']:.2f}).",
                       f"إعطاء الأولوية لتحسين البند الأدنى تقديراً ({b['item']}، المتوسط = {b['mean']:.2f})."))
    if rel:
        weak = [s for s in rel["stats"]["scales"] if s["alpha"] is not None and s["alpha"] < 0.7]
        for s in weak:
            recs.append(_t(lang, f"Revise the items of {s['dimension']} (α = {s['alpha']:.2f}) before further use of the instrument.",
                           f"مراجعة بنود البعد {s['dimension']} (ألفا = {s['alpha']:.2f}) قبل إعادة استخدام الأداة."))
    if nsig:
        recs.append(_t(lang, "Non-significant results may reflect limited power: consider a priori power analysis and larger samples in future studies.",
                       "قد تعكس النتائج غير الدالة قوة إحصائية محدودة: يُنصح بتحليل القوة المسبق وعينات أكبر في الدراسات المستقبلية."))
    if recs:
        concl.append({"type": "bullets", "items": recs})
    sections.append({"heading": _t(lang, "Conclusions and recommendations", "الاستنتاجات والتوصيات"), "blocks": concl})
    sampling = settings.get("sampling_method") or ""
    lim = [_t(lang, "Results are based on self-reported questionnaire data.", "تعتمد النتائج على بيانات استبانة ذاتية التقرير."),
           _t(lang, f"Generalisation is limited by the sampling method{(' (' + sampling + ')') if sampling else ''}.",
              f"يتحدد التعميم بطريقة اختيار العينة{(' (' + sampling + ')') if sampling else ''}."),
           _t(lang, "Correlational/regression findings do not establish causality.", "نتائج الارتباط والانحدار لا تثبت السببية."),
           _t(lang, f"Missing data: handled as documented in the processing log; composites require ≥ {int(100 * d.get('composite_min_answered', 0.5))}% answered items.",
              f"القيم المفقودة: عولجت كما هو موثق في سجل المعالجة؛ وتتطلب الدرجات المركبة الإجابة عن {int(100 * d.get('composite_min_answered', 0.5))}% من البنود على الأقل."),
           _t(lang, "Analyses labelled exploratory (EFA, PCA, clustering, text) should be confirmed on independent data.",
              "ينبغي تأكيد التحليلات الاستكشافية (العاملي الاستكشافي، المكونات الرئيسية، العنقودي، النصوص) على بيانات مستقلة.")]
    if not settings.get("weights_variable"):
        lim.append(_t(lang, "No sampling weights or complex-design information were specified; estimates assume simple random sampling.",
                      "لم تُحدد أوزان أو معلومات تصميم معقد للعينة؛ وتفترض التقديرات المعاينة العشوائية البسيطة."))
    sections.append({"heading": _t(lang, "Methodological and statistical limitations", "القيود المنهجية والإحصائية"), "blocks": [{"type": "bullets", "items": lim}]})
    return _doc(project, report_type, lang, title, sections)


def _doc(project, report_type, lang, title, sections):
    return {"title": title, "subtitle": _t(lang, *REPORT_TYPES[report_type]), "lang": lang, "type": report_type,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "notice": _t(lang, SYNTHETIC_NOTICE_EN, SYNTHETIC_NOTICE_AR) if project.is_synthetic else None,
            "sections": sections}
