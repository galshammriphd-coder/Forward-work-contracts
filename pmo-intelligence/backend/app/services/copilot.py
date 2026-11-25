"""AI PMO Copilot: platform-wide assistant. It only ever sees the projects the asking
user may access, and labels every block by where it came from:
  system      – records in the database        calculated – output of the engines
  documented  – retrieved from documents (RAG)  analysis   – generated recommendations"""
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m, security
from ..rag import answer as rag_answer
from ..rag.text import detect_language, normalize, tokens
from . import core


def _name(p, ar):
    return (p["name_ar"] if ar else p["name_en"]) or p["name_ar"] or p["name_en"]


def _recs(c: dict, ar: bool) -> list[str]:
    mt, out = c["metrics"], []
    e = mt["evm"]
    if mt["critical_late"]:
        out.append(f"{mt['critical_late']} نشاط حرج متأخر: أعد توزيع الموارد عليها أو قصّر الأنشطة اللاحقة، ثم أعد حساب الجدول." if ar else f"{mt['critical_late']} late critical activities: move resources onto them or compress their successors, then recalculate.")
    if e["SPI"] is not None and e["SPI"] < 0.9:
        out.append(f"SPI = {e['SPI']}: الإنجاز متأخر عن المخطط بـ {mt['planned_progress'] - mt['progress']:.0f} نقطة؛ اطلب خطة استدراك من مدير المشروع." if ar else f"SPI = {e['SPI']}: progress trails plan by {mt['planned_progress'] - mt['progress']:.0f} points; ask the project manager for a recovery plan.")
    if mt["over_budget"]:
        out.append(f"المصروف تجاوز الميزانية بـ {mt['actual'] - mt['budget']:,.0f}: أوقف الالتزامات الجديدة واعرض الخيارات على المراقب المالي." if ar else f"Spend exceeds budget by {mt['actual'] - mt['budget']:,.0f}: freeze new commitments and take options to the financial controller.")
    elif e["CPI"] is not None and e["CPI"] < 0.9:
        out.append(f"CPI = {e['CPI']}: التكلفة المتوقعة عند الإنجاز {e['EAC']:,.0f} مقابل ميزانية {mt['budget']:,.0f}." if ar else f"CPI = {e['CPI']}: estimate at completion {e['EAC']:,.0f} against a budget of {mt['budget']:,.0f}.")
    if mt["risk_counts"]["critical"]:
        out.append(f"{mt['risk_counts']['critical']} خطر حرج مفتوح: تحقق من تنفيذ خطط المعالجة هذا الأسبوع." if ar else f"{mt['risk_counts']['critical']} open critical risk(s): verify mitigation is being executed this week.")
    if c.get("needs_intervention"):
        out.append(("يتطلب قراراً تنفيذياً: " if ar else "Needs an executive decision: ") + (c.get("intervention_reason") or ""))
    return out


def recommendations_text(db: Session, project: m.Project, lang: str) -> str:
    ar = lang == "ar"
    recs = _recs(core.project_card(db, project), ar)
    head = "توصيات مولدة من المؤشرات:" if ar else "Recommendations generated from the indicators:"
    return head + "\n" + ("\n".join(f"• {r}" for r in recs) if recs else ("• لا إجراءات تصحيحية مطلوبة حالياً." if ar else "• No corrective action needed right now."))


def project_brief(db: Session, project: m.Project, lang: str) -> str:
    ar = lang == "ar"
    mt = core.project_metrics(db, project)
    e = mt["evm"]
    line = (f"{project.name_ar}: الإنجاز {mt['progress']}% (المخطط {mt['planned_progress']}%)، SPI {e['SPI']}، CPI {e['CPI']}، مخاطر حرجة {mt['risk_counts']['critical']}."
            if ar else f"{project.name_en}: progress {mt['progress']}% (planned {mt['planned_progress']}%), SPI {e['SPI']}, CPI {e['CPI']}, critical risks {mt['risk_counts']['critical']}.")
    return line + "\n" + recommendations_text(db, project, lang)


def _priority_score(c: dict) -> float:
    mt = c["metrics"]
    e = mt["evm"]
    s = 0.0
    s += 30 * max(0, 1 - (e["SPI"] if e["SPI"] is not None else 1))
    s += 30 * max(0, 1 - (e["CPI"] if e["CPI"] is not None else 1))
    s += 6 * mt["risk_counts"]["critical"] + 2 * mt["risk_counts"]["high"] + 4 * mt["critical_late"]
    s += 15 if mt["over_budget"] else 0
    s += 20 if c.get("needs_intervention") else 0
    s *= {"high": 1.3, "critical": 1.5, "low": 0.8}.get(c.get("priority"), 1)
    return round(s, 1)


def ask(db: Session, user: m.User, question: str) -> dict:
    lang = detect_language(question)
    ar = lang == "ar"
    n = normalize(question)
    qt = set(tokens(question))
    projects = core.visible_projects(db, user)
    if not projects:
        return {"lang": lang, "blocks": [{"kind": "system", "text": "لا توجد مشاريع ضمن صلاحياتك." if ar else "There are no projects in your scope."}], "citations": []}
    cards = [core.project_card(db, p) for p in projects]
    live = [c for c in cards if c["status"] not in ("completed", "cancelled")]
    blocks, citations = [], []
    H = lambda a, e: a if ar else e
    f = lambda v, d=2: "—" if v is None else (f"{v:,.0f}" if d == 0 else f"{v:.{d}f}")

    def table(text, head, rows, kind="system"):
        blocks.append({"kind": kind, "text": text, "table": {"head": head, "rows": rows}})

    named = [c for c in cards if (c["code"] and c["code"].lower() in question.lower())
             or len(set(tokens(c["name_ar"] or "")) & qt) >= 2 or len(set(tokens(c["name_en"] or "")) & qt) >= 2]

    if re.search("قارن|مقارنه|compare|versus| vs ", n) and len(named) >= 2:
        table(H("مقارنة المشاريع (مؤشرات محسوبة):", "Project comparison (calculated indicators):"),
              [H("المؤشر", "Indicator")] + [_name(c, ar) for c in named],
              [[H("الإنجاز %", "Progress %")] + [c["metrics"]["progress"] for c in named],
               [H("المخطط %", "Planned %")] + [c["metrics"]["planned_progress"] for c in named],
               ["SPI"] + [f(c["metrics"]["evm"]["SPI"]) for c in named], ["CPI"] + [f(c["metrics"]["evm"]["CPI"]) for c in named],
               [H("الميزانية", "Budget")] + [f(c["budget"], 0) for c in named],
               [H("المصروف", "Actual")] + [f(c["metrics"]["actual"], 0) for c in named],
               [H("مخاطر حرجة", "Critical risks")] + [c["metrics"]["risk_counts"]["critical"] for c in named],
               [H("أنشطة متأخرة", "Late activities")] + [c["metrics"]["late_activities"] for c in named]], "calculated")
        worst = max(named, key=_priority_score)
        blocks.append({"kind": "analysis", "text": H(f"الأولى بالمتابعة: {_name(worst, ar)}.", f"Needs the most attention: {_name(worst, ar)}.") + "\n" + "\n".join(f"• {r}" for r in _recs(worst, ar))})
    elif re.search("اولوي|تدخل|priorit|intervention|attention|where should", n):
        ranked = sorted(live, key=_priority_score, reverse=True)[:5]
        table(H("أولويات التدخل — مرتبة بدرجة محسوبة من SPI و CPI والمخاطر والتأخير:", "Intervention priorities — ranked by a score computed from SPI, CPI, risks and delays:"),
              [H("المشروع", "Project"), H("الدرجة", "Score"), "SPI", "CPI", H("مخاطر حرجة", "Critical risks"), H("أنشطة حرجة متأخرة", "Late critical activities")],
              [[_name(c, ar), _priority_score(c), f(c["metrics"]["evm"]["SPI"]), f(c["metrics"]["evm"]["CPI"]), c["metrics"]["risk_counts"]["critical"], c["metrics"]["critical_late"]] for c in ranked], "calculated")
        lines = [f"{_name(c, ar)}: " + (_recs(c, ar) or [H("راقب فقط.", "Monitor only.")])[0] for c in ranked[:3]]
        blocks.append({"kind": "analysis", "text": H("الإجراء المقترح لكل مشروع:", "Suggested action per project:") + "\n" + "\n".join(f"• {x}" for x in lines)})
    elif "delay" in qt or re.search("متعثر|behind schedule|slipp", n):
        late = sorted([c for c in live if c["metrics"]["late_activities"]], key=lambda c: -c["metrics"]["critical_late"])
        table(H(f"المشاريع التي لديها أنشطة متأخرة: {len(late)}", f"Projects with late activities: {len(late)}"),
              [H("المشروع", "Project"), H("أنشطة متأخرة", "Late activities"), H("منها حرجة", "Critical"), "SPI", H("انحراف الانتهاء (يوم)", "Finish variance (days)")],
              [[_name(c, ar), c["metrics"]["late_activities"], c["metrics"]["critical_late"], f(c["metrics"]["evm"]["SPI"]), c["metrics"]["schedule_variance_days"]] for c in late])
    elif "risk" in qt:
        ids = [c["id"] for c in live]
        rs = sorted(db.scalars(select(m.Risk).where(m.Risk.project_id.in_(ids), m.Risk.status != "closed")), key=lambda r: -(r.score or 0))
        seen, top = set(), []
        for r in rs:  # a shared risk is listed once
            k = r.shared_key or r.id
            if k not in seen:
                seen.add(k)
                top.append(r)
        code = {c["id"]: c for c in cards}
        table(H(f"أعلى المخاطر عبر {len(live)} مشروعاً (المخاطر المشتركة تُحتسب مرة واحدة):", f"Top risks across {len(live)} projects (shared risks counted once):"),
              [H("الخطر", "Risk"), H("المشروع", "Project"), H("الدرجة", "Score"), H("المستوى", "Level"), H("المالك", "Owner")],
              [[r.title, _name(code[r.project_id], ar), r.score, r.level, r.owner_name or "—"] for r in top[:8]])
        cats: dict = {}
        for r in top:
            cats[r.category or "—"] = cats.get(r.category or "—", 0) + 1
        common = sorted(cats.items(), key=lambda x: -x[1])[:3]
        blocks.append({"kind": "analysis", "text": H("نمط متكرر: أكثر فئات المخاطر تكراراً هي ", "Recurring pattern: the most frequent risk categories are ") + "، ".join(f"{k} ({v})" for k, v in common) + "."})
    elif qt & {"budget", "expense"} or re.search("مالي|financ|cpi", n):
        rows = sorted(live, key=lambda c: (c["metrics"]["evm"]["CPI"] if c["metrics"]["evm"]["CPI"] is not None else 9))
        table(H("الأداء المالي للمشاريع الجارية:", "Financial performance of running projects:"),
              [H("المشروع", "Project"), H("الميزانية", "Budget"), H("المصروف", "Actual"), H("الالتزامات", "Committed"), "CPI", "EAC"],
              [[_name(c, ar), f(c["budget"], 0), f(c["metrics"]["actual"], 0), f(c["metrics"]["committed"], 0), f(c["metrics"]["evm"]["CPI"]), f(c["metrics"]["evm"]["EAC"], 0)] for c in rows], "calculated")
        over = [c for c in rows if c["metrics"]["over_budget"]]
        if over:
            blocks.append({"kind": "analysis", "text": H("تجاوزت الميزانية: ", "Over budget: ") + "، ".join(_name(c, ar) for c in over)})
    elif re.search("نمط|انماط|متكرر|pattern|recurring", n):
        late_ph: dict = {}
        for c in live:
            for a in db.scalars(select(m.Activity).where(m.Activity.project_id == c["id"])):
                if a.planned_end and a.planned_end.isoformat() < c["metrics"]["data_date"] and (a.progress or 0) < 100 and a.phase_id:
                    ph = db.get(m.ProjectPhase, a.phase_id)
                    late_ph[ph.name] = late_ph.get(ph.name, 0) + 1
        lessons = list(db.scalars(select(m.LessonLearned).where(m.LessonLearned.project_id.in_([c["id"] for c in cards]))))
        cats: dict = {}
        for l in lessons:
            cats[l.category or "—"] = cats.get(l.category or "—", 0) + 1
        table(H("أين يتكرر التأخير — عدد الأنشطة المتأخرة حسب المرحلة:", "Where delay recurs — late activities by phase:"),
              [H("المرحلة", "Phase"), H("أنشطة متأخرة", "Late activities")], sorted(late_ph.items(), key=lambda x: -x[1])[:6] or [["—", 0]])
        if cats:
            table(H("موضوعات الدروس المستفادة الأكثر تكراراً:", "Most frequent lessons-learned themes:"),
                  [H("الفئة", "Category"), H("عدد الدروس", "Lessons")], sorted(cats.items(), key=lambda x: -x[1])[:5])
    elif named:
        c = named[0]
        mt, e = c["metrics"], c["metrics"]["evm"]
        table(H(f"وضع {_name(c, ar)} ({mt['data_date']}):", f"Status of {_name(c, ar)} ({mt['data_date']}):"), [H("المؤشر", "Indicator"), H("القيمة", "Value")],
              [[H("الحالة", "Status"), c["status"]], [H("الإنجاز / المخطط %", "Progress / planned %"), f"{mt['progress']} / {mt['planned_progress']}"],
               ["SPI", f(e["SPI"])], ["CPI", f(e["CPI"])], [H("الميزانية", "Budget"), f(mt["budget"], 0)], [H("المصروف", "Actual"), f(mt["actual"], 0)],
               [H("الانتهاء المتوقع", "Forecast finish"), mt["forecast_finish"]], [H("مخاطر حرجة", "Critical risks"), mt["risk_counts"]["critical"]]], "calculated")
        recs = _recs(c, ar)
        if recs:
            blocks.append({"kind": "analysis", "text": H("إجراءات تصحيحية مقترحة:", "Suggested corrective actions:") + "\n" + "\n".join(f"• {r}" for r in recs)})
        if security.has(user, "docs.read"):
            res = rag_answer.answer(db, user, c["id"], question, core.get_settings(db)["ai"])
            if res["grounded"]:
                blocks.append({"kind": "documented", "text": res["blocks"][0]["text"]})
                citations = res["citations"]
    else:
        d = core.dashboard(db, user)
        k = d["kpis"]
        table(H(f"ملخص المحفظة ضمن صلاحياتك ({d['as_of']}):", f"Portfolio summary within your scope ({d['as_of']}):"), [H("المؤشر", "Indicator"), H("القيمة", "Value")],
              [[H("إجمالي المشاريع", "Total projects"), k["total"]], [H("النشطة", "Active"), k["active"]], [H("المتأخرة", "Delayed"), k["delayed"]],
               [H("عالية المخاطر", "High risk"), k["high_risk"]], [H("تتطلب تدخلاً", "Need intervention"), k["needs_intervention"]],
               [H("الميزانية المعتمدة", "Approved budget"), f(k["budget"], 0)], [H("المصروف الفعلي", "Actual spend"), f(k["actual"], 0)],
               [H("نسبة الإنجاز الكلية %", "Overall progress %"), k["progress"]], [H("أداء المحفظة (من 100)", "Portfolio score (of 100)"), k["portfolio_score"]]], "calculated")
        ranked = sorted(live, key=_priority_score, reverse=True)[:3]
        blocks.append({"kind": "analysis", "text": H("الأولى بالمتابعة: ", "Watch first: ") + "، ".join(_name(c, ar) for c in ranked) + ".\n" +
                       "\n".join(f"• {_name(c, ar)}: {(_recs(c, ar) or [H('راقب فقط.', 'Monitor only.')])[0]}" for c in ranked)})
    security.audit(db, user, "copilot.ask", "copilot", None, None, {"question": question[:300], "projects_in_scope": len(projects)})
    return {"lang": lang, "blocks": blocks, "citations": citations, "scope_projects": len(projects)}
