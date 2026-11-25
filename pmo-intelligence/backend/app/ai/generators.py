"""Generators for the initiation wizard. Everything produced here is a *proposal*
tagged "ai" (or "calculated" for engine output) and stays a draft until a person approves it."""
from __future__ import annotations

from datetime import date, timedelta

from ..engines import risk as risk_engine
from ..engines import scheduling

PHASES = [("init", "التهيئة والانطلاق", "Initiation & mobilisation", 0.10),
          ("plan", "التخطيط والتصميم", "Planning & design", 0.20),
          ("exec", "التنفيذ والتسليم", "Execution & delivery", 0.50),
          ("accept", "الاختبار والقبول", "Testing & acceptance", 0.13),
          ("close", "الإغلاق ونقل المعرفة", "Closure & handover", 0.07)]


def _val(draft, f, default=None):
    v = draft["profile"].get(f)
    return v["value"] if v else default


def generate_wbs(draft: dict, calendar: scheduling.Calendar) -> dict:
    ar = draft.get("language") == "ar"
    T = lambda a, e: a if ar else e
    start = date.fromisoformat(_val(draft, "start_date")) if _val(draft, "start_date") else None
    end = date.fromisoformat(_val(draft, "end_date")) if _val(draft, "end_date") else None
    assumed = []
    if start and end and end > start:
        work = max(20, calendar.working_days_between(start, end))
    else:
        work = 120
        assumed.append(T("لم يحدد الميثاق تاريخي البداية والنهاية؛ افتُرضت مدة 120 يوم عمل.",
                         "The charter gives no start/end dates; 120 working days were assumed."))
    delivs = [d["text"] for d in draft["lists"].get("deliverables", [])]
    if not delivs:
        delivs = [T("المخرج الرئيسي للمشروع", "Main project deliverable")]
        assumed.append(T("لم يذكر الميثاق مخرجات؛ أضيف مخرج عام يحتاج إلى تحديد.",
                         "The charter lists no deliverables; one generic deliverable was added and needs defining."))
    manager = _val(draft, "manager", "")
    phases, wbs, acts = [], [], []
    seq = {"n": 0}

    def act(phase, wbs_key, name, dur, deps=(), parent=None, deliverable=None, criteria="", prio="medium", res=""):
        seq["n"] += 1
        key = f"A{seq['n']}"
        acts.append({"key": key, "code": f"ACT-{seq['n']:03d}", "phase": phase, "wbs": wbs_key, "parent": parent,
                     "deliverable": deliverable, "name": name, "description": "", "duration_days": max(1, round(dur)),
                     "deps": [{"pred": d[0], "type": d[1] if len(d) > 1 else "FS", "lag": d[2] if len(d) > 2 else 0} for d in deps],
                     "priority": prio, "responsible_name": manager, "supporting_team": "",
                     "required_resources": res, "estimated_cost": 0, "completion_criteria": criteria,
                     "weight": 0, "status": "not_started", "progress": 0, "tag": "ai"})
        return key

    days = {k: max(2, round(work * share)) for k, _, _, share in PHASES}
    for i, (k, a, e, _) in enumerate(PHASES, 1):
        phases.append({"key": k, "name": T(a, e), "order": i, "tag": "ai"})
        wbs.append({"key": k, "parent": None, "code": str(i), "name": T(a, e), "kind": "phase", "phase": k, "tag": "ai"})

    def wp(phase, idx, name, kind="work_package", parent=None, deliverable=None):
        code = f"{[p[0] for p in PHASES].index(phase) + 1}.{idx}" if parent is None else f"{parent['code']}.{idx}"
        node = {"key": f"W{len(wbs)}", "parent": parent["key"] if parent else phase, "code": code, "name": name,
                "kind": kind, "phase": phase, "deliverable": deliverable, "tag": "ai"}
        wbs.append(node)
        return node

    w = wp("init", 1, T("حوكمة المشروع وتعبئة الفريق", "Governance & team mobilisation"))
    a1 = act("init", w["key"], T("اجتماع الانطلاق وتعبئة الفريق", "Kick-off meeting and team mobilisation"), days["init"] * 0.4,
             criteria=T("محضر اجتماع الانطلاق معتمد", "Kick-off minutes approved"), prio="high")
    a2 = act("init", w["key"], T("اعتماد هيكل الحوكمة وسجل أصحاب المصلحة", "Approve governance structure and stakeholder register"),
             days["init"] * 0.6, [(a1,)], criteria=T("سجل أصحاب المصلحة ومصفوفة RACI معتمدان", "Stakeholder register and RACI approved"))
    w = wp("plan", 1, T("المتطلبات وخط أساس النطاق", "Requirements & scope baseline"))
    a3 = act("plan", w["key"], T("جمع المتطلبات التفصيلية وتوثيقها", "Elicit and document detailed requirements"), days["plan"] * 0.4,
             [(a2,)], criteria=T("وثيقة المتطلبات موقعة من مالك الأعمال", "Requirements document signed by the business owner"), prio="high")
    w = wp("plan", 2, T("التصميم وخطة إدارة المشروع", "Design & project management plan"))
    a4 = act("plan", w["key"], T("إعداد التصميم التفصيلي ومنهجية التنفيذ", "Prepare detailed design and delivery approach"), days["plan"] * 0.4,
             [(a3,)], criteria=T("وثيقة التصميم معتمدة", "Design document approved"))
    a5 = act("plan", w["key"], T("اعتماد خطة إدارة المشروع وخط الأساس", "Approve project management plan and baseline"), days["plan"] * 0.2,
             [(a4,)], criteria=T("خطة المشروع وخط الأساس معتمدان من الراعي", "Plan and baseline approved by the sponsor"), prio="high")

    n = len(delivs)
    span = days["exec"] / (1 + (n - 1) / 2)  # each package overlaps the previous one by half
    reviews, prev_first = [], None
    for i, d in enumerate(delivs, 1):
        dn = wp("exec", i, d, kind="deliverable", deliverable=d)
        pk = wp("exec", 1, T(f"حزمة عمل: {d}", f"Work package: {d}"), parent=dn, deliverable=d)
        deps = [(a5,)] + ([(prev_first, "SS", max(1, round(span / 2)))] if prev_first else [])
        p1 = act("exec", pk["key"], T(f"تجهيز مدخلات «{d}»", f"Prepare inputs for “{d}”"), span * 0.2, deps, deliverable=d,
                 criteria=T("المدخلات والموارد جاهزة", "Inputs and resources ready"))
        p2 = act("exec", pk["key"], T(f"إنتاج «{d}»", f"Produce “{d}”"), span * 0.6, deliverable=d,
                 criteria=T("المخرج مكتمل وفق المتطلبات", "Deliverable complete against requirements"), prio="high")
        s1 = act("exec", pk["key"], T(f"النسخة الأولى من «{d}»", f"First version of “{d}”"), span * 0.38, [(p1,)], parent=p2, deliverable=d)
        s2 = act("exec", pk["key"], T(f"استكمال «{d}» ومعالجة الملاحظات", f"Complete “{d}” and resolve comments"), span * 0.22, [(s1,)], parent=p2, deliverable=d)
        p3 = act("exec", pk["key"], T(f"المراجعة الداخلية لـ«{d}»", f"Internal review of “{d}”"), span * 0.2, [(s2,)], deliverable=d,
                 criteria=T("تقرير المراجعة بلا ملاحظات حرجة", "Review report with no critical findings"))
        reviews.append(p3)
        prev_first = p1
    w = wp("accept", 1, T("الاختبار وضبط الجودة", "Testing & quality control"))
    a6 = act("accept", w["key"], T("الاختبار المتكامل وفحص الجودة", "Integrated testing and quality check"), days["accept"] * 0.6,
             [(r,) for r in reviews], criteria=T("تقرير الاختبار معتمد", "Test report approved"), prio="high")
    w = wp("accept", 2, T("القبول", "Acceptance"))
    a7 = act("accept", w["key"], T("اختبار القبول والتوقيع على المخرجات", "User acceptance and deliverable sign-off"), days["accept"] * 0.4,
             [(a6,)], criteria=T("محاضر القبول موقعة", "Acceptance certificates signed"), prio="high")
    w = wp("close", 1, T("التسليم والإغلاق", "Handover & closure"))
    a8 = act("close", w["key"], T("التسليم ونقل المعرفة", "Handover and knowledge transfer"), days["close"] * 0.6, [(a7,)],
             criteria=T("محضر التسليم موقع", "Handover record signed"))
    act("close", w["key"], T("تقرير الإغلاق والدروس المستفادة", "Closure report and lessons learned"), days["close"] * 0.4, [(a8,)],
        criteria=T("تقرير الإغلاق معتمد", "Closure report approved"))

    summaries = {a["parent"] for a in acts if a["parent"]}
    leaf = [a for a in acts if a["key"] not in summaries]
    total = sum(a["duration_days"] for a in leaf) or 1
    budget = _val(draft, "budget") or 0
    for a in leaf:
        a["weight"] = round(a["duration_days"] / total * 100, 2)
        a["estimated_cost"] = round(budget * a["duration_days"] / total, 2)
    by_key = {a["key"]: a for a in acts}
    for a in acts:  # summaries carry the sum of their children
        if a["key"] in summaries:
            kids = [x for x in acts if x["parent"] == a["key"]]
            a["weight"] = round(sum(k["weight"] for k in kids), 2)
            a["estimated_cost"] = round(sum(k["estimated_cost"] for k in kids), 2)
    if not budget:
        assumed.append(T("لا توجد ميزانية في الميثاق؛ تُركت تكاليف الأنشطة صفراً.", "No budget in the charter; activity costs were left at zero."))
    wcode = {w["key"]: w["code"] for w in wbs}
    count: dict = {}
    for a in acts:
        base = wcode[a["wbs"]] if not a["parent"] else by_key[a["parent"]]["wbs_code"]
        count[base] = count.get(base, 0) + 1
        a["wbs_code"] = f"{base}.{count[base]}"
    return {"phases": phases, "wbs": wbs, "activities": acts, "assumptions": assumed}


def generate_schedule(draft: dict, calendar: scheduling.Calendar) -> dict:
    """Runs the deterministic engine on the draft activities. Output is tagged 'calculated'."""
    ar = draft.get("language") == "ar"
    acts = draft["activities"]
    start_txt = _val(draft, "start_date")
    start = date.fromisoformat(start_txt) if start_txt else calendar.next_working(date.today())
    items = [{"id": a["key"], "duration": a["duration_days"], "parent": a.get("parent")} for a in acts]
    links = [{"pred": d["pred"], "succ": a["key"], "type": d.get("type", "FS"), "lag": d.get("lag", 0)}
             for a in acts for d in a.get("deps", [])]
    res = scheduling.schedule_with_summaries(items, links, start, calendar)
    for a in acts:
        r = res["tasks"][a["key"]]
        a.update(planned_start=r["start"].isoformat(), planned_end=r["end"].isoformat(),
                 total_float=r["total_float"], is_critical=r["critical"], is_summary=r["summary"])
    phase_end = {}
    for a in acts:
        phase_end[a["phase"]] = max(phase_end.get(a["phase"], a["planned_end"]), a["planned_end"])
    names = {p["key"]: p["name"] for p in draft["phases"]}
    milestones = [dict(mm) for mm in draft.get("milestones", []) if mm.get("tag") == "extracted" or mm.get("tag") == "user"]
    have = {mm["name"] for mm in milestones}
    for k, _, _, _ in PHASES:
        if k in phase_end:
            n = f"اكتمال مرحلة {names[k]}" if ar else f"{names[k]} complete"
            if n not in have:
                milestones.append({"name": n, "target_date": phase_end[k], "tag": "ai", "source": None, "phase": k,
                                   "acceptance_criteria": "اعتماد بوابة المرحلة" if ar else "Stage gate approved"})
    end_txt = _val(draft, "end_date")
    warn = []
    if end_txt and res["finish"] and res["finish"] > date.fromisoformat(end_txt):
        over = (res["finish"] - date.fromisoformat(end_txt)).days
        warn.append((f"الجدول المحسوب ينتهي بعد تاريخ النهاية في الميثاق بـ {over} يوماً؛ قصّر المدد أو زد التداخل."
                     if ar else f"The calculated schedule ends {over} days after the charter end date; shorten durations or add overlap."))
    return {"activities": acts, "milestones": sorted(milestones, key=lambda x: x.get("target_date") or "9999"),
            "finish": res["finish"].isoformat() if res["finish"] else None, "duration_days": res["duration"],
            "critical_path": res["critical_path"], "warnings": warn, "start": start.isoformat()}


def generate_risks(draft: dict, thresholds: dict | None = None) -> list[dict]:
    ar = draft.get("language") == "ar"
    T = lambda a, e: a if ar else e
    owner = _val(draft, "manager", "")
    end = _val(draft, "end_date")
    deadline = (date.fromisoformat(_val(draft, "start_date")) + timedelta(days=30)).isoformat() if _val(draft, "start_date") else None
    out = []

    def add(level, title, cat, p, i, mit, cont, trig, tag="ai", source=None, desc="", acts=(), deliv=None, phase=None, est=False):
        a = risk_engine.assess(p, i, thresholds)
        rp, ri = max(1, p - 1), max(1, i - 1) if mit else i
        out.append({"code": f"R-{len(out) + 1:03d}", "scope_level": level, "title": title, "description": desc, "category": cat,
                    "probability": p, "impact": i, "score": a["score"], "level": a["level"], "owner_name": owner,
                    "mitigation": mit, "contingency": cont, "trigger": trig, "response_deadline": deadline,
                    "residual_probability": rp, "residual_impact": ri, "residual_score": rp * ri,
                    "related_activities": list(acts), "related_deliverable": deliv, "phase": phase,
                    "tag": tag, "source": source, "rating_estimated": est})

    for r in draft.get("risks_extracted", []):
        est = r.get("rating_missing", False)
        add("project", r["title"], T("مذكور في الميثاق", "Stated in charter"), r.get("probability") or 3, r.get("impact") or 3,
            r.get("mitigation", ""), "", "", tag="extracted", source=r.get("source"), est=est)
    for c in draft["lists"].get("constraints", [])[:4]:
        add("project", T(f"تعذر الالتزام بالقيد: {c['text']}", f"Constraint cannot be met: {c['text']}"), T("قيود", "Constraint"), 3, 4,
            T("راقب القيد في تقارير الحالة الدورية وحدد هامشاً احتياطياً.", "Track the constraint in status reports and set a buffer."),
            T("ارفع طلب تغيير للجنة التوجيهية.", "Raise a change request to the steering committee."),
            T("انحراف يتجاوز 10% عن القيد", "Deviation above 10% from the constraint"), source=c.get("source"))
    for a in draft["lists"].get("assumptions", [])[:4]:
        add("project", T(f"عدم تحقق الافتراض: {a['text']}", f"Assumption proves false: {a['text']}"), T("افتراضات", "Assumption"), 2, 4,
            T("تحقق من الافتراض خلال مرحلة التخطيط ووثق النتيجة.", "Validate the assumption during planning and record the result."),
            T("أعد تخطيط الأنشطة المتأثرة.", "Replan the affected activities."), T("دليل يخالف الافتراض", "Evidence contradicting the assumption"),
            source=a.get("source"))
    for d in draft["lists"].get("dependencies", [])[:3]:
        add("project", T(f"تأخر الاعتمادية الخارجية: {d['text']}", f"External dependency slips: {d['text']}"), T("اعتماديات", "Dependency"), 3, 3,
            T("اتفق على مواعيد ملزمة مع الجهة المعنية وتابعها أسبوعياً.", "Agree binding dates with the other party and track weekly."),
            T("فعّل مساراً بديلاً أو أعد ترتيب الأنشطة.", "Use an alternative path or resequence activities."),
            T("تأخر الجهة عن موعد متفق عليه", "The other party misses an agreed date"), source=d.get("source"))
    acts = draft.get("activities", [])
    crit = [a for a in acts if a.get("is_critical") and not a.get("is_summary")]
    plan_phase = next((p for p in draft.get("phases", []) if p["key"] == "plan"), None)
    if plan_phase:
        add("phase", T("تأخر اعتماد المتطلبات والتصميم يؤخر بدء التنفيذ", "Late approval of requirements and design delays execution"),
            T("جدول زمني", "Schedule"), 3, 4, T("حدد مهلة مراجعة مع مالك الأعمال وجلسات اعتماد مجدولة مسبقاً.", "Set review deadlines with the business owner and pre-book approval sessions."),
            T("ابدأ الأعمال غير المتأثرة بالتوازي.", "Start unaffected work in parallel."), T("تجاوز مهلة المراجعة بخمسة أيام عمل", "Review deadline missed by five working days"),
            phase="plan")
    for d in draft["lists"].get("deliverables", [])[:3]:
        add("deliverable", T(f"عدم قبول المخرج «{d['text']}» من أول مراجعة", f"Deliverable “{d['text']}” rejected at first review"),
            T("جودة", "Quality"), 3, 3, T("اتفق على معايير القبول كتابياً قبل الإنتاج وأجرِ مراجعة منتصف المدة.", "Agree acceptance criteria in writing before production and hold a mid-point review."),
            T("خصص وقتاً لدورة تصحيح واحدة.", "Reserve time for one correction cycle."), T("ملاحظات جوهرية في المراجعة الداخلية", "Major findings in internal review"),
            deliv=d["text"], acts=[a["key"] for a in acts if a.get("deliverable") == d["text"] and not a.get("is_summary")][:3])
    wps = [w for w in draft.get("wbs", []) if w["kind"] == "work_package" and w["phase"] == "exec"]
    if wps:
        add("work_package", T(f"نقص الموارد المتخصصة في «{wps[0]['name']}»", f"Shortage of specialist resources in “{wps[0]['name']}”"),
            T("موارد", "Resources"), 3, 3, T("احجز الموارد قبل بدء الحزمة وحدد بدلاء.", "Reserve resources before the package starts and name backups."),
            T("استعن بمورد خارجي مؤقت.", "Bring in a temporary external resource."), T("انخفاض التخصيص عن 80% من المخطط", "Allocation below 80% of plan"),
            acts=[a["key"] for a in acts if a["wbs"] == wps[0]["key"]][:3])
    for a in crit[:2]:
        add("activity", T(f"تأخر النشاط الحرج «{a['name']}»", f"Critical activity “{a['name']}” runs late"), T("جدول زمني", "Schedule"), 3, 4,
            T("تابع النشاط يومياً خلال تنفيذه ولا تسحب موارده.", "Track the activity daily while it runs and protect its resources."),
            T("قصّر الأنشطة اللاحقة أو نفّذها بالتوازي.", "Crash or fast-track the following activities."),
            T("إنجاز أقل من المخطط بـ 15% عند منتصف المدة", "Progress 15% under plan at mid-point"), acts=[a["key"]])
    if _val(draft, "budget"):
        add("project", T("تجاوز التكلفة الفعلية للميزانية المعتمدة", "Actual cost exceeds the approved budget"), T("مالية", "Financial"), 2, 4,
            T("راجع CPI شهرياً واضبط الالتزامات قبل التعاقد.", "Review CPI monthly and control commitments before contracting."),
            T("استخدم احتياطي الطوارئ أو قلّص النطاق باعتماد.", "Use contingency reserve or reduce scope with approval."), T("CPI أقل من 0.9", "CPI below 0.9"))
    return out


def _table(head: list[str], rows: list[list]) -> str:
    if not rows:
        return ""
    return "\n".join([" | ".join(head)] + [" | ".join("" if c is None else str(c) for c in r) for r in rows])


def generate_documents(draft: dict) -> list[dict]:
    """19 management-document drafts built from the reviewed draft. Sections with no data say so."""
    ar = draft.get("language") == "ar"
    T = lambda a, e: a if ar else e
    P = lambda f: (draft["profile"].get(f) or {}).get("raw") or (draft["profile"].get(f) or {}).get("value")
    none = T("لا توجد بيانات في الميثاق — يحتاج إلى استكمال.", "No data in the charter — to be completed.")
    name = P("name") or T("المشروع", "Project")
    lst = lambda f: draft["lists"].get(f, [])
    bullets = lambda items: "\n".join(f"- {i['text']}" for i in items) or none
    acts = [a for a in draft.get("activities", []) if not a.get("is_summary")]
    risks, ms = draft.get("risks", []), draft.get("milestones", [])
    stake = lst("stakeholders")
    head = lambda title: f"# {title}\n\n{T('المشروع', 'Project')}: {name}\n{T('الحالة', 'Status')}: {T('مسودة مولدة آلياً — تتطلب المراجعة والاعتماد', 'Auto-generated draft — requires review and approval')}\n"
    docs = []

    def doc(key, ar_t, en_t, body):
        docs.append({"key": key, "title": T(ar_t, en_t), "content": head(T(ar_t, en_t)) + "\n" + body.strip() + "\n", "tag": "ai", "approved": False})

    doc("charter", "ميثاق المشروع", "Project Charter", "\n\n".join([
        f"## {T('البيانات الأساسية', 'Key data')}\n" + _table([T('البند', 'Item'), T('القيمة', 'Value')], [
            [T("راعي المشروع", "Project sponsor"), P("sponsor") or none], [T("مدير المشروع", "Project manager"), P("manager") or none],
            [T("مالك الأعمال", "Business owner"), P("business_owner") or none], [T("الميزانية المعتمدة", "Approved budget"), P("budget") or none],
            [T("تاريخ البداية", "Start date"), P("start_date") or none], [T("تاريخ النهاية", "End date"), P("end_date") or none]]),
        f"## {T('مبررات المشروع', 'Business case')}\n{P('business_case') or none}",
        f"## {T('أهداف المشروع', 'Project objectives')}\n{bullets(lst('objectives'))}",
        f"## {T('نطاق المشروع', 'Project scope')}\n{P('scope') or none}",
        f"## {T('خارج النطاق', 'Out of scope')}\n{P('out_of_scope') or none}",
        f"## {T('المخرجات', 'Deliverables')}\n{bullets(lst('deliverables'))}"]))
    doc("pmp", "خطة إدارة المشروع", "Project Management Plan", "\n\n".join([
        f"## {T('منهجية التنفيذ', 'Delivery approach')}\n" + T("ينفذ المشروع على مراحل تنتهي كل منها ببوابة اعتماد:", "The project is delivered in phases, each ending in a stage gate:") + "\n" + "\n".join(f"- {p['name']}" for p in draft.get("phases", [])),
        f"## {T('خط الأساس الزمني', 'Schedule baseline')}\n" + T(f"عدد الأنشطة: {len(acts)}. الانتهاء المحسوب: {draft.get('schedule', {}).get('finish') or '—'}.", f"Activities: {len(acts)}. Calculated finish: {draft.get('schedule', {}).get('finish') or '—'}."),
        f"## {T('خط الأساس المالي', 'Cost baseline')}\n{T('الميزانية المعتمدة', 'Approved budget')}: {P('budget') or none}",
        f"## {T('الخطط الفرعية', 'Subsidiary plans')}\n" + T("خطط المخاطر والجودة والموارد والتواصل والتغيير والمتابعة مرفقة كوثائق مستقلة.", "Risk, quality, resource, communication, change and monitoring plans are separate documents.")]))
    doc("stakeholders", "سجل أصحاب المصلحة", "Stakeholder Register",
        _table([T("الاسم", "Name"), T("الدور", "Role"), T("التأثير", "Power"), T("الاهتمام", "Interest")],
               [[s.get("name") or s["text"], s.get("role", ""), T("يحدد", "TBD"), T("يحدد", "TBD")] for s in stake]) or none)
    parties = [s.get("name") or s["text"] for s in stake][:5] or [P("manager") or T("مدير المشروع", "Project manager")]
    doc("raci", "مصفوفة RACI", "RACI Matrix", _table([T("النشاط", "Activity")] + parties,
        [[a["name"]] + ["R" if j == 0 else ("A" if j == 1 else "I") for j in range(len(parties))] for a in acts[:25]]) or none)
    doc("communication", "خطة إدارة التواصل", "Communication Management Plan", _table(
        [T("الجمهور", "Audience"), T("المحتوى", "Content"), T("الدورية", "Frequency"), T("القناة", "Channel")],
        [[T("اللجنة التوجيهية", "Steering committee"), T("تقرير الحالة التنفيذي", "Executive status report"), T("شهري", "Monthly"), T("اجتماع", "Meeting")],
         [T("فريق المشروع", "Project team"), T("متابعة الأنشطة والمشكلات", "Activity and issue follow-up"), T("أسبوعي", "Weekly"), T("اجتماع", "Meeting")]] +
        [[s.get("name") or s["text"], T("مستجدات المشروع", "Project updates"), T("شهري", "Monthly"), T("بريد إلكتروني", "Email")] for s in stake[:6]]))
    doc("risk_plan", "خطة إدارة المخاطر", "Risk Management Plan", "\n\n".join([
        f"## {T('منهجية التقييم', 'Assessment method')}\n" + T("درجة الخطر = الاحتمالية × الأثر على مقياس من 1 إلى 5.", "Risk score = probability × impact on a 1–5 scale."),
        f"## {T('سجل المخاطر الأولي', 'Initial risk register')}\n" + (_table([T("الرمز", "ID"), T("الخطر", "Risk"), T("الاحتمالية", "P"), T("الأثر", "I"), T("الدرجة", "Score"), T("المعالجة", "Mitigation")],
            [[r["code"], r["title"], r["probability"], r["impact"], r["score"], r["mitigation"]] for r in risks]) or none)]))
    doc("quality", "خطة إدارة الجودة", "Quality Management Plan", "\n\n".join([
        f"## {T('معايير النجاح', 'Success criteria')}\n{bullets(lst('success_criteria'))}",
        f"## {T('معايير قبول المخرجات', 'Deliverable acceptance')}\n" + (_table([T("المخرج", "Deliverable"), T("معيار القبول", "Acceptance criterion")],
            [[d["text"], T("يحدد مع مالك الأعمال", "To be agreed with the business owner")] for d in lst("deliverables")]) or none)]))
    doc("resources", "خطة إدارة الموارد", "Resource Management Plan", _table([T("النشاط", "Activity"), T("المسؤول", "Responsible"), T("المدة (يوم عمل)", "Duration (working days)")],
        [[a["name"], a.get("responsible_name") or T("يحدد", "TBD"), a["duration_days"]] for a in acts[:30]]) or none)
    doc("procurement", "خطة إدارة المشتريات", "Procurement Management Plan",
        T("لم يحدد الميثاق بنود شراء. تُستكمل هذه الخطة عند الحاجة إلى تعاقدات.", "The charter names no procurement items. Complete this plan if contracts are needed."))
    doc("change", "خطة إدارة التغيير", "Change Management Plan",
        T("أي تغيير في النطاق أو الجدول أو التكلفة يقدم كطلب تغيير، يُحلل أثره، ثم يعتمده الراعي أو اللجنة التوجيهية قبل التنفيذ.",
          "Any change to scope, schedule or cost is raised as a change request, impact-assessed, then approved by the sponsor or steering committee before implementation."))
    doc("monitoring", "خطة المتابعة والتقييم", "Monitoring & Evaluation Plan",
        T("يُحدّث الإنجاز والتكاليف أسبوعياً. تُحسب مؤشرات القيمة المكتسبة (SPI و CPI) آلياً، وتراجع شهرياً مع الراعي.",
          "Progress and costs are updated weekly. Earned value indicators (SPI, CPI) are calculated automatically and reviewed monthly with the sponsor."))
    doc("kpis", "سجل مؤشرات الأداء", "KPI Register", _table([T("المؤشر", "KPI"), T("المستهدف", "Target")],
        [[k.get("name") or k["text"], k.get("target_raw", "")] for k in lst("kpis")]) or none)
    doc("deliverables", "سجل المخرجات", "Deliverables Register", _table([T("المخرج", "Deliverable"), T("الحالة", "Status")],
        [[d["text"], T("مخطط", "Planned")] for d in lst("deliverables")]) or none)
    doc("milestones", "سجل المعالم الرئيسية", "Milestone Register", _table([T("المعلم", "Milestone"), T("التاريخ المستهدف", "Target date"), T("المصدر", "Source")],
        [[x["name"], x.get("target_date") or T("غير محدد", "Not set"), T("الميثاق", "Charter") if x.get("tag") == "extracted" else T("مقترح", "Proposed")] for x in ms]) or none)
    doc("issues", "سجل المشكلات", "Issues Register", T("لا مشكلات مسجلة عند انطلاق المشروع.", "No issues recorded at project start."))
    doc("assumptions", "سجل الافتراضات", "Assumptions Log", bullets(lst("assumptions")))
    doc("constraints", "سجل القيود", "Constraints Register", bullets(lst("constraints")))
    doc("dependencies", "سجل الاعتماديات", "Dependency Register", bullets(lst("dependencies")))
    doc("lessons", "سجل الدروس المستفادة", "Lessons Learned Register", T("يُستكمل خلال التنفيذ وعند الإغلاق.", "Completed during delivery and at closure."))
    return docs
