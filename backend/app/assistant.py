"""Research assistant: answers questions using ONLY the project's computed results.

It is deterministic (no external AI service, so no research data leaves the server).
It routes the question to the relevant stored analyses and returns their computed
interpretations, hypothesis decisions, summaries, and recommendations. When nothing
relevant has been computed it says so instead of guessing.
"""
from __future__ import annotations

import re

from .engine.utils import fp, normalize_text

INTENTS = [
    ("summary", ["summary", "summarize", "summarise", "overview", "findings", "ملخص", "لخص", "النتائج", "اهم"]),
    ("hypotheses", ["hypothes", "supported", "accepted", "rejected", "فرض", "فرضيه", "فرضيات", "مقبوله", "مدعومه"]),
    ("reliability", ["reliab", "alpha", "omega", "cronbach", "ثبات", "الفا", "كرونباخ", "اوميغا"]),
    ("validity", ["validity", "ave", "htmt", "fornell", "صدق", "تقاربي", "تمييزي"]),
    ("correlation", ["correlat", "relationship", "ارتباط", "علاقه"]),
    ("regression", ["regress", "predict", "انحدار", "تنبؤ"]),
    ("difference", ["differ", "t-test", "ttest", "anova", "compare", "فروق", "فرق", "مقارنه", "تباين"]),
    ("factor", ["factor", "efa", "cfa", "pca", "loading", "عاملي", "تشبع", "عوامل"]),
    ("descriptive", ["descript", "mean", "likert", "level", "وصفي", "متوسط", "ليكرت", "مستوى"]),
    ("recommendations", ["recommend", "suggest", "توصي", "توصيات", "اقترح"]),
    ("limitations", ["limitation", "limit", "قيود", "حدود"]),
    ("apa", ["apa", "academic", "write", "اكاديمي", "صياغه", "اكتب"]),
]
CATEGORY_FOR = {"reliability": {"reliability"}, "validity": {"validity", "cfa"}, "correlation": {"correlation"},
                "regression": {"linear_simple", "linear_multiple", "polynomial", "hierarchical", "logistic", "ordinal"},
                "difference": {"ttest_ind", "mannwhitney", "anova", "kruskal", "anova_twoway", "ttest_paired", "wilcoxon", "rm_anova", "friedman", "ttest_one"},
                "factor": {"efa", "pca", "cfa"}, "descriptive": {"descriptive", "likert", "normality"}}


def detect(question: str) -> list[str]:
    q = normalize_text(question)
    found = [name for name, kws in INTENTS if any(normalize_text(k) in q for k in kws)]
    return found or ["summary"]


def answer(project, question: str, lang: str = "ar", analysis_id: str | None = None, current_fp: str | None = None) -> dict:
    ar = lang == "ar"
    analyses = [a for a in project.analyses if current_fp is None or a.data_fingerprint == current_fp]
    if analysis_id:
        a = next((x for x in project.analyses if x.id == analysis_id), None)
        if not a:
            return {"answer": "التحليل غير موجود." if ar else "Analysis not found.", "sources": []}
        it = a.result.get("interpretation", {})
        parts = [it.get("apa_ar" if ar else "apa_en") or it.get("summary_ar" if ar else "summary_en")]
        if it.get("effect_ar" if ar else "effect_en"):
            parts.append(("حجم الأثر: " if ar else "Effect size: ") + it["effect_ar" if ar else "effect_en"])
        for asm in a.result.get("assumptions", []):
            parts.append(("✓ " if asm.get("met") else "✗ " if asm.get("met") is False else "• ") + (asm["name_ar"] if ar else asm["name_en"]) + ": " + (asm["detail_ar"] if ar else asm["detail_en"]))
        for l in it.get("limitations", []):
            parts.append(("حدود الاستنتاج: " if ar else "Limitation: ") + l["ar" if ar else "en"])
        return {"answer": "\n\n".join(p for p in parts if p), "sources": [a.id], "intents": ["explain"]}
    intents = detect(question)
    parts, sources = [], []
    if not analyses:
        return {"answer": ("لا توجد نتائج تحليل محسوبة على النسخة الحالية من البيانات بعد. نفّذ التحليلات أولاً، ولن أقدّم أي قيمة إحصائية لم تُحسب فعلياً."
                           if ar else "There are no computed results for the current data yet. Run analyses first — I will not provide any statistic that has not actually been computed."),
                "sources": [], "intents": intents}
    for intent in intents:
        if intent == "hypotheses":
            hyps = project.hypotheses or []
            if not hyps:
                parts.append("لم تُعرَّف فرضيات بعد." if ar else "No hypotheses have been defined yet.")
            for h in hyps:
                dec = h.get("decision")
                if dec:
                    parts.append(f"{h['code']}: {h['text']} — {dec['ar' if ar else 'en']}" + (f" (p المعدلة بطريقة هولم {fp(h['p_adjusted'])})" if ar and h.get("p_adjusted") is not None else f" (Holm-adjusted p {fp(h['p_adjusted'])})" if h.get("p_adjusted") is not None else ""))
                    sources.append(h.get("analysis_id"))
                else:
                    parts.append(f"{h['code']}: {h['text']} — " + ("لم تُختبر بعد." if ar else "not tested yet."))
        elif intent in CATEGORY_FOR:
            rel = [a for a in analyses if a.result.get("kind") in CATEGORY_FOR[intent]]
            if not rel:
                parts.append(("لا توجد نتائج محسوبة من هذا النوع بعد." if ar else "No computed results of this type yet.") + f" ({intent})")
            for a in rel[-3:]:
                it = a.result.get("interpretation", {})
                parts.append(f"[{a.result['title_ar' if ar else 'title_en']}] " + (it.get("apa_ar" if ar else "apa_en") or it.get("summary_ar" if ar else "summary_en") or ""))
                sources.append(a.id)
        elif intent in ("summary", "apa"):
            for a in analyses[-8:]:
                it = a.result.get("interpretation", {})
                txt = it.get("apa_ar" if ar else "apa_en") or it.get("summary_ar" if ar else "summary_en")
                if txt:
                    parts.append(f"• {txt}")
                    sources.append(a.id)
        elif intent == "recommendations":
            sig = [a for a in analyses if (a.result.get("interpretation") or {}).get("significant")]
            nsig = [a for a in analyses if (a.result.get("interpretation") or {}).get("significant") is False]
            for a in analyses:
                if a.result.get("kind") == "likert" and a.result["stats"].get("bottom"):
                    b = a.result["stats"]["bottom"][0]
                    parts.append((f"إعطاء أولوية للتحسين في البند {b['item']} (المتوسط = {b['mean']:.2f})، وهو الأدنى تقديراً." if ar
                                  else f"Prioritise improvement on {b['item']} (M = {b['mean']:.2f}), the lowest-rated item."))
                    sources.append(a.id)
                    break
            if sig:
                parts.append((f"بناء التوصيات العملية على النتائج الدالة ({len(sig)}) مع مراعاة أحجام الأثر وليس قيمة p وحدها." if ar
                              else f"Base practical recommendations on the {len(sig)} significant result(s), weighting effect sizes rather than p-values alone."))
            if nsig:
                parts.append(("النتائج غير الدالة لا تعني انعدام الأثر؛ يوصى بتحليل القوة الإحصائية وعينات أكبر." if ar
                              else "Non-significant results do not show absence of an effect; consider power analysis and larger samples."))
            parts.append(("يوصى بتكرار الدراسة على عينة مستقلة لتأكيد النتائج الاستكشافية." if ar else "Replicate on an independent sample to confirm exploratory findings."))
        elif intent == "limitations":
            seen = set()
            for a in analyses:
                for l in (a.result.get("interpretation") or {}).get("limitations", []):
                    t = l["ar" if ar else "en"]
                    if t not in seen:
                        seen.add(t)
                        parts.append("• " + t)
    if not parts:
        parts.append("لم أجد نتائج محسوبة تتعلق بسؤالك." if ar else "I found no computed results related to your question.")
    footer = ("\n\n— جميع القيم أعلاه مأخوذة من نتائج التحليل المحسوبة فعلياً على بياناتك؛ ولم يُخترع أي رقم." if ar
              else "\n\n— All values above are taken from analyses actually computed on your data; no number was generated.")
    return {"answer": "\n\n".join(parts) + footer, "sources": [s for s in sources if s], "intents": intents}
