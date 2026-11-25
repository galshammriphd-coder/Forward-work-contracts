"""Report builder: one structured report model, rendered to JSON (screen), XLSX, DOCX and PDF,
in Arabic or English. All numbers come from the same engines the screens use."""
from __future__ import annotations

import io
import os
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import core

TYPES = {
    "executive_portfolio": ("التقرير التنفيذي للمحفظة", "Executive Portfolio Report", False),
    "project_status": ("تقرير حالة المشروع", "Project Status Report", True),
    "project_progress": ("تقرير تقدم المشروع", "Project Progress Report", True),
    "project_financial": ("التقرير المالي للمشروع", "Project Financial Report", True),
    "risk": ("تقرير إدارة المخاطر", "Risk Management Report", False),
    "schedule_performance": ("تقرير أداء الجدول الزمني", "Schedule Performance Report", True),
    "resource_utilization": ("تقرير استغلال الموارد", "Resource Utilization Report", False),
    "governance_compliance": ("تقرير الالتزام بالحوكمة", "Governance Compliance Report", False),
    "closure": ("تقرير إغلاق المشروع", "Project Closure Report", True),
    "benefits": ("تقرير تحقيق المنافع", "Benefits Realization Report", False),
    "lessons": ("تقرير الدروس المستفادة", "Lessons Learned Report", False),
    "pmo_performance": ("تقرير أداء مكتب إدارة المشاريع", "PMO Performance Report", False),
}


def _n(v, d=0):
    return "—" if v is None else (f"{v:,.{d}f}" if isinstance(v, (int, float)) else str(v))


def benefit_gap(b: m.Benefit) -> dict:
    """Realisation % measured from baseline toward target. Completion of the project plays no part."""
    if b.target is None or b.actual is None:
        return {"realization": None, "gap": None}
    base = b.baseline or 0
    span = b.target - base
    real = ((b.actual - base) / span * 100) if span else (100.0 if b.actual == b.target else 0.0)
    return {"realization": round(max(0.0, real), 1), "gap": round(b.target - b.actual, 2)}


def build(db: Session, user: m.User, rtype: str, lang: str = "ar", project_id: int | None = None,
          portfolio_id: int | None = None, date_from: date | None = None, date_to: date | None = None,
          include: list[str] | None = None, comment: str = "") -> dict:
    if rtype not in TYPES:
        raise ValueError(f"Unknown report type {rtype}")
    ar = lang == "ar"
    T = lambda a, e: a if ar else e
    projects = core.visible_projects(db, user) if user else list(db.scalars(select(m.Project)))
    if portfolio_id:
        projects = [p for p in projects if p.portfolio_id == portfolio_id]
    if project_id:
        projects = [p for p in projects if p.id == project_id]
        if not projects:
            raise LookupError("Project not found")
    if TYPES[rtype][2] and not project_id:
        raise ValueError("This report needs a project")
    cards = [core.project_card(db, p) for p in projects]
    ids = [p.id for p in projects]
    nm = lambda c: (c["name_ar"] if ar else c["name_en"]) or c["name_ar"]
    in_period = lambda d: d is None or ((date_from is None or d >= date_from) and (date_to is None or d <= date_to))
    sections, summary = [], []

    def kpis(title, items):
        sections.append({"key": "kpis", "kind": "kpis", "title": title, "items": [{"label": l, "value": v} for l, v in items]})

    def table(key, title, head, rows, chart=None):
        sections.append({"key": key, "kind": "table", "title": title, "head": head, "rows": rows, "chart": chart})

    def rows_of(model, extra=None):
        q = select(model).where(model.project_id.in_(ids)) if ids else None
        return [r for r in db.scalars(q)] if q is not None else []

    one = cards[0] if project_id else None
    mt = one["metrics"] if one else None

    if rtype in ("executive_portfolio", "pmo_performance"):
        d = core.dashboard(db, user)
        k = d["kpis"]
        kpis(T("مؤشرات المحفظة", "Portfolio indicators"), [
            (T("إجمالي المشاريع", "Total projects"), len(cards)), (T("النشطة", "Active"), sum(c["status"] == "active" for c in cards)),
            (T("المتأخرة", "Delayed"), sum(c["metrics"]["delayed"] for c in cards)),
            (T("الميزانية المعتمدة", "Approved budget"), _n(sum(c["budget"] or 0 for c in cards))),
            (T("المصروف الفعلي", "Actual spend"), _n(sum(c["metrics"]["actual"] for c in cards))),
            (T("أداء المحفظة", "Portfolio score"), k["portfolio_score"])])
        table("projects", T("أداء المشاريع", "Project performance"),
              [T("المشروع", "Project"), T("الحالة", "Status"), T("الإنجاز %", "Progress %"), T("المخطط %", "Planned %"), "SPI", "CPI", T("مخاطر حرجة", "Critical risks")],
              [[nm(c), c["status"], c["metrics"]["progress"], c["metrics"]["planned_progress"], _n(c["metrics"]["evm"]["SPI"], 2), _n(c["metrics"]["evm"]["CPI"], 2), c["metrics"]["risk_counts"]["critical"]] for c in cards],
              chart={"type": "bar", "labels": [c["code"] for c in cards], "series": [{"name": T("الإنجاز %", "Progress %"), "values": [c["metrics"]["progress"] for c in cards]}, {"name": T("المخطط %", "Planned %"), "values": [c["metrics"]["planned_progress"] for c in cards]}]})
        red = [c for c in cards if c["metrics"]["health"] == "red"]
        summary.append(T(f"من {len(cards)} مشروعاً، {len(red)} في وضع حرج و{sum(c['metrics']['health'] == 'amber' for c in cards)} تحتاج متابعة.",
                         f"Of {len(cards)} projects, {len(red)} are in a critical state and {sum(c['metrics']['health'] == 'amber' for c in cards)} need watching."))
        if red:
            summary.append(T("الأكثر حاجة للتدخل: ", "Most in need of intervention: ") + "، ".join(nm(c) for c in red[:4]) + ".")
        if rtype == "pmo_performance":
            appr = rows_of(m.Approval)
            done = [a for a in appr if a.decided_at and a.requested_at]
            avg = sum((a.decided_at - a.requested_at).days for a in done) / len(done) if done else None
            kpis(T("أداء مكتب إدارة المشاريع", "PMO performance"), [
                (T("الالتزام بالجدول %", "Schedule adherence %"), k["schedule_adherence"]), (T("الالتزام بالميزانية %", "Budget adherence %"), k["budget_adherence"]),
                (T("متوسط زمن الاعتماد (يوم)", "Average approval time (days)"), _n(avg, 1)),
                (T("اعتمادات معلقة", "Pending approvals"), sum(a.status == "pending" for a in appr)),
                (T("تنبيهات مفتوحة", "Open alerts"), len(d["alerts"]))])
    if rtype in ("project_status", "project_progress", "closure"):
        e = mt["evm"]
        kpis(T("مؤشرات المشروع", "Project indicators"), [
            (T("الحالة", "Status"), one["status"]), (T("الإنجاز %", "Progress %"), mt["progress"]), (T("المخطط %", "Planned %"), mt["planned_progress"]),
            ("SPI", _n(e["SPI"], 2)), ("CPI", _n(e["CPI"], 2)), (T("الانتهاء المتوقع", "Forecast finish"), mt["forecast_finish"])])
        acts = core.leaf_activities(rows_of(m.Activity))
        if rtype == "project_progress":
            acts = [a for a in acts if in_period(a.planned_start) or in_period(a.planned_end)]
        table("activities", T("الأنشطة", "Activities"),
              [T("الرمز", "WBS"), T("النشاط", "Activity"), T("البداية", "Start"), T("النهاية", "End"), T("الإنجاز %", "Progress %"), T("حرج", "Critical")],
              [[a.wbs_code, a.name, str(a.planned_start), str(a.planned_end), a.progress or 0, T("نعم", "Yes") if a.is_critical else ""] for a in sorted(acts, key=lambda a: a.planned_start or date.min)])
        table("milestones", T("المعالم الرئيسية", "Milestones"), [T("المعلم", "Milestone"), T("المستهدف", "Target"), T("الحالة", "Status")],
              [[x.name, str(x.target_date), x.status] for x in sorted(rows_of(m.Milestone), key=lambda x: x.target_date or date.max)])
        table("issues", T("المشكلات المفتوحة", "Open issues"), [T("المشكلة", "Issue"), T("الأهمية", "Severity"), T("المالك", "Owner")],
              [[i.title, i.severity, i.owner_name or "—"] for i in rows_of(m.Issue) if i.status != "closed"])
        summary.append(T(f"الإنجاز {mt['progress']}% مقابل مخطط {mt['planned_progress']}%؛ {mt['late_activities']} نشاط متأخر منها {mt['critical_late']} حرج.",
                         f"Progress is {mt['progress']}% against {mt['planned_progress']}% planned; {mt['late_activities']} late activities, {mt['critical_late']} of them critical."))
    if rtype in ("project_financial", "project_status", "closure"):
        e = mt["evm"]
        table("evm", T("القيمة المكتسبة", "Earned value"), [T("المؤشر", "Indicator"), T("القيمة", "Value"), T("طريقة الحساب", "Formula")],
              [[k, _n(e[k], 3 if k in ("SPI", "CPI") else 0), e["formulas"][k]] for k in ("PV", "EV", "AC", "SV", "CV", "SPI", "CPI", "EAC", "ETC", "VAC")])
        if rtype == "project_financial":
            buds = rows_of(m.Budget)
            costs = [c for c in rows_of(m.Cost) if in_period(c.cost_date)]
            table("budget", T("الميزانية حسب البند", "Budget by line"), [T("البند", "Line"), T("المخطط", "Planned"), T("المعتمد", "Approved"), T("الفعلي", "Actual"), T("الالتزامات", "Committed")],
                  [[b.category, _n(b.planned_amount), _n(b.approved_amount), _n(sum(c.amount for c in costs if c.budget_id == b.id and c.kind == "actual")),
                    _n(sum(c.amount for c in costs if c.budget_id == b.id and c.kind == "commitment"))] for b in buds])
            table("costs", T("حركات التكلفة", "Cost entries"), [T("التاريخ", "Date"), T("النوع", "Kind"), T("الوصف", "Description"), T("المبلغ", "Amount")],
                  [[str(c.cost_date), c.kind, c.description or "", _n(c.amount)] for c in sorted(costs, key=lambda c: c.cost_date or date.min)])
        if e["CPI"] is not None:
            summary.append(T(f"CPI = {e['CPI']}؛ التكلفة المتوقعة عند الإنجاز {_n(e['EAC'])} مقابل ميزانية {_n(e['BAC'])}.",
                             f"CPI = {e['CPI']}; estimate at completion {_n(e['EAC'])} against a budget of {_n(e['BAC'])}."))
    if rtype in ("risk", "project_status"):
        risks = sorted([r for r in rows_of(m.Risk) if r.status != "closed"], key=lambda r: -(r.score or 0))
        code = {c["id"]: c for c in cards}
        table("risks", T("سجل المخاطر المفتوحة", "Open risk register"),
              [T("المشروع", "Project"), T("الخطر", "Risk"), T("الاحتمالية", "P"), T("الأثر", "I"), T("الدرجة", "Score"), T("المستوى", "Level"), T("المالك", "Owner"), T("المعالجة", "Mitigation")],
              [[code[r.project_id]["code"], r.title, r.probability, r.impact, r.score, r.level, r.owner_name or "—", r.mitigation or "—"] for r in risks[:60]])
        if rtype == "risk":
            lv = {l: sum(r.level == l for r in risks) for l in ("critical", "high", "moderate", "low")}
            kpis(T("توزيع المخاطر", "Risk distribution"), [(T("حرجة", "Critical"), lv["critical"]), (T("عالية", "High"), lv["high"]), (T("متوسطة", "Moderate"), lv["moderate"]), (T("منخفضة", "Low"), lv["low"])])
            summary.append(T(f"{len(risks)} خطراً مفتوحاً، منها {lv['critical']} حرجة و{lv['high']} عالية.", f"{len(risks)} open risks: {lv['critical']} critical and {lv['high']} high."))
    if rtype == "schedule_performance":
        acts = core.leaf_activities(rows_of(m.Activity))
        bl = core.current_baseline(db, project_id)
        snap = (bl.snapshot.get("activities") if bl else {}) or {}
        rows = []
        for a in sorted(acts, key=lambda a: a.planned_start or date.min):
            b = snap.get(str(a.id), {})
            var = (a.planned_end - date.fromisoformat(b["end"])).days if b.get("end") and a.planned_end else None
            rows.append([a.wbs_code, a.name, b.get("end") or "—", str(a.planned_end), _n(var), a.total_float, T("نعم", "Yes") if a.is_critical else ""])
        kpis(T("أداء الجدول", "Schedule performance"), [("SPI", _n(mt["evm"]["SPI"], 2)), (T("انتهاء خط الأساس", "Baseline finish"), mt["baseline_finish"]),
                                                       (T("الانتهاء المتوقع", "Forecast finish"), mt["forecast_finish"]), (T("الانحراف (يوم)", "Variance (days)"), mt["schedule_variance_days"])])
        table("baseline", T("المخطط مقابل خط الأساس", "Plan against baseline"),
              [T("الرمز", "WBS"), T("النشاط", "Activity"), T("نهاية خط الأساس", "Baseline end"), T("النهاية الحالية", "Current end"), T("الانحراف", "Variance"), T("الفائض", "Float"), T("حرج", "Critical")], rows)
        summary.append(T(f"الانتهاء المتوقع {mt['forecast_finish']} مقابل خط الأساس {mt['baseline_finish']} (انحراف {mt['schedule_variance_days']} يوماً).",
                         f"Forecast finish {mt['forecast_finish']} against baseline {mt['baseline_finish']} ({mt['schedule_variance_days']} days variance)."))
    if rtype == "resource_utilization":
        util = resource_utilization(db, ids)
        table("resources", T("استغلال الموارد", "Resource utilization"), [T("المورد", "Resource"), T("الفريق", "Team"), T("الطاقة %", "Capacity %"), T("التحميل الحالي %", "Current load %"), T("المشاريع", "Projects")],
              [[r["name"], r["team"] or "—", r["capacity_pct"], r["load"], r["projects"]] for r in util],
              chart={"type": "bar", "labels": [r["name"] for r in util], "series": [{"name": T("التحميل %", "Load %"), "values": [r["load"] for r in util]}]})
        over = [r for r in util if r["load"] > r["capacity_pct"]]
        summary.append(T(f"{len(over)} مورد محمّل فوق طاقته من أصل {len(util)}.", f"{len(over)} of {len(util)} resources are over capacity."))
    if rtype == "governance_compliance":
        appr = rows_of(m.Approval)
        gates = rows_of(m.ProjectPhase)
        today = date.today()
        code = {c["id"]: c for c in cards}
        kpis(T("الالتزام بالحوكمة", "Governance compliance"), [
            (T("اعتمادات معلقة", "Pending approvals"), sum(a.status == "pending" for a in appr)),
            (T("اعتمادات متأخرة", "Overdue approvals"), sum(a.status == "pending" and a.due_date and a.due_date < today for a in appr)),
            (T("بوابات معتمدة", "Gates approved"), sum(g.gate_status == "approved" for g in gates)),
            (T("مشاريع بلا خط أساس", "Projects without a baseline"), sum(core.current_baseline(db, i) is None for i in ids))])
        table("approvals", T("الاعتمادات", "Approvals"), [T("المشروع", "Project"), T("الاعتماد", "Approval"), T("الحالة", "Status"), T("الاستحقاق", "Due")],
              [[code[a.project_id]["code"] if a.project_id in code else "—", a.title, a.status, str(a.due_date)] for a in appr])
        stale = [c for c in cards if c["status"] == "active" and c["last_update_at"] and (datetime.utcnow() - datetime.fromisoformat(c["last_update_at"])).days > 14]
        summary.append(T(f"{len(stale)} مشروع نشط بلا تحديث منذ أكثر من 14 يوماً.", f"{len(stale)} active project(s) with no update for more than 14 days."))
    if rtype in ("benefits", "closure"):
        bens = rows_of(m.Benefit)
        code = {c["id"]: c for c in cards}
        rows = []
        for b in bens:
            g = benefit_gap(b)
            rows.append([code[b.project_id]["code"], b.name, b.metric or "", _n(b.baseline, 1), _n(b.target, 1), _n(b.actual, 1), _n(g["realization"], 1), b.status])
        table("benefits", T("المنافع", "Benefits"), [T("المشروع", "Project"), T("المنفعة", "Benefit"), T("المقياس", "Metric"), T("خط الأساس", "Baseline"), T("المستهدف", "Target"), T("المتحقق", "Actual"), T("التحقق %", "Realised %"), T("الحالة", "Status")], rows)
        value = sum(b.monetary_value or 0 for b in bens)
        cost = sum(c["metrics"]["actual"] for c in cards if any(b.project_id == c["id"] and b.monetary_value for b in bens))
        if value and cost:
            kpis(T("العائد على الاستثمار", "Return on investment"), [(T("القيمة المالية المتحققة", "Realised financial value"), _n(value)), (T("التكلفة الفعلية", "Actual cost"), _n(cost)),
                                                                    ("ROI %", _n((value - cost) / cost * 100, 1))])
        measured = [b for b in bens if b.actual is not None]
        summary.append(T(f"{len(measured)} من {len(bens)} منفعة لها قياس فعلي. اكتمال المشروع لا يعني تحقق المنفعة: ما لم يُقَس يبقى «غير متحقق».",
                         f"{len(measured)} of {len(bens)} benefits have an actual measurement. A finished project is not a realised benefit: anything unmeasured stays “not realised”."))
    if rtype in ("lessons", "closure"):
        les = [l for l in db.scalars(select(m.LessonLearned)) if l.project_id in ids]
        code = {c["id"]: c for c in cards}
        table("lessons", T("الدروس المستفادة", "Lessons learned"), [T("المشروع", "Project"), T("الفئة", "Category"), T("الدرس", "Lesson"), T("التوصية", "Recommendation")],
              [[code[l.project_id]["code"], l.category or "—", l.title, l.recommendation or ""] for l in les])
    if include:
        sections = [s for s in sections if s["key"] in include or s["key"] == "kpis"]
    scope = nm(one) if one else T(f"{len(cards)} مشروعاً", f"{len(cards)} projects")
    period = f"{date_from or '…'} → {date_to or '…'}" if (date_from or date_to) else ""
    return {"type": rtype, "lang": lang, "title": T(*TYPES[rtype][:2]), "scope": scope, "period": period,
            "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"), "summary": summary, "comment": comment,
            "summary_label": T("ملخص ذكي (مولد من المؤشرات)", "Smart summary (generated from the indicators)"),
            "comment_label": T("تعليق تنفيذي", "Executive comment"), "sections": sections}


def resource_utilization(db: Session, project_ids: list[int] | None = None, today: date | None = None) -> list[dict]:
    today = today or date.today()
    out = []
    for r in db.scalars(select(m.Resource).order_by(m.Resource.name)):
        assigns = [a for a in db.scalars(select(m.ResourceAssignment).where(m.ResourceAssignment.resource_id == r.id))
                   if (a.start_date is None or a.start_date <= today) and (a.end_date is None or a.end_date >= today)]
        if project_ids is not None and not any(a.project_id in project_ids for a in assigns) and assigns:
            continue
        load = sum(a.allocation_pct or 0 for a in assigns)
        out.append({**core.to_dict(r), "load": load, "projects": len({a.project_id for a in assigns}),
                    "conflict": load > (r.capacity_pct or 100), "free": max(0, (r.capacity_pct or 100) - load),
                    "assignments": [core.to_dict(a) for a in assigns]})
    return out


# ---------- renderers ----------
def to_xlsx(rep: dict) -> bytes:
    import openpyxl
    from openpyxl.chart import BarChart, Reference
    from openpyxl.styles import Alignment, Font, PatternFill
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Summary"
    rtl = rep["lang"] == "ar"
    ws.sheet_view.rightToLeft = rtl
    ws.append([rep["title"]]); ws["A1"].font = Font(size=16, bold=True)
    ws.append([rep["scope"], rep["period"], rep["generated_at"]])
    ws.append([])
    ws.append([rep["summary_label"]]); ws.cell(ws.max_row, 1).font = Font(bold=True)
    for s in rep["summary"]:
        ws.append([s])
    if rep["comment"]:
        ws.append([]); ws.append([rep["comment_label"]]); ws.cell(ws.max_row, 1).font = Font(bold=True); ws.append([rep["comment"]])
    for s in rep["sections"]:
        if s["kind"] == "kpis":
            ws.append([]); ws.append([s["title"]]); ws.cell(ws.max_row, 1).font = Font(bold=True)
            for it in s["items"]:
                ws.append([it["label"], it["value"]])
    ws.column_dimensions["A"].width = 60
    used = set()
    for s in rep["sections"]:
        if s["kind"] != "table":
            continue
        name = s["title"][:28].replace("/", "-")
        while name in used:
            name += "_"
        used.add(name)
        sh = wb.create_sheet(name)
        sh.sheet_view.rightToLeft = rtl
        sh.append(s["head"])
        for c in sh[1]:
            c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="14343B"); c.alignment = Alignment(wrap_text=True)
        for r in s["rows"]:
            sh.append(r)
        for i, _ in enumerate(s["head"], 1):
            sh.column_dimensions[openpyxl.utils.get_column_letter(i)].width = 22
        ch = s.get("chart")
        if ch and s["rows"]:
            base = len(s["head"]) + 2
            sh.cell(1, base, "label")
            for j, se in enumerate(ch["series"]):
                sh.cell(1, base + 1 + j, se["name"])
            for i, lab in enumerate(ch["labels"]):
                sh.cell(2 + i, base, lab)
                for j, se in enumerate(ch["series"]):
                    sh.cell(2 + i, base + 1 + j, se["values"][i])
            bc = BarChart(); bc.title = s["title"]; bc.height, bc.width = 8, 18
            bc.add_data(Reference(sh, min_col=base + 1, max_col=base + len(ch["series"]), min_row=1, max_row=1 + len(ch["labels"])), titles_from_data=True)
            bc.set_categories(Reference(sh, min_col=base, min_row=2, max_row=1 + len(ch["labels"])))
            sh.add_chart(bc, f"{openpyxl.utils.get_column_letter(base + len(ch['series']) + 2)}2")
    buf = io.BytesIO(); wb.save(buf)
    return buf.getvalue()


def to_docx(rep: dict) -> bytes:
    import docx
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    rtl = rep["lang"] == "ar"
    d = docx.Document()

    def para(text, style=None, bold=False):
        p = d.add_paragraph(style=style)
        run = p.add_run(str(text)); run.bold = bold
        if rtl:
            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            bidi = OxmlElement("w:bidi"); p._p.get_or_add_pPr().append(bidi)
            rpr = run._r.get_or_add_rPr(); r = OxmlElement("w:rtl"); rpr.append(r)
        return p

    para(rep["title"], "Title")
    para(" | ".join(x for x in (rep["scope"], rep["period"], rep["generated_at"]) if x))
    para(rep["summary_label"], "Heading 2")
    for s in rep["summary"]:
        para(s, "List Bullet")
    if rep["comment"]:
        para(rep["comment_label"], "Heading 2"); para(rep["comment"])
    for s in rep["sections"]:
        para(s["title"], "Heading 2")
        head = s["head"] if s["kind"] == "table" else ["", ""]
        rows = s["rows"] if s["kind"] == "table" else [[i["label"], i["value"]] for i in s["items"]]
        if not rows:
            para("—"); continue
        t = d.add_table(rows=1 if s["kind"] == "table" else 0, cols=len(head)); t.style = "Light Grid Accent 1"
        if rtl:
            tblPr = t._tbl.tblPr; b = OxmlElement("w:bidiVisual"); b.set(qn("w:val"), "1"); tblPr.append(b)
        if s["kind"] == "table":
            for i, h in enumerate(head):
                t.rows[0].cells[i].text = str(h)
        for r in rows:
            cells = t.add_row().cells
            for i, v in enumerate(r[:len(head)]):
                cells[i].text = "" if v is None else str(v)
    buf = io.BytesIO(); d.save(buf)
    return buf.getvalue()


_FONT_CANDIDATES = [os.environ.get("PMO_PDF_FONT", ""), "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                    "/usr/share/fonts/dejavu/DejaVuSans.ttf", "/usr/share/fonts/TTF/DejaVuSans.ttf",
                    "/Library/Fonts/Arial Unicode.ttf", "C:/Windows/Fonts/arial.ttf"]


def to_pdf(rep: dict) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    font = "Helvetica"
    for path in _FONT_CANDIDATES:
        if path and os.path.exists(path):
            if "PMOFont" not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont("PMOFont", path))
            font = "PMOFont"
            break
    rtl = rep["lang"] == "ar"

    def sh(text):
        text = "" if text is None else str(text)
        if rtl and any("\u0600" <= ch <= "\u06FF" for ch in text):
            import arabic_reshaper
            from bidi.algorithm import get_display
            return get_display(arabic_reshaper.reshape(text))
        return text

    al = TA_RIGHT if rtl else TA_LEFT
    st = lambda size, lead=None, color="#14343B": ParagraphStyle("s", fontName=font, fontSize=size, leading=lead or size * 1.5, alignment=al, textColor=colors.HexColor(color))
    cell = ParagraphStyle("c", fontName=font, fontSize=7.5, leading=10, alignment=al)
    esc = lambda t: sh(t).replace("&", "&amp;").replace("<", "&lt;")
    flow = [Paragraph(esc(rep["title"]), st(18)), Paragraph(esc(" | ".join(x for x in (rep["scope"], rep["period"], rep["generated_at"]) if x)), st(9, color="#5B6B6E")),
            Spacer(1, 10), Paragraph(esc(rep["summary_label"]), st(12))]
    flow += [Paragraph(esc("• " + s), st(9.5, color="#1E2A2C")) for s in rep["summary"]]
    if rep["comment"]:
        flow += [Spacer(1, 6), Paragraph(esc(rep["comment_label"]), st(12)), Paragraph(esc(rep["comment"]), st(9.5, color="#1E2A2C"))]
    for s in rep["sections"]:
        flow += [Spacer(1, 12), Paragraph(esc(s["title"]), st(12))]
        head = s["head"] if s["kind"] == "table" else None
        rows = s["rows"] if s["kind"] == "table" else [[i["label"], i["value"]] for i in s["items"]]
        if not rows:
            flow.append(Paragraph("—", cell)); continue
        data = ([head] if head else []) + rows[:200]
        data = [[Paragraph(esc(v), cell) for v in (list(reversed(r)) if rtl else r)] for r in data]
        t = Table(data, repeatRows=1 if head else 0, hAlign="RIGHT" if rtl else "LEFT")
        style = [("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#C9D3D3")), ("VALIGN", (0, 0), (-1, -1), "TOP")]
        if head:
            style += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E4ECEC"))]
        t.setStyle(TableStyle(style))
        flow.append(t)
    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=28, rightMargin=28, topMargin=28, bottomMargin=28, title=rep["title"]).build(flow)
    return buf.getvalue()


RENDER = {"xlsx": (to_xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
          "docx": (to_docx, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
          "pdf": (to_pdf, "application/pdf")}


def to_markdown(rep: dict) -> str:
    out = [f"# {rep['title']}", "", f"{rep['scope']} | {rep['generated_at']}", "", f"## {rep['summary_label']}"] + [f"- {s}" for s in rep["summary"]]
    for s in rep["sections"]:
        out += ["", f"## {s['title']}"]
        if s["kind"] == "kpis":
            out += [f"{i['label']}: {i['value']}" for i in s["items"]]
        else:
            out += [" | ".join(map(str, s["head"]))] + [" | ".join("" if v is None else str(v) for v in r) for r in s["rows"]]
    return "\n".join(out) + "\n"


def save_as_document(db: Session, project: m.Project, rtype: str, lang: str) -> m.Document:
    """Store a generated report in the project's knowledge base (so it is searchable)."""
    from . import knowledge
    rep = build(db, None, rtype, lang, project_id=project.id)
    return knowledge.save_upload(db, None, project, f"{rtype}_{date.today()}.md", to_markdown(rep).encode("utf-8"),
                                 name=f"{rep['title']} — {date.today()}", doc_type="progress_report" if rtype != "closure" else "other",
                                 doc_date=date.today(), folder="/reports", tags=["generated", rtype], source_tag="calculated", fire_event=False)


def run_schedule(db: Session, s: m.ReportSchedule):
    target = db.get(m.Project, s.project_id) if s.project_id else None
    title = TYPES[s.report_type][0]
    if target:
        doc = save_as_document(db, target, s.report_type, s.lang)
        body = f"حُفظ في وثائق المشروع (وثيقة {doc.id})."
    else:
        body = "جاهز للتنزيل من صفحة التقارير."
    core.notify(db, s.recipient_roles or ["pmo_director"], target, f"تقرير دوري: {title}", body, "informational")
    s.last_run_at = datetime.utcnow()
    db.flush()
