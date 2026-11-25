"""Early-warning rules. Pure: takes a project snapshot, returns findings.
Each rule has a key so thresholds, severity, recipients and escalation are configurable."""
from __future__ import annotations

from datetime import date, timedelta

SEVERITIES = ["informational", "advisory", "warning", "critical"]

# key: (category, default severity, default threshold, name_ar, name_en)
RULES = {
    "activity_late": ("schedule", "warning", 0, "تأخر الأنشطة", "Late activities"),
    "critical_activity_late": ("schedule", "critical", 0, "تأخر نشاط على المسار الحرج", "Late critical-path activity"),
    "milestone_late": ("schedule", "critical", 0, "تأخر معلم رئيسي", "Late milestone"),
    "milestone_due": ("schedule", "advisory", 14, "معلم رئيسي قريب", "Milestone approaching"),
    "finish_slip": ("schedule", "warning", 5, "انحراف موعد الانتهاء عن خط الأساس", "Finish date slipping past baseline"),
    "progress_rate_low": ("schedule", "advisory", 10, "انخفاض معدل الإنجاز", "Progress behind plan"),
    "budget_overrun": ("financial", "critical", 100, "تجاوز الميزانية", "Budget overrun"),
    "spend_high": ("financial", "warning", 90, "ارتفاع المصروفات والالتزامات", "Spend and commitments near budget"),
    "eac_over_budget": ("financial", "warning", 5, "التكلفة المتوقعة تتجاوز الميزانية", "Forecast cost above budget"),
    "spi_low": ("performance", "warning", 0.9, "انخفاض مؤشر أداء الجدول SPI", "Low SPI"),
    "cpi_low": ("performance", "warning", 0.9, "انخفاض مؤشر أداء التكلفة CPI", "Low CPI"),
    "kpi_missed": ("performance", "advisory", 80, "مؤشر أداء دون المستهدف", "KPI below target"),
    "risk_critical": ("risk", "critical", 15, "خطر حرج مفتوح", "Open critical risk"),
    "risk_response_overdue": ("risk", "warning", 0, "خطة معالجة لم تنفذ في موعدها", "Risk response overdue"),
    "risk_deadline_near": ("risk", "advisory", 7, "اقتراب موعد الاستجابة للخطر", "Risk response deadline near"),
    "residual_high": ("risk", "warning", 10, "ارتفاع المخاطر المتبقية", "High residual risk"),
    "approval_stalled": ("governance", "warning", 5, "تعثر الاعتمادات", "Approval stalled"),
    "no_updates": ("governance", "advisory", 14, "غياب تحديثات المشروع", "No project updates"),
    "issue_open_long": ("governance", "warning", 14, "مشكلات لم تغلق", "Issues open too long"),
    "decision_pending": ("governance", "warning", 7, "تأخر اتخاذ القرار", "Decision overdue"),
    "resource_overallocated": ("governance", "warning", 100, "تحميل زائد على الموارد", "Resource over-allocated"),
}


def _f(key, entity_type, entity_id, ar, en, rec_ar, rec_en, bump=False):
    return {"rule_key": key, "entity_type": entity_type, "entity_id": entity_id,
            "title_ar": ar, "title_en": en, "recommendation_ar": rec_ar, "recommendation_en": rec_en,
            "bump": bump}


def evaluate(s: dict, thresholds: dict | None = None, today: date | None = None) -> list[dict]:
    """`s` is a snapshot: activities, milestones, risks, issues, approvals, decisions, kpis,
    evm, budget, actual, committed, baseline_finish, forecast_finish, last_update, status."""
    today = today or date.today()
    th = {k: v[2] for k, v in RULES.items()}
    th.update(thresholds or {})
    out = []
    if s.get("status") in ("completed", "cancelled"):
        return out
    paused = s.get("status") == "on_hold"  # a paused plan slipping is expected; keep risk, cost and governance rules

    for a in ([] if paused else s.get("activities", [])):
        end = a.get("planned_end")
        if end and end < today and (a.get("progress") or 0) < 100:
            days = (today - end).days
            if a.get("is_critical"):
                out.append(_f("critical_activity_late", "activity", a["id"],
                              f"النشاط الحرج «{a['name']}» متأخر {days} يوماً", f"Critical activity “{a['name']}” is {days} days late",
                              "أعد تخصيص الموارد لهذا النشاط أو قصّر الأنشطة اللاحقة على المسار الحرج، ثم أعد حساب الجدول.",
                              "Reassign resources to this activity or compress its successors on the critical path, then recalculate."))
            else:
                out.append(_f("activity_late", "activity", a["id"],
                              f"النشاط «{a['name']}» متأخر {days} يوماً", f"Activity “{a['name']}” is {days} days late",
                              f"الفائض الزمني المتاح {a.get('total_float') or 0} يوماً؛ حدّث نسبة الإنجاز أو أعد جدولة النشاط.",
                              f"Available float is {a.get('total_float') or 0} days; update progress or reschedule."))

    for m in ([] if paused else s.get("milestones", [])):
        td = m.get("target_date")
        if not td or m.get("status") == "achieved":
            continue
        if td < today:
            out.append(_f("milestone_late", "milestone", m["id"],
                          f"المعلم «{m['name']}» تجاوز موعده بـ {(today - td).days} يوماً", f"Milestone “{m['name']}” is {(today - td).days} days overdue",
                          "اعرض خطة تعافٍ على لجنة المشروع وحدد تاريخاً جديداً معتمداً.",
                          "Present a recovery plan to the project committee and agree a new approved date."))
        elif td <= today + timedelta(days=int(th["milestone_due"])):
            out.append(_f("milestone_due", "milestone", m["id"],
                          f"المعلم «{m['name']}» يستحق خلال {(td - today).days} يوماً", f"Milestone “{m['name']}” is due in {(td - today).days} days",
                          "تحقق من جاهزية المخرجات ومعيار الاعتماد.", "Check deliverable readiness and the acceptance criterion."))

    bf, ff = s.get("baseline_finish"), s.get("forecast_finish")
    if bf and ff and (ff - bf).days > th["finish_slip"] and not paused:
        out.append(_f("finish_slip", "project", s["id"],
                      f"موعد الانتهاء المتوقع يتأخر {(ff - bf).days} يوماً عن خط الأساس", f"Forecast finish is {(ff - bf).days} days past baseline",
                      "راجع المسار الحرج وقدّم طلب تغيير إذا تعذر الاستدراك.", "Review the critical path; raise a change request if recovery is not possible."))

    evm = s.get("evm") or {}
    gap = (evm.get("planned_pct") or 0) - (evm.get("earned_pct") or 0)
    if gap > th["progress_rate_low"] and not paused:
        out.append(_f("progress_rate_low", "project", s["id"],
                      f"الإنجاز الفعلي أقل من المخطط بـ {gap:.0f} نقطة مئوية", f"Actual progress is {gap:.0f} points behind plan",
                      "حدد الأنشطة المسببة للفجوة وضع لها خطة استدراك أسبوعية.", "Identify the activities causing the gap and set a weekly catch-up plan."))
    spi, cpi = evm.get("SPI"), evm.get("CPI")
    if spi is not None and spi < th["spi_low"] and not paused:
        out.append(_f("spi_low", "project", s["id"], f"SPI = {spi:.2f} (أقل من {th['spi_low']})", f"SPI = {spi:.2f} (below {th['spi_low']})",
                      "الجدول يتأخر: ركّز على أنشطة المسار الحرج.", "Schedule is slipping: focus on critical-path activities.", bump=spi < 0.8))
    if cpi is not None and cpi < th["cpi_low"]:
        out.append(_f("cpi_low", "project", s["id"], f"CPI = {cpi:.2f} (أقل من {th['cpi_low']})", f"CPI = {cpi:.2f} (below {th['cpi_low']})",
                      "التكلفة أعلى من القيمة المكتسبة: راجع بنود الصرف والعقود.", "Cost exceeds earned value: review spend lines and contracts.", bump=cpi < 0.8))

    budget, actual, committed = s.get("budget") or 0, s.get("actual") or 0, s.get("committed") or 0
    if budget > 0:
        if actual / budget * 100 > th["budget_overrun"]:
            out.append(_f("budget_overrun", "project", s["id"],
                          f"المصروفات الفعلية تجاوزت الميزانية المعتمدة بنسبة {actual / budget * 100 - 100:.0f}%", f"Actual spend exceeds approved budget by {actual / budget * 100 - 100:.0f}%",
                          "أوقف الالتزامات الجديدة واعرض طلب تمويل إضافي أو تقليص نطاق على الجهة المالية.",
                          "Freeze new commitments and take a funding or scope-reduction request to Finance."))
        elif (actual + committed) / budget * 100 > th["spend_high"]:
            out.append(_f("spend_high", "project", s["id"],
                          f"المصروفات والالتزامات بلغت {(actual + committed) / budget * 100:.0f}% من الميزانية", f"Spend plus commitments at {(actual + committed) / budget * 100:.0f}% of budget",
                          "راجع الالتزامات غير المصروفة وتوقعات نهاية المشروع.", "Review open commitments and the forecast at completion."))
        eac = evm.get("EAC")
        if eac and (eac - budget) / budget * 100 > th["eac_over_budget"] and actual <= budget:
            out.append(_f("eac_over_budget", "project", s["id"],
                          f"التكلفة المتوقعة عند الإنجاز تتجاوز الميزانية بـ {(eac - budget) / budget * 100:.0f}%", f"Estimate at completion is {(eac - budget) / budget * 100:.0f}% over budget",
                          "حدّث التوقعات المالية وحدد بنود الوفر الممكنة.", "Update the forecast and identify possible savings."))

    for k in s.get("kpis", []):
        t, a = k.get("target"), k.get("actual")
        if t and a is not None:
            pct = (a / t * 100) if k.get("direction") != "down" else (t / a * 100 if a else 100)
            if pct < th["kpi_missed"]:
                out.append(_f("kpi_missed", "kpi", k["id"], f"المؤشر «{k['name']}» عند {pct:.0f}% من المستهدف", f"KPI “{k['name']}” at {pct:.0f}% of target",
                              "حلّل سبب الفجوة مع مالك المؤشر.", "Analyse the gap with the KPI owner."))

    for r in s.get("risks", []):
        if r.get("status") in ("closed",):
            continue
        if (r.get("score") or 0) >= th["risk_critical"]:
            out.append(_f("risk_critical", "risk", r["id"], f"خطر حرج: {r['title']} (الدرجة {r['score']})", f"Critical risk: {r['title']} (score {r['score']})",
                          "صعّد إلى مدير المشروع ومدير مكتب إدارة المشاريع وتحقق من تنفيذ خطة المعالجة.",
                          "Escalate to the project manager and PMO director; verify the mitigation plan is being executed."))
        dl = r.get("response_deadline")
        if dl and r.get("status") == "open":
            if dl < today:
                out.append(_f("risk_response_overdue", "risk", r["id"], f"خطة معالجة الخطر «{r['title']}» متأخرة {(today - dl).days} يوماً", f"Response to risk “{r['title']}” is {(today - dl).days} days overdue",
                              "نفّذ خطة المعالجة أو حدّث موعدها مع مالك الخطر.", "Execute the response or agree a new date with the risk owner."))
            elif dl <= today + timedelta(days=int(th["risk_deadline_near"])):
                out.append(_f("risk_deadline_near", "risk", r["id"], f"موعد الاستجابة للخطر «{r['title']}» خلال {(dl - today).days} يوماً", f"Response to risk “{r['title']}” due in {(dl - today).days} days",
                              "تابع مع مالك الإجراء.", "Follow up with the action owner."))
        if (r.get("residual_score") or 0) >= th["residual_high"]:
            out.append(_f("residual_high", "risk", r["id"], f"المخاطر المتبقية مرتفعة في «{r['title']}» ({r['residual_score']})", f"High residual risk in “{r['title']}” ({r['residual_score']})",
                          "خطة المعالجة الحالية لا تكفي؛ أضف إجراءات أو خطة طوارئ.", "Current mitigation is not enough; add actions or a contingency plan."))

    for a in s.get("approvals", []):
        if a.get("status") == "pending" and a.get("requested_at"):
            days = (today - a["requested_at"]).days
            if days > th["approval_stalled"]:
                out.append(_f("approval_stalled", "approval", a["id"], f"اعتماد «{a['title']}» معلق منذ {days} يوماً", f"Approval “{a['title']}” pending for {days} days",
                              "ذكّر صاحب الصلاحية أو فوّض الاعتماد.", "Remind the approver or delegate the approval."))
    lu = s.get("last_update")
    if lu and (today - lu).days > th["no_updates"] and s.get("status") == "active":
        out.append(_f("no_updates", "project", s["id"], f"لا تحديثات على المشروع منذ {(today - lu).days} يوماً", f"No project updates for {(today - lu).days} days",
                      "اطلب من مدير المشروع تحديث الإنجاز والتكاليف.", "Ask the project manager to update progress and costs."))
    for i in s.get("issues", []):
        if i.get("status") != "closed" and i.get("raised_at") and (today - i["raised_at"]).days > th["issue_open_long"]:
            out.append(_f("issue_open_long", "issue", i["id"], f"المشكلة «{i['title']}» مفتوحة منذ {(today - i['raised_at']).days} يوماً", f"Issue “{i['title']}” open for {(today - i['raised_at']).days} days",
                          "حدد مالكاً وتاريخ إغلاق، أو صعّدها.", "Assign an owner and closing date, or escalate."))
    for d in s.get("decisions", []):
        if d.get("status") == "pending" and d.get("due_date") and (today - d["due_date"]).days > th["decision_pending"]:
            out.append(_f("decision_pending", "decision", d["id"], f"القرار «{d['title']}» متأخر {(today - d['due_date']).days} يوماً", f"Decision “{d['title']}” is {(today - d['due_date']).days} days overdue",
                          "ارفع القرار إلى اللجنة التوجيهية في أقرب اجتماع.", "Take the decision to the next steering committee."))
    for r in s.get("overallocated", []):
        out.append(_f("resource_overallocated", "resource", r["id"], f"المورد «{r['name']}» محمّل بنسبة {r['load']:.0f}%", f"Resource “{r['name']}” loaded at {r['load']:.0f}%",
                      "أعد توزيع المهام أو أضف مورداً.", "Rebalance assignments or add a resource."))
    return out
