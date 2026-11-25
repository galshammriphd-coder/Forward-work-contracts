import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ChevronLeft, DoorOpen, Pencil, Play, Trash2, UserPlus, X } from "lucide-react";
import { api, useApp, useLoad } from "../lib/core";
import { Async, Confirm, FormModal, Progress, Register, Src, Status, Tabs } from "../lib/ui";
import { AlertList } from "./Dashboard";
import { Gauge, RiskMatrix, VBars } from "../lib/charts";
import Schedule, { Planning } from "./Schedule";
import Risks from "./Risks";
import Finance from "./Finance";
import { Resources, Stakeholders } from "./People";
import { Chat, Documents } from "./Knowledge";
import { projectFields, STAGE, useLists } from "./Portfolio";
import { ReportBuilder } from "./Reports";

export function BenefitsRegister({ pid, onChanged }: { pid?: number; onChanged?: () => void }) {
  const { T, N, num } = useApp();
  const lists = useLists();
  const projects = useLoad<any[]>(pid ? null : "/projects");
  return <Register resource="benefits" projectId={pid} perm="benefit.write" noun={["منفعة", "Benefit"]} title={T("المنافع وتحقيق القيمة", "Benefits and value realisation")} onChanged={onChanged}
    sub={T("التحقق يُحسب من القياس الفعلي فقط: من خط الأساس نحو المستهدف. اكتمال المشروع لا يُحتسب منفعة.", "Realisation is computed from actual measurements only, from baseline toward target. A finished project does not count as a benefit.")}
    cols={[...(pid ? [] : [{ key: "project_id", label: ["المشروع", "Project"] as [string, string], render: (r: any) => <Link to={`/projects/${r.project_id}/value`}>{N((projects.data || []).find(p => p.id === r.project_id))}</Link> }]),
      { key: "name", label: ["المنفعة", "Benefit"] }, { key: "metric", label: ["مؤشر القياس", "Measure"] }, { key: "owner_name", label: ["المالك", "Owner"] }, { key: "baseline", label: ["خط الأساس", "Baseline"], type: "num" }, { key: "target", label: ["المستهدف", "Target"], type: "num" },
      { key: "actual", label: ["المتحقق", "Actual"], render: r => r.actual == null ? <span className="tag warning">{T("لم يُقَس", "Not measured")}</span> : <span className="num">{num(r.actual, 1)} {r.unit}</span> },
      { key: "realization", label: ["التحقق", "Realised"], render: r => r.realization == null ? "—" : <Progress v={Math.min(100, r.realization)} /> }, { key: "gap", label: ["الفجوة", "Gap"], type: "num" },
      { key: "target_date", label: ["موعد التحقق", "Target date"], type: "date" }, { key: "status", label: ["الحالة", "Status"], type: "status" }]}
    fields={[...(pid ? [] : [{ key: "project_id", label: ["المشروع", "Project"] as [string, string], type: "select" as const, required: true, options: () => (projects.data || []).map(p => [p.id, N(p)]) as [any, string][] }]),
      { key: "name", label: ["المنفعة المتوقعة", "Expected benefit"], required: true, wide: true }, { key: "objective_id", label: ["الهدف الاستراتيجي", "Strategic objective"], type: "select", options: lists.objectives.map(o => [o.id, N(o)]) },
      { key: "owner_name", label: ["مالك المنفعة", "Benefit owner"] }, { key: "metric", label: ["مؤشر القياس", "Measure"] }, { key: "unit", label: ["الوحدة", "Unit"] },
      { key: "baseline", label: ["خط الأساس", "Baseline"], type: "number" }, { key: "target", label: ["المستهدف", "Target"], type: "number" }, { key: "actual", label: ["القياس الفعلي", "Actual measurement"], type: "number", hint: ["اتركه فارغاً حتى يُقاس فعلياً", "Leave empty until actually measured"] },
      { key: "measured_at", label: ["تاريخ القياس", "Measured on"], type: "date" }, { key: "target_date", label: ["موعد التحقق", "Target date"], type: "date" },
      { key: "monetary_value", label: ["القيمة المالية المتحققة", "Realised financial value"], type: "number", hint: ["تُستخدم لحساب العائد على الاستثمار عند توفرها", "Used for ROI when available"] },
      { key: "status", label: ["الحالة", "Status"], type: "select", def: "planned", required: true, options: [["planned", T("مخطط", "Planned")], ["tracking", T("قيد القياس", "Tracking")], ["realized", T("تحققت", "Realised")], ["at_risk", T("مهددة", "At risk")]] }]} />;
}

export function LessonsRegister({ pid }: { pid?: number }) {
  const { T, N } = useApp();
  const projects = useLoad<any[]>(pid ? null : "/projects");
  const cats = ["موردون", "نطاق", "تغيير", "جدول زمني", "مالية", "جودة", "موارد", "حوكمة", "تقني"];
  return <Register resource="lessons" projectId={pid} perm="benefit.write" noun={["درساً", "Lesson"]} title={T("الدروس المستفادة", "Lessons learned")}
    cols={[...(pid ? [] : [{ key: "project_id", label: ["المشروع", "Project"] as [string, string], render: (r: any) => N((projects.data || []).find(p => p.id === r.project_id)) || "—" }]),
      { key: "kind", label: ["النوع", "Kind"], render: r => <span className={`tag ${r.kind === "success" ? "good" : "warning"}`}>{r.kind === "success" ? T("نجاح يُكرَّر", "Worked — repeat") : T("يحتاج تحسيناً", "To improve")}</span> },
      { key: "category", label: ["الفئة", "Category"] }, { key: "title", label: ["الدرس", "Lesson"] }, { key: "recommendation", label: ["التوصية", "Recommendation"] }]}
    fields={[...(pid ? [] : [{ key: "project_id", label: ["المشروع", "Project"] as [string, string], type: "select" as const, options: () => (projects.data || []).map(p => [p.id, N(p)]) as [any, string][] }]),
      { key: "title", label: ["الدرس", "Lesson"], required: true, wide: true }, { key: "kind", label: ["النوع", "Kind"], type: "select", def: "improve", required: true, options: [["success", T("نجاح يُكرَّر", "Worked — repeat")], ["improve", T("يحتاج تحسيناً", "To improve")]] },
      { key: "category", label: ["الفئة", "Category"], type: "select", options: cats.map(c => [c, c]) }, { key: "description", label: ["ما الذي حدث؟", "What happened?"], type: "textarea" }, { key: "recommendation", label: ["التوصية للمشاريع القادمة", "Recommendation for future projects"], type: "textarea" }]} />;
}

function Overview({ p, reload }: { p: any; reload: () => void }) {
  const { T, N, num, money, pct, date, can, meta, fail, toast } = useApp();
  const m = p.metrics, e = m.evm;
  const [member, setMember] = useState("");
  const write = can("project.write");
  const gate = (ph: any) => api.post(`/phases/${ph.id}/gate`).then(() => { toast(T("أُرسل طلب اعتماد البوابة", "Gate approval requested")); reload(); }).catch(fail);
  const hm = useLoad<any>(`/risks/heatmap?project_id=${p.id}`);
  const fin = useLoad<any>(can("finance.read") ? `/projects/${p.id}/finance` : null);
  const nav = useNavigate();
  const t0 = p.start_date ? +new Date(p.start_date) : 0, t1 = m.forecast_finish ? Math.max(+new Date(m.forecast_finish), +new Date(p.end_date || m.forecast_finish)) : 0;
  const pos = (d: string) => (t1 > t0 ? Math.max(0, Math.min(100, ((+new Date(d) - t0) / (t1 - t0)) * 100)) : 0);
  const info: [string, any][] = [[T("الراعي", "Sponsor"), p.sponsor], [T("مدير المشروع", "Project manager"), N(p, "manager_name")], [T("مالك الأعمال", "Business owner"), p.business_owner], [T("البداية", "Start"), date(p.start_date)], [T("النهاية", "End"), date(p.end_date)],
    [T("الانتهاء المتوقع", "Forecast finish"), date(m.forecast_finish)], [T("الأولوية", "Priority"), <Status v={p.priority} />], [T("طريقة الإنشاء", "Created"), p.created_from === "charter" ? T("من ميثاق بالمعالج الذكي", "From a charter, by the wizard") : T("يدوياً", "Manually")]];
  return <div className="grid split" style={{ alignItems: "start" }}>
    <div className="stack">
      {p.needs_intervention && <div className="note critical"><div><b>{T("يتطلب تدخلاً تنفيذياً", "Needs executive intervention")}</b><div>{p.intervention_reason}</div></div></div>}
      <div className="grid g4w">
        <section className="panel"><header><h2>{T("الإنجاز", "Progress")}</h2></header><div className="body"><Gauge value={m.progress} marker={m.planned_progress} color="var(--c-actual)" sub={T(`الخط = المخطط ${pct(m.planned_progress, 1)}`, `Line = planned ${pct(m.planned_progress, 1)}`)} /></div></section>
        <section className="panel"><header><h2>{T("الميزانية المصروفة", "Used budget")}</h2></header><div className="body"><Gauge value={m.actual} max={m.budget || 1} ends color={m.over_budget ? "var(--s-critical)" : "var(--c-lime)"} fmt={v => money(v).replace(/ [^ ]+$/, "")} marker={Math.min(m.budget, m.actual + m.committed)} sub={T(`من ${money(m.budget)}؛ الخط = مع الالتزامات`, `Of ${money(m.budget)}; line = with commitments`)} /></div></section>
        <section className="panel"><header><h2>{T("أداء الجدول SPI", "Schedule performance (SPI)")}</h2></header><div className="body"><Gauge value={e.SPI} max={1.5} fmt={v => num(v, 2)} marker={1} color={e.SPI != null && e.SPI < 0.9 ? "var(--s-critical)" : "var(--c1)"} sub={T("الخط = 1.00 (وفق الخطة)", "Line = 1.00 (on plan)")} /></div></section>
        <section className="panel"><header><h2>{T("أداء التكلفة CPI", "Cost performance (CPI)")}</h2></header><div className="body"><Gauge value={e.CPI} max={1.5} fmt={v => num(v, 2)} marker={1} color={e.CPI != null && e.CPI < 0.9 ? "var(--s-critical)" : "var(--c-violet)"} sub={T("الخط = 1.00 (وفق الميزانية)", "Line = 1.00 (on budget)")} /></div></section>
      </div>
      <div className="grid gates">
        <section className="panel"><header><h2>{T("الخط الزمني للمراحل", "Gates timeline")}</h2></header><div className="body">
          {p.phases.length === 0 || !t0 ? <p className="muted">{T("لا مراحل بعد.", "No phases yet.")}</p> : <div className="timeline" dir="ltr">
            <div className="tl-ends"><span>{date(p.start_date)}</span><span>{date(m.forecast_finish)}</span></div>
            <div className="tl-bar">{p.phases.map((ph: any) => ph.start_date && <i key={ph.id} className={`tl-${ph.status}`} title={ph.name} style={{ left: `${pos(ph.start_date)}%`, width: `${Math.max(1.5, pos(ph.end_date) - pos(ph.start_date))}%` }} />)}
              <em style={{ left: `${pos(m.data_date)}%` }}><span>{T("اليوم", "Today")}</span></em></div>
            <div className="tl-names">{p.phases.map((ph: any) => ph.start_date && <span key={ph.id} style={{ left: `${pos(ph.start_date)}%`, width: `${Math.max(1.5, pos(ph.end_date) - pos(ph.start_date))}%` }} dir="auto">{ph.name}</span>)}</div></div>}</div></section>
        <section className="panel"><header><h2>{T("بوابات الاعتماد", "Gates")}</h2></header>
          {p.phases.length === 0 ? <div className="empty">{T("لا مراحل. أنشئها من التخطيط أو بالمعالج.", "No phases. Create them under Planning or with the wizard.")}</div> :
            <div className="tbl-wrap"><table className="tbl cells"><thead><tr><th>{T("المرحلة", "Phase")}</th><th>{T("الحالة", "Status")}</th><th>{T("البوابة", "Gate")}</th><th>{T("النهاية", "End")}</th></tr></thead>
              <tbody>{p.phases.map((ph: any) => <tr key={ph.id}><td>{ph.name}</td><td><Status v={ph.status} /></td>
                <td>{write && ph.gate_status === "pending" && ph.status === "completed" ? <button className="btn sm" onClick={() => gate(ph)}><DoorOpen />{T("اطلب الاعتماد", "Request approval")}</button> : <Status v={ph.gate_status} />}</td><td>{date(ph.end_date)}</td></tr>)}</tbody></table></div>}</section>
      </div>
      <div className="grid g2">
        <section className="panel"><header><h2>{T("مخاطر المشروع", "Project risks")}</h2><button className="btn sm" onClick={() => nav(`/projects/${p.id}/risks`)}>{T("افتح السجل", "Open register")}</button></header><div className="body"><Async q={hm}>{d => <RiskMatrix grid={d.grid} onPick={() => nav(`/projects/${p.id}/risks`)} />}</Async></div></section>
        {fin.data ? <section className="panel"><header><h2>{T("التكلفة المخططة مقابل الفعلية حسب المرحلة", "Budgeted against actual cost by phase")}</h2></header><div className="body">
          <VBars names={[T("المخطط", "Budget"), T("الفعلي", "Actual")]} fmt={v => money(v).replace(/ [^ ]+$/, "")} rows={fin.data.by_phase.map((x: any) => ({ label: x.phase, a: x.planned, b: x.actual }))} /></div></section> : null}
      </div>
      <div className="kpis">
        <div className="kpi" style={{ cursor: "default" }}><span>{T("أنشطة متأخرة", "Late activities")}</span><b className={m.late_activities ? "warning" : ""}>{num(m.late_activities)}</b><small>{num(m.critical_late)} {T("على المسار الحرج", "on the critical path")}</small></div>
        <div className="kpi" style={{ cursor: "default" }}><span>{T("مخاطر مفتوحة", "Open risks")}</span><b className={m.risk_counts.critical ? "critical" : ""}>{num(m.open_risks)}</b><small>{num(m.risk_counts.critical)} {T("حرجة", "critical")}</small></div>
        <div className="kpi" style={{ cursor: "default" }}><span>{T("انحراف الانتهاء", "Finish variance")}</span><b className={m.schedule_variance_days > 0 ? "critical" : ""}>{num(m.schedule_variance_days)} {T("يوم", "days")}</b><small>{T("مقابل خط الأساس", "Against baseline")}</small></div>
        <div className="kpi" style={{ cursor: "default" }}><span>{T("الوثائق", "Documents")}</span><b>{num(p.counts.documents)}</b><small>{num(p.counts.activities)} {T("نشاطاً", "activities")}</small></div>
      </div>
      <section className="panel"><header><h2>{T("معلومات المشروع", "Project information")}</h2></header><div className="body stack">
        <p dir="auto">{p.description || <span className="muted">{T("لا وصف.", "No description.")}</span>}</p>
        <div className="grid g4 small">{info.map(([l, v]) => <div key={l}><div className="muted">{l}</div><div className="strong">{v || "—"}</div></div>)}</div>
        {[["النطاق", "Scope", p.scope], ["خارج النطاق", "Out of scope", p.out_of_scope], ["مبررات المشروع", "Business case", p.business_case], ["معايير النجاح", "Success criteria", p.success_criteria], ["الافتراضات", "Assumptions", p.assumptions], ["القيود", "Constraints", p.constraints], ["الاعتماديات", "Dependencies", p.dependencies_text]]
          .filter(x => x[2]).map(([a, en, v]) => <div key={en}><h4>{T(a, en)}</h4><p style={{ whiteSpace: "pre-wrap" }} dir="auto">{v}</p></div>)}</div></section>
    </div>
    <div className="stack">
      <section className="panel"><header><div><h2>{T("تنبيهات المشروع", "Project alerts")}</h2><p>{num(p.alerts.length)} {T("مفتوحة", "open")}</p></div></header>
        <div style={{ maxHeight: 420, overflowY: "auto" }}><AlertList alerts={[...p.alerts].sort((a: any, b: any) => meta?.severities.indexOf(b.severity) - meta?.severities.indexOf(a.severity))} onChange={reload} showProject={false} /></div></section>
      <section className="panel"><header><h2>{T("فريق المشروع والصلاحيات", "Project team and access")}</h2></header><div className="body stack tight">
        {p.members.map((mm: any) => <div key={mm.id} className="row small"><span className="grow">{N(mm)} <span className="muted">— {N((meta?.roles || []).find((r: any) => r.key === mm.role_key))}</span></span>
          {write && <button className="btn ghost sm icon" aria-label={T("أزل من الفريق", "Remove from team")} onClick={() => api.del(`/projects/${p.id}/members/${mm.id}`).then(reload).catch(fail)}><X /></button>}</div>)}
        {write && <div className="row"><select className="input grow" style={{ width: "auto" }} value={member} onChange={ev => setMember(ev.target.value)} aria-label={T("مستخدم", "User")}><option value="">{T("أضف عضواً…", "Add a member…")}</option>
          {(meta?.users || []).filter((u: any) => !p.members.some((x: any) => x.user_id === u.id)).map((u: any) => <option key={u.id} value={u.id}>{N(u)}</option>)}</select>
          <button className="btn icon" disabled={!member} aria-label={T("أضف", "Add")} onClick={() => api.post(`/projects/${p.id}/members`, { user_id: +member }).then(() => { setMember(""); reload(); }).catch(fail)}><UserPlus /></button></div>}
        <p className="small muted">{T("الأعضاء يرون هذا المشروع ووثائقه وفق أدوارهم. من ليس عضواً ولا يملك صلاحية عامة لا يراه.", "Members see this project and its documents according to their roles. Anyone who is not a member and has no platform-wide access cannot see it.")}</p></div></section>
    </div></div>;
}

function Charter({ p }: { p: any }) {
  const { T } = useApp();
  const L: Record<string, [string, string]> = { name: ["اسم المشروع", "Project name"], code: ["الرمز", "Code"], description: ["الوصف", "Description"], sponsor: ["راعي المشروع", "Sponsor"], manager: ["مدير المشروع", "Project manager"], business_owner: ["مالك الأعمال", "Business owner"],
    department: ["الإدارة", "Department"], priority: ["الأولوية", "Priority"], strategic_objective: ["الهدف الاستراتيجي", "Strategic objective"], business_case: ["المبررات", "Business case"], scope: ["النطاق", "Scope"], out_of_scope: ["خارج النطاق", "Out of scope"],
    budget: ["الميزانية", "Budget"], start_date: ["تاريخ البداية", "Start date"], end_date: ["تاريخ النهاية", "End date"], duration: ["المدة (شهر)", "Duration (months)"] };
  if (!p.charter) return <section className="panel"><div className="empty">{T("أُنشئ هذا المشروع يدوياً، فلا ميثاق محللاً له. ارفع الميثاق في تبويب الوثائق ليصبح متاحاً للمحادثة.", "This project was created manually, so it has no analysed charter. Upload the charter under Documents to make it available to the chat.")}</div></section>;
  return <section className="panel"><header><div><h2>{T("ميثاق المشروع المعتمد", "Approved project charter")}</h2><p>{T("كل قيمة مع مصدرها في الوثيقة الأصلية.", "Every value with its source in the original document.")}</p></div><Status v={p.charter.status} /></header>
    <div className="tbl-wrap"><table className="tbl"><thead><tr><th>{T("البند", "Item")}</th><th>{T("القيمة", "Value")}</th><th>{T("التصنيف", "Tag")}</th><th>{T("المصدر", "Source")}</th></tr></thead>
      <tbody>{Object.entries(p.charter.content || {}).map(([k, f]: any) => <tr key={k}><td>{T(...(L[k] || [k, k]))}</td><td dir="auto" style={{ maxWidth: 460 }}>{String(f.raw ?? f.value)}</td><td><Src v={f.tag} /></td>
        <td className="small muted">{f.source ? <>{T("الصفحة", "Page")} <bdi>{f.source.page}</bdi>{f.source.section && ` · ${f.source.section}`}</> : "—"}</td></tr>)}</tbody></table></div></section>;
}

function Governance({ p, reload }: { p: any; reload: () => void }) {
  const { T, date, can, fail, toast } = useApp();
  const defs = useLoad<any[]>("/r/workflow_definitions");
  const [wf, setWf] = useState("");
  const pid = p.id;
  return <div className="stack">
    <section className="panel"><header><div><h2>{T("الاعتمادات", "Approvals")}</h2></div>
      {can("project.write") && <div className="row"><select className="input" style={{ width: 220 }} value={wf} onChange={e => setWf(e.target.value)} aria-label={T("مسار الاعتماد", "Workflow")}><option value="">{T("اختر مسار اعتماد…", "Choose a workflow…")}</option>{(defs.data || []).filter(d => d.is_active).map(d => <option key={d.key} value={d.key}>{T(d.name_ar, d.name_en)}</option>)}</select>
        <button className="btn sm" disabled={!wf} onClick={() => api.post(`/projects/${pid}/workflows`, { key: wf }).then(() => { toast(T("بدأ مسار الاعتماد", "Workflow started")); reload(); }).catch(fail)}><Play className="flip" />{T("ابدأ المسار", "Start workflow")}</button></div>}</header>
      {p.approvals.length === 0 ? <div className="empty">{T("لا اعتمادات لهذا المشروع.", "No approvals for this project.")}</div> : <div className="tbl-wrap"><table className="tbl"><thead><tr><th>{T("الاعتماد", "Approval")}</th><th>{T("صاحب الصلاحية", "Approver role")}</th><th>{T("طُلب في", "Requested")}</th><th>{T("الاستحقاق", "Due")}</th><th>{T("الحالة", "Status")}</th><th>{T("ملاحظة", "Note")}</th></tr></thead>
        <tbody>{p.approvals.map((a: any) => <tr key={a.id}><td>{a.title}</td><td>{a.approver_role}</td><td>{date(a.requested_at)}</td><td>{date(a.due_date)}</td><td><Status v={a.status} /></td><td>{a.note || "—"}</td></tr>)}</tbody></table></div>}
      <div className="body small muted">{T("القرار يُتخذ من صفحة الحوكمة لدى صاحب الصلاحية.", "The decision is taken on the Governance page by the approver.")} <Link to="/governance">{T("افتح الحوكمة", "Open Governance")}</Link></div></section>
    <Register resource="issues" projectId={pid} perm="project.write" noun={["مشكلة", "Issue"]} title={T("سجل المشكلات", "Issues register")} onChanged={reload}
      cols={[{ key: "title", label: ["المشكلة", "Issue"] }, { key: "severity", label: ["الأهمية", "Severity"], type: "status" }, { key: "owner_name", label: ["المالك", "Owner"] }, { key: "raised_at", label: ["رُفعت في", "Raised"], type: "date" }, { key: "due_date", label: ["موعد الإغلاق", "Due"], type: "date" }, { key: "status", label: ["الحالة", "Status"], type: "status" }]}
      fields={[{ key: "title", label: ["المشكلة", "Issue"], required: true, wide: true }, { key: "severity", label: ["الأهمية", "Severity"], type: "select", def: "medium", required: true, options: [["low", T("منخفضة", "Low")], ["medium", T("متوسطة", "Medium")], ["high", T("عالية", "High")], ["critical", T("حرجة", "Critical")]] },
        { key: "status", label: ["الحالة", "Status"], type: "select", def: "open", required: true, options: [["open", T("مفتوحة", "Open")], ["in_progress", T("قيد المعالجة", "In progress")], ["closed", T("مغلقة", "Closed")]] },
        { key: "owner_name", label: ["المالك", "Owner"] }, { key: "due_date", label: ["موعد الإغلاق", "Due date"], type: "date" }, { key: "description", label: ["الوصف", "Description"], type: "textarea" }]} />
    <Register resource="change_requests" projectId={pid} perm="project.write" noun={["طلب تغيير", "Change request"]} title={T("سجل التغييرات", "Change log")}
      cols={[{ key: "title", label: ["التغيير", "Change"] }, { key: "change_type", label: ["النوع", "Type"] }, { key: "impact_cost", label: ["أثر التكلفة", "Cost impact"], type: "money" }, { key: "impact_schedule_days", label: ["أثر الجدول (يوم)", "Schedule impact (days)"], type: "num" }, { key: "requested_by", label: ["مقدم الطلب", "Requested by"] }, { key: "requested_at", label: ["التاريخ", "Date"], type: "date" }, { key: "status", label: ["الحالة", "Status"], type: "status" }]}
      fields={[{ key: "title", label: ["التغيير المطلوب", "Requested change"], required: true, wide: true }, { key: "change_type", label: ["النوع", "Type"], type: "select", def: "scope", options: [["scope", T("نطاق", "Scope")], ["schedule", T("جدول", "Schedule")], ["cost", T("تكلفة", "Cost")], ["quality", T("جودة", "Quality")]] },
        { key: "status", label: ["الحالة", "Status"], type: "select", def: "submitted", required: true, options: [["submitted", T("مقدّم", "Submitted")], ["approved", T("معتمد", "Approved")], ["rejected", T("مرفوض", "Rejected")], ["implemented", T("منفّذ", "Implemented")]] },
        { key: "impact_cost", label: ["أثر التكلفة", "Cost impact"], type: "number" }, { key: "impact_schedule_days", label: ["أثر الجدول (يوم عمل)", "Schedule impact (working days)"], type: "number" }, { key: "requested_by", label: ["مقدم الطلب", "Requested by"] }, { key: "description", label: ["الوصف والمبرر", "Description and rationale"], type: "textarea" }]} />
    <Register resource="decisions" projectId={pid} perm="project.write" noun={["قراراً", "Decision"]} title={T("سجل القرارات", "Decision log")} onChanged={reload}
      cols={[{ key: "title", label: ["القرار", "Decision"] }, { key: "decided_by", label: ["الجهة", "Body"] }, { key: "meeting", label: ["الاجتماع", "Meeting"] }, { key: "due_date", label: ["مطلوب قبل", "Needed by"], type: "date" }, { key: "decided_at", label: ["صدر في", "Decided on"], type: "date" }, { key: "status", label: ["الحالة", "Status"], type: "status" }]}
      fields={[{ key: "title", label: ["القرار", "Decision"], required: true, wide: true }, { key: "decided_by", label: ["الجهة صاحبة القرار", "Deciding body"] }, { key: "meeting", label: ["الاجتماع", "Meeting"] },
        { key: "status", label: ["الحالة", "Status"], type: "select", def: "pending", required: true, options: [["pending", T("معلق", "Pending")], ["decided", T("صدر", "Decided")], ["implemented", T("منفّذ", "Implemented")]] },
        { key: "due_date", label: ["مطلوب قبل", "Needed by"], type: "date" }, { key: "decided_at", label: ["صدر في", "Decided on"], type: "date" }, { key: "description", label: ["التفاصيل", "Details"], type: "textarea" }]} />
  </div>;
}

export default function ProjectCenter() {
  const { id, tab = "overview" } = useParams();
  const pid = +id!;
  const { T, N, can, meta, date, user } = useApp();
  const nav = useNavigate();
  const q = useLoad<any>(`/projects/${pid}`, [tab === "overview" || tab === "governance" ? tab : ""]);
  const lists = useLists();
  const [edit, setEdit] = useState(false);
  const [del, setDel] = useState(false);
  const tabs: [string, string][] = [["overview", T("نظرة عامة", "Overview")], ["charter", T("الميثاق", "Charter")], ["planning", T("التخطيط و WBS", "Planning & WBS")], ["gantt", T("الجدول الزمني", "Schedule")], ["risks", T("المخاطر", "Risks")],
    ...(can("finance.read") ? [["finance", T("المالية", "Finance")] as [string, string]] : []), ["resources", T("الموارد", "Resources")], ["stakeholders", T("أصحاب المصلحة و RACI", "Stakeholders & RACI")],
    ...(can("docs.read") ? [["documents", T("الوثائق", "Documents")] as [string, string]] : []), ...(can("chat.use") ? [["chat", T("المحادثة الذكية", "Knowledge chat")] as [string, string]] : []),
    ["governance", T("الاعتمادات والتغييرات", "Approvals & changes")], ["value", T("المؤشرات والمنافع", "KPIs & benefits")], ...(can("report.read") ? [["reports", T("التقارير", "Reports")] as [string, string]] : []), ...(can("project.write") ? [["log", T("سجل الإنجاز", "Activity log")] as [string, string]] : [])];
  return <div className="page">
    <Async q={q}>{p => { const stages: string[] = meta?.lifecycle || [], at = stages.indexOf(p.stage);
      return <>
        <div className="page-head"><div>
          <Link to="/projects" className="row small" style={{ gap: 2, textDecoration: "none" }}><ChevronLeft size={15} className="flip" style={{ transform: "scaleX(-1)" }} />{T("كل المشاريع", "All projects")}</Link>
          <h1>{N(p)}</h1><div className="row small" style={{ marginBlockStart: 4 }}><bdi className="muted">{p.code}</bdi><Status v={p.status} /><Status v={p.metrics.health} /><span className="muted">{T("آخر تحديث", "Last update")} {date(p.last_update_at)}</span></div></div>
          {can("project.write") && <div className="row"><button className="btn" onClick={() => setEdit(true)}><Pencil />{T("عدّل بيانات المشروع", "Edit project")}</button>
            {(["super_admin", "pmo_director"].includes(user?.role_key) || p.manager_id === user?.id) && <button className="btn danger icon" onClick={() => setDel(true)} aria-label={T("احذف المشروع", "Delete project")}><Trash2 /></button>}</div>}</div>
        <ul className="rail-life" aria-label={T("دورة حياة المشروع", "Project lifecycle")}>{stages.map((s, i) => <li key={s} className={i < at ? "done" : i === at ? "now done" : ""}>{T(...(STAGE[s] || [s, s]))}</li>)}</ul>
        <div style={{ height: 14 }} />
        <Tabs tabs={tabs} value={tab} onChange={t => nav(`/projects/${pid}/${t}`)} />
        {tab === "overview" && <Overview p={p} reload={q.reload} />}
        {tab === "charter" && <Charter p={p} />}
        {tab === "planning" && <Planning pid={pid} />}
        {tab === "gantt" && <Schedule pid={pid} />}
        {tab === "risks" && <Risks pid={pid} />}
        {tab === "finance" && <Finance pid={pid} />}
        {tab === "resources" && <Resources pid={pid} />}
        {tab === "stakeholders" && <Stakeholders pid={pid} />}
        {tab === "documents" && <Documents pid={pid} />}
        {tab === "chat" && <Chat pid={pid} />}
        {tab === "governance" && <Governance p={p} reload={q.reload} />}
        {tab === "value" && <div className="stack">
          <Register resource="kpis" projectId={pid} perm="project.write" noun={["مؤشراً", "KPI"]} title={T("مؤشرات الأداء", "Key performance indicators")}
            cols={[{ key: "name", label: ["المؤشر", "KPI"] }, { key: "unit", label: ["الوحدة", "Unit"] }, { key: "baseline", label: ["خط الأساس", "Baseline"], type: "num" }, { key: "target", label: ["المستهدف", "Target"], type: "num" }, { key: "actual", label: ["الفعلي", "Actual"], type: "num" },
              { key: "ach", label: ["التحقق", "Achievement"], render: r => r.target && r.actual != null ? <Progress v={Math.min(100, r.direction === "down" ? (r.target / r.actual) * 100 : (r.actual / r.target) * 100)} /> : "—" }, { key: "owner_name", label: ["المالك", "Owner"] }, { key: "source_tag", label: ["المصدر", "Source"], type: "src" }]}
            fields={[{ key: "name", label: ["المؤشر", "KPI"], required: true, wide: true }, { key: "unit", label: ["الوحدة", "Unit"] }, { key: "direction", label: ["الاتجاه", "Direction"], type: "select", def: "up", required: true, options: [["up", T("الأعلى أفضل", "Higher is better")], ["down", T("الأقل أفضل", "Lower is better")]] },
              { key: "baseline", label: ["خط الأساس", "Baseline"], type: "number" }, { key: "target", label: ["المستهدف", "Target"], type: "number" }, { key: "actual", label: ["الفعلي", "Actual"], type: "number" },
              { key: "frequency", label: ["دورية القياس", "Frequency"], type: "select", def: "monthly", options: [["weekly", T("أسبوعي", "Weekly")], ["monthly", T("شهري", "Monthly")], ["quarterly", T("ربع سنوي", "Quarterly")]] }, { key: "owner_name", label: ["المالك", "Owner"] }]} />
          <BenefitsRegister pid={pid} /><LessonsRegister pid={pid} /></div>}
        {tab === "reports" && <ReportBuilder fixedProject={pid} />}
        {tab === "log" && <section className="panel"><header><div><h2>{T("سجل الإنجاز", "Activity log")}</h2><p>{T("آخر 25 عملية على هذا المشروع من سجل التدقيق", "The last 25 operations on this project, from the audit trail")}</p></div></header>
          <div className="tbl-wrap"><table className="tbl"><thead><tr><th>{T("الوقت", "When")}</th><th>{T("المستخدم", "User")}</th><th>{T("العملية", "Operation")}</th><th>{T("التفاصيل", "Details")}</th></tr></thead>
            <tbody>{p.progress_log.map((a: any) => <tr key={a.id}><td className="small">{date(a.created_at)} <bdi>{String(a.created_at).slice(11, 16)}</bdi></td><td><bdi>{a.user_email || "—"}</bdi></td><td><bdi>{a.action}</bdi></td><td className="small muted" style={{ maxWidth: 520, overflowWrap: "anywhere" }}><bdi>{JSON.stringify(a.detail).slice(0, 220)}</bdi></td></tr>)}</tbody></table></div></section>}
        {edit && <FormModal title={T("تعديل بيانات المشروع", "Edit project")} fields={projectFields(T, meta, N, lists)} initial={p} onClose={() => setEdit(false)} onSave={async v => { await api.patch(`/projects/${pid}`, v); q.reload(); }} />}
        {del && <Confirm title={T("حذف المشروع", "Delete project")} text={T(`سيحذف «${N(p)}» بكل أنشطته ومخاطره ووثائقه ومحادثاته نهائياً.`, `“${N(p)}” and all its activities, risks, documents and conversations will be permanently deleted.`)} onClose={() => setDel(false)} onYes={async () => { await api.del(`/projects/${pid}`); nav("/projects"); }} />}
      </>; }}</Async>
  </div>;
}
