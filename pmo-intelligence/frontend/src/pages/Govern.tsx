import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Check, Play, Plus, Trash2, X } from "lucide-react";
import { api, useApp, useLoad } from "../lib/core";
import { Async, Modal, Register, Status, Tabs } from "../lib/ui";
import { CAT } from "./Dashboard";

/* ---------------- governance ---------------- */
function StepsEditor({ value, onChange }: { value: any[]; onChange: (v: any[]) => void }) {
  const { T, meta, N } = useApp();
  const set = (i: number, k: string, v: any) => onChange(value.map((s, j) => (j === i ? { ...s, [k]: v } : s)));
  return <div className="stack tight">{value.map((s, i) => <div key={i} className="row"><span className="num muted">{i + 1}</span>
    <input className="input grow" style={{ width: "auto" }} placeholder={T("اسم الخطوة (عربي)", "Step name (Arabic)")} value={s.name_ar || ""} onChange={e => set(i, "name_ar", e.target.value)} />
    <input className="input grow" style={{ width: "auto" }} placeholder="Step name (English)" value={s.name_en || ""} onChange={e => set(i, "name_en", e.target.value)} dir="ltr" />
    <select className="input" style={{ width: 190 }} value={s.approver_role || ""} onChange={e => set(i, "approver_role", e.target.value)} aria-label={T("صاحب الصلاحية", "Approver")}>{(meta?.roles || []).map((r: any) => <option key={r.key} value={r.key}>{N(r)}</option>)}</select>
    <input className="input num" style={{ width: 80 }} type="number" min={1} value={s.sla_days || 5} onChange={e => set(i, "sla_days", +e.target.value)} title={T("المهلة بالأيام", "SLA in days")} aria-label={T("المهلة بالأيام", "SLA in days")} />
    <button type="button" className="btn ghost icon danger" onClick={() => onChange(value.filter((_, j) => j !== i))} aria-label={T("احذف الخطوة", "Remove step")}><Trash2 /></button></div>)}
    <div><button type="button" className="btn sm" onClick={() => onChange([...value, { name_ar: "", name_en: "", approver_role: "pmo_director", sla_days: 5 }])}><Plus />{T("أضف خطوة", "Add step")}</button></div></div>;
}

function Workflows() {
  const { T, can, fail, toast } = useApp();
  const q = useLoad<any[]>("/r/workflow_definitions");
  const [edit, setEdit] = useState<any>(null);
  const write = can("governance.write");
  const save = async () => { try { if (!edit.key || !edit.steps?.length) throw new Error(T("أدخل رمزاً وخطوة واحدة على الأقل.", "Enter a key and at least one step.")); edit.id ? await api.patch(`/r/workflow_definitions/${edit.id}`, edit) : await api.post("/r/workflow_definitions", edit); toast(T("حُفظ المسار", "Workflow saved")); setEdit(null); q.reload(); } catch (e) { fail(e); } };
  return <section className="panel"><header><div><h2>{T("مسارات الاعتماد", "Approval workflows")}</h2><p>{T("عدّل الخطوات وأصحاب الصلاحية والمهل وفق هيكل مؤسستك.", "Change steps, approvers and time limits to match your organisation.")}</p></div>
    {write && <button className="btn primary sm" onClick={() => setEdit({ key: "", name_ar: "", name_en: "", steps: [], is_active: true })}><Plus />{T("مسار جديد", "New workflow")}</button>}</header>
    <Async q={q}>{rows => <div className="tbl-wrap"><table className="tbl"><thead><tr><th>{T("المسار", "Workflow")}</th><th>{T("الخطوات", "Steps")}</th><th>{T("الحالة", "State")}</th><th /></tr></thead>
      <tbody>{rows.map((w: any) => <tr key={w.id}><td><b>{T(w.name_ar, w.name_en)}</b><div className="small muted"><bdi>{w.key}</bdi></div></td><td className="small">{w.steps.map((s: any, i: number) => <span key={i}>{i > 0 && " ← "}{T(s.name_ar, s.name_en)}</span>)}</td>
        <td>{w.is_active ? <span className="tag good">{T("مفعّل", "Active")}</span> : <span className="tag">{T("موقوف", "Inactive")}</span>}</td><td className="act">{write && <button className="btn ghost sm" onClick={() => setEdit(JSON.parse(JSON.stringify(w)))}>{T("عدّل", "Edit")}</button>}</td></tr>)}</tbody></table></div>}</Async>
    {edit && <Modal wide title={edit.id ? T("تعديل مسار الاعتماد", "Edit workflow") : T("مسار اعتماد جديد", "New workflow")} onClose={() => setEdit(null)} footer={<><button className="btn" onClick={() => setEdit(null)}>{T("إلغاء", "Cancel")}</button><button className="btn primary" onClick={save}>{T("حفظ", "Save")}</button></>}>
      <div className="stack"><div className="form-grid"><label className="field"><span>{T("الرمز", "Key")}</span><input className="input" dir="ltr" value={edit.key} disabled={!!edit.id} onChange={e => setEdit({ ...edit, key: e.target.value })} /></label>
        <label className="field"><span>{T("مفعّل", "Active")}</span><label className="row"><input type="checkbox" checked={edit.is_active} onChange={e => setEdit({ ...edit, is_active: e.target.checked })} />{T("نعم", "Yes")}</label></label>
        <label className="field"><span>{T("الاسم (عربي)", "Name (Arabic)")}</span><input className="input" value={edit.name_ar} onChange={e => setEdit({ ...edit, name_ar: e.target.value })} /></label>
        <label className="field"><span>{T("الاسم (إنجليزي)", "Name (English)")}</span><input className="input" dir="ltr" value={edit.name_en} onChange={e => setEdit({ ...edit, name_en: e.target.value })} /></label></div>
        <h3>{T("الخطوات بالترتيب", "Steps in order")}</h3><StepsEditor value={edit.steps} onChange={steps => setEdit({ ...edit, steps })} /></div></Modal>}
  </section>;
}

export function Governance() {
  const { T, N, date, fail, toast, can } = useApp();
  const [tab, setTab] = useState("approvals");
  const ap = useLoad<any[]>("/approvals");
  const inst = useLoad<any[]>(tab === "workflows" ? "/workflows/instances" : null);
  const audit = useLoad<any[]>(tab === "audit" && can("audit.read") ? "/audit?limit=300" : null);
  const [dec, setDec] = useState<any>(null);
  const [note, setNote] = useState("");
  const [flt, setFlt] = useState("");
  const decide = (approve: boolean) => api.post(`/approvals/${dec.id}/decide`, { approve, note }).then(() => { toast(approve ? T("اعتُمد", "Approved") : T("رُفض", "Rejected")); setDec(null); setNote(""); ap.reload(); }).catch(fail);
  const kinds: [string, string, string][] = [["policy", "السياسات", "Policies"], ["methodology", "المنهجيات", "Methodologies"], ["template", "قوالب الوثائق", "Document templates"], ["committee", "اللجان", "Committees"], ["exception", "الاستثناءات", "Exceptions"], ["quality_review", "مراجعات الجودة", "Quality reviews"]];
  return <div className="page">
    <div className="page-head"><div><h1>{T("حوكمة مكتب إدارة المشاريع", "PMO governance")}</h1><p>{T("السياسات والمنهجيات واللجان، وبوابات الاعتماد وصلاحياتها، وسجل التدقيق.", "Policies, methodologies and committees; stage gates and who approves them; and the audit trail.")}</p></div></div>
    <Tabs value={tab} onChange={setTab} tabs={[["approvals", T("الاعتمادات", "Approvals")], ["workflows", T("مسارات الاعتماد", "Workflows")], ["library", T("السياسات واللجان", "Policies & committees")], ["compliance", T("الالتزام", "Compliance")], ...(can("audit.read") ? [["audit", T("سجل التدقيق", "Audit trail")] as [string, string]] : [])]} />
    {tab === "approvals" && <section className="panel"><header><div><h2>{T("الاعتمادات", "Approvals")}</h2><p>{T("المعلّق منها أولاً. يقرر صاحب الصلاحية المحدد في كل خطوة.", "Pending first. The approver named on each step decides.")}</p></div></header>
      <Async q={ap}>{rows => rows.length === 0 ? <div className="empty">{T("لا اعتمادات.", "No approvals.")}</div> : <div className="tbl-wrap"><table className="tbl"><thead><tr><th>{T("الاعتماد", "Approval")}</th><th>{T("المشروع", "Project")}</th><th>{T("صاحب الصلاحية", "Approver")}</th><th>{T("طُلب في", "Requested")}</th><th>{T("الاستحقاق", "Due")}</th><th>{T("الحالة", "Status")}</th><th /></tr></thead>
        <tbody>{[...rows].sort((a, b) => (a.status === "pending" ? 0 : 1) - (b.status === "pending" ? 0 : 1)).map((a: any) => <tr key={a.id}><td>{a.title}{a.note && <div className="small muted">{a.note}</div>}</td><td>{a.project_id ? <Link to={`/projects/${a.project_id}/governance`}>{N(a, "project_name")}</Link> : "—"}</td>
          <td><bdi>{a.approver_role}</bdi></td><td>{date(a.requested_at)}</td><td>{date(a.due_date)}</td><td><Status v={a.status} /></td>
          <td className="act">{a.status === "pending" && a.can_decide && <button className="btn sm primary" onClick={() => setDec(a)}>{T("اتخذ القرار", "Decide")}</button>}</td></tr>)}</tbody></table></div>}</Async></section>}
    {tab === "workflows" && <div className="stack"><Workflows />
      <section className="panel"><header><h2>{T("المسارات الجارية والمنتهية", "Running and finished workflows")}</h2></header><Async q={inst}>{rows => rows.length === 0 ? <div className="empty">{T("لم يبدأ أي مسار بعد.", "No workflow has started yet.")}</div> : <div className="tbl-wrap"><table className="tbl"><thead><tr><th>{T("المسار", "Workflow")}</th><th>{T("المشروع", "Project")}</th><th>{T("الخطوة الحالية", "Current step")}</th><th>{T("الحالة", "Status")}</th><th>{T("السجل", "History")}</th></tr></thead>
        <tbody>{rows.map((i: any) => <tr key={i.id}><td>{N(i, "definition_name")}</td><td>{i.project_id ? <Link to={`/projects/${i.project_id}/governance`}>{N(i, "project_name")}</Link> : "—"}</td><td>{i.status === "running" ? `${i.current_step + 1}/${i.steps.length} — ${T(i.steps[i.current_step]?.name_ar, i.steps[i.current_step]?.name_en)}` : "—"}</td>
          <td><Status v={i.status} /></td><td className="small muted">{(i.history || []).map((h: any) => `${h.name}: ${h.decision}`).join(" · ") || "—"}</td></tr>)}</tbody></table></div>}</Async></section></div>}
    {tab === "library" && <div className="stack"><div className="row">{kinds.map(([k, a, e]) => <button key={k} className={`btn sm ${flt === k ? "primary" : ""}`} onClick={() => setFlt(flt === k ? "" : k)} aria-pressed={flt === k}>{T(a, e)}</button>)}</div>
      <Register resource="governance" perm="governance.write" noun={["بنداً", "Item"]} title={T("مكتبة الحوكمة", "Governance library")} filter={r => !flt || r.kind === flt}
        cols={[{ key: "kind", label: ["النوع", "Kind"], render: r => { const k = kinds.find(x => x[0] === r.kind); return <span className="tag">{k ? T(k[1], k[2]) : r.kind}</span>; } }, { key: "title", label: ["العنوان", "Title"], render: r => <b>{r.title}</b> }, { key: "body", label: ["المحتوى", "Content"] }, { key: "owner_name", label: ["المالك", "Owner"] }, { key: "status", label: ["الحالة", "Status"], render: r => <Status v={r.status === "active" ? "active_" : r.status} /> }]}
        fields={[{ key: "kind", label: ["النوع", "Kind"], type: "select", required: true, def: flt || "policy", options: kinds.map(([k, a, e]) => [k, T(a, e)]) }, { key: "title", label: ["العنوان", "Title"], required: true }, { key: "owner_name", label: ["المالك", "Owner"] },
          { key: "status", label: ["الحالة", "Status"], type: "select", def: "active", required: true, options: [["active", T("سارٍ", "Active")], ["draft", T("مسودة", "Draft")], ["expired", T("منتهٍ", "Expired")]] }, { key: "body", label: ["المحتوى", "Content"], type: "textarea" }]} /></div>}
    {tab === "compliance" && <Compliance />}
    {tab === "audit" && <section className="panel"><header><div><h2>{T("سجل التدقيق", "Audit trail")}</h2><p>{T("كل عملية حساسة: من، ماذا، متى، وعلى أي مشروع. لا يُعدَّل ولا يُحذف من الواجهة.", "Every sensitive operation: who, what, when and on which project. It cannot be edited or deleted from the interface.")}</p></div>
      <input className="input" style={{ width: 220 }} placeholder={T("تصفية بالعملية أو المستخدم…", "Filter by operation or user…")} value={flt} onChange={e => setFlt(e.target.value)} aria-label={T("تصفية", "Filter")} /></header>
      <Async q={audit}>{rows => <div className="tbl-wrap" style={{ maxHeight: "65vh" }}><table className="tbl"><thead><tr><th>{T("الوقت (UTC)", "Time (UTC)")}</th><th>{T("المستخدم", "User")}</th><th>{T("العملية", "Operation")}</th><th>{T("الكيان", "Entity")}</th><th>{T("المشروع", "Project")}</th><th>{T("التفاصيل", "Details")}</th></tr></thead>
        <tbody>{rows.filter((a: any) => !flt || `${a.action} ${a.user_email}`.toLowerCase().includes(flt.toLowerCase())).map((a: any) => <tr key={a.id}><td className="small"><bdi>{String(a.created_at).replace("T", " ").slice(0, 19)}</bdi></td><td><bdi>{a.user_email || "—"}</bdi></td><td><bdi>{a.action}</bdi></td>
          <td><bdi>{a.entity_type}{a.entity_id ? ` #${a.entity_id}` : ""}</bdi></td><td className="num">{a.project_id ?? "—"}</td><td className="small muted" style={{ maxWidth: 420, overflowWrap: "anywhere" }}><bdi>{JSON.stringify(a.detail).slice(0, 200)}</bdi></td></tr>)}</tbody></table></div>}</Async></section>}
    {dec && <Modal title={dec.title} onClose={() => setDec(null)} footer={<><button className="btn danger" onClick={() => decide(false)}><X />{T("ارفض", "Reject")}</button><button className="btn primary" onClick={() => decide(true)}><Check />{T("اعتمد", "Approve")}</button></>}>
      <div className="stack"><p>{T("المشروع", "Project")}: <b>{N(dec, "project_name") || "—"}</b></p><label className="field"><span>{T("ملاحظة القرار (تُحفظ في السجل)", "Decision note (kept on record)")}</span><textarea className="input" dir="auto" value={note} onChange={e => setNote(e.target.value)} /></label></div></Modal>}
  </div>;
}

function Compliance() {
  const { T, fail, lang } = useApp();
  const [rep, setRep] = useState<any>(null);
  useEffect(() => { api.post("/reports/build", { type: "governance_compliance", lang }).then(setRep).catch(fail); }, [lang]);  // eslint-disable-line
  if (!rep) return <div className="loading"><i className="spin" /></div>;
  return <section className="panel"><header><div><h2>{rep.title}</h2><p>{rep.summary.join(" ")}</p></div><Link className="btn sm" to="/reports">{T("صدّر من التقارير", "Export from Reports")}</Link></header>
    <div className="body stack">{rep.sections.map((s: any, i: number) => s.kind === "kpis" ? <div key={i} className="grid g4">{s.items.map((it: any) => <div key={it.label}><div className="small muted">{it.label}</div><div className="strong" style={{ fontSize: "1.3rem" }}>{String(it.value)}</div></div>)}</div>
      : <div key={i} className="tbl-wrap"><table className="tbl"><thead><tr>{s.head.map((h: string) => <th key={h}>{h}</th>)}</tr></thead><tbody>{s.rows.map((r: any[], j: number) => <tr key={j}>{r.map((c, k) => <td key={k}>{String(c ?? "—")}</td>)}</tr>)}</tbody></table></div>)}</div></section>;
}

/* ---------------- automation ---------------- */
const TRIG: Record<string, [string, string]> = { event: ["عند حدث", "On an event"], schedule: ["مجدولة", "Scheduled"], rule: ["قاعدة بشرط", "Rule with condition"], ai: ["بالذكاء الاصطناعي", "AI-based"], manual: ["يدوية", "Manual"] };
const EVT: Record<string, [string, string]> = { "project.created": ["إنشاء مشروع", "Project created"], "charter.uploaded": ["رفع ميثاق", "Charter uploaded"], "charter.approved": ["اعتماد بيانات الميثاق", "Charter data approved"], "project.activated": ["تفعيل مشروع", "Project activated"],
  "document.uploaded": ["رفع وثيقة", "Document uploaded"], "alert.created": ["صدور تنبيه", "Alert raised"], "risk.critical": ["خطر أصبح حرجاً", "Risk became critical"], "phase.completed": ["اكتمال مرحلة", "Phase completed"], "project.completed": ["اكتمال مشروع", "Project completed"], "approval.decided": ["صدور قرار اعتماد", "Approval decided"], "schedule.tick": ["نبضة الجدولة", "Scheduler tick"] };
const ACT: Record<string, [string, string]> = { notify: ["أرسل إشعاراً", "Send a notification"], start_workflow: ["ابدأ مسار اعتماد", "Start a workflow"], request_gate_approval: ["اطلب اعتماد البوابة", "Request gate approval"], run_early_warning: ["شغّل الإنذار المبكر", "Run early warning"],
  create_closure_report: ["أنشئ تقرير الإغلاق", "Create the closure report"], reindex_knowledge: ["حدّث قاعدة المعرفة", "Refresh the knowledge base"], generate_wbs: ["ولّد هيكل العمل", "Generate the WBS"], start_ai_analysis: ["ابدأ تحليل الميثاق", "Start charter analysis"], ai_summary_alert: ["أرسل ملخصاً ذكياً", "Send an AI brief"], webhook: ["استدعِ نظاماً خارجياً (Webhook)", "Call an external system (webhook)"] };

function RuleEditor({ rule, onClose, onSaved }: { rule: any; onClose: () => void; onSaved: () => void }) {
  const { T, N, meta, fail, toast } = useApp();
  const [v, setV] = useState<any>(() => ({ trigger_type: "event", event: "alert.created", schedule: "daily", conditions: [], actions: [{ type: "notify", roles: ["pmo_director"], message: "" }], enabled: true, name_ar: "", name_en: "", ...JSON.parse(JSON.stringify(rule)) }));
  const [defs] = [useLoad<any[]>("/r/workflow_definitions")];
  const setA = (i: number, k: string, val: any) => setV({ ...v, actions: v.actions.map((a: any, j: number) => (j === i ? { ...a, [k]: val } : a)) });
  const setC = (i: number, k: string, val: any) => setV({ ...v, conditions: v.conditions.map((a: any, j: number) => (j === i ? { ...a, [k]: val } : a)) });
  const save = async () => { try { if (!v.name_ar && !v.name_en) throw new Error(T("سمِّ القاعدة.", "Name the rule.")); if (!v.actions.length) throw new Error(T("أضف إجراءً واحداً على الأقل.", "Add at least one action."));
    const body = { ...v, name_en: v.name_en || v.name_ar, name_ar: v.name_ar || v.name_en, event: ["event", "rule", "ai"].includes(v.trigger_type) ? v.event : null, schedule: v.trigger_type === "schedule" ? v.schedule : null };
    v.id ? await api.patch(`/r/automation_rules/${v.id}`, body) : await api.post("/r/automation_rules", body); toast(T("حُفظت القاعدة", "Rule saved")); onSaved(); onClose(); } catch (e) { fail(e); } };
  return <Modal wide title={v.id ? T("تعديل قاعدة الأتمتة", "Edit automation rule") : T("قاعدة أتمتة جديدة", "New automation rule")} onClose={onClose} footer={<><button className="btn" onClick={onClose}>{T("إلغاء", "Cancel")}</button><button className="btn primary" onClick={save}>{T("حفظ", "Save")}</button></>}>
    <div className="stack"><div className="form-grid">
      <label className="field"><span>{T("اسم القاعدة (عربي)", "Rule name (Arabic)")}</span><input className="input" value={v.name_ar} onChange={e => setV({ ...v, name_ar: e.target.value })} /></label>
      <label className="field"><span>{T("اسم القاعدة (إنجليزي)", "Rule name (English)")}</span><input className="input" dir="ltr" value={v.name_en} onChange={e => setV({ ...v, name_en: e.target.value })} /></label>
      <label className="field"><span>{T("متى تعمل؟", "When does it run?")}</span><select className="input" value={v.trigger_type} onChange={e => setV({ ...v, trigger_type: e.target.value })}>{Object.entries(TRIG).map(([k, l]) => <option key={k} value={k}>{T(...l)}</option>)}</select></label>
      {["event", "rule", "ai"].includes(v.trigger_type) && <label className="field"><span>{T("الحدث", "Event")}</span><select className="input" value={v.event || ""} onChange={e => setV({ ...v, event: e.target.value })}>{(meta?.events || []).map((k: string) => <option key={k} value={k}>{T(...(EVT[k] || [k, k]))}</option>)}</select></label>}
      {v.trigger_type === "schedule" && <label className="field"><span>{T("الدورية", "Frequency")}</span><select className="input" value={v.schedule || "daily"} onChange={e => setV({ ...v, schedule: e.target.value })}><option value="hourly">{T("كل ساعة", "Hourly")}</option><option value="daily">{T("يومياً", "Daily")}</option><option value="weekly">{T("أسبوعياً", "Weekly")}</option></select></label>}
      <label className="field"><span>{T("مفعّلة", "Enabled")}</span><label className="row"><input type="checkbox" checked={v.enabled} onChange={e => setV({ ...v, enabled: e.target.checked })} />{T("نعم", "Yes")}</label></label></div>
      {["event", "rule", "ai"].includes(v.trigger_type) && <div className="stack tight"><h3>{T("الشروط (كلها يجب أن تتحقق)", "Conditions (all must hold)")}</h3>
        {v.conditions.map((c: any, i: number) => <div className="row" key={i}><input className="input" style={{ width: 170 }} dir="ltr" placeholder="rule_key / severity / doc_type" value={c.field || ""} onChange={e => setC(i, "field", e.target.value)} aria-label={T("الحقل", "Field")} />
          <select className="input" style={{ width: 130 }} value={c.op || "eq"} onChange={e => setC(i, "op", e.target.value)} aria-label={T("المقارنة", "Operator")}><option value="eq">=</option><option value="ne">≠</option><option value="gt">&gt;</option><option value="lt">&lt;</option><option value="in">{T("ضمن", "in")}</option><option value="contains">{T("يحتوي", "contains")}</option></select>
          <input className="input grow" style={{ width: "auto" }} dir="ltr" value={Array.isArray(c.value) ? c.value.join(",") : c.value ?? ""} onChange={e => setC(i, "value", c.op === "in" ? e.target.value.split(",").map(x => x.trim()) : e.target.value)} aria-label={T("القيمة", "Value")} />
          <button className="btn ghost icon danger" onClick={() => setV({ ...v, conditions: v.conditions.filter((_: any, j: number) => j !== i) })} aria-label={T("احذف الشرط", "Remove condition")}><Trash2 /></button></div>)}
        <div><button className="btn sm" onClick={() => setV({ ...v, conditions: [...v.conditions, { field: "rule_key", op: "eq", value: "" }] })}><Plus />{T("أضف شرطاً", "Add condition")}</button></div></div>}
      <div className="stack tight"><h3>{T("الإجراءات", "Actions")}</h3>
        {v.actions.map((a: any, i: number) => <div key={i} className="stack tight" style={{ border: "1px solid var(--line-2)", borderRadius: 4, padding: 10 }}><div className="row">
          <select className="input" style={{ width: 230 }} value={a.type} onChange={e => setA(i, "type", e.target.value)} aria-label={T("الإجراء", "Action")}>{(meta?.actions || []).map((k: string) => <option key={k} value={k}>{T(...(ACT[k] || [k, k]))}</option>)}</select>
          {a.type === "start_workflow" && <select className="input" style={{ width: 220 }} value={a.workflow || "project_lifecycle"} onChange={e => setA(i, "workflow", e.target.value)} aria-label={T("المسار", "Workflow")}>{(defs.data || []).map(d => <option key={d.key} value={d.key}>{T(d.name_ar, d.name_en)}</option>)}</select>}
          {a.type === "notify" && <><input className="input grow" style={{ width: "auto" }} placeholder={T("نص الإشعار — يمكن استخدام {title} و {project}", "Message — {title} and {project} are available")} value={a.message || ""} onChange={e => setA(i, "message", e.target.value)} />
            <label className="row small"><input type="checkbox" checked={!!a.include_manager} onChange={e => setA(i, "include_manager", e.target.checked)} />{T("ومدير المشروع", "plus the project manager")}</label></>}
          {a.type === "webhook" && <input className="input grow" style={{ width: "auto" }} dir="ltr" placeholder="https://… (Teams, Power Automate, Jira, ERP)" value={a.url || ""} onChange={e => setA(i, "url", e.target.value)} aria-label="Webhook URL" />}
          <span className="grow" /><button className="btn ghost icon danger" onClick={() => setV({ ...v, actions: v.actions.filter((_: any, j: number) => j !== i) })} aria-label={T("احذف الإجراء", "Remove action")}><Trash2 /></button></div>
          {a.type === "webhook" && <p className="small muted">{T("يُرسل اسم الحدث ورمز المشروع وعنوان التنبيه فقط. لا يُرسل محتوى الوثائق أبداً.", "Sends only the event name, project code and alert title. Document content is never sent.")}</p>}
          {["notify", "ai_summary_alert"].includes(a.type) && <div className="row small"><span>{T("إلى:", "To:")}</span>{(meta?.roles || []).map((r: any) => <label key={r.key} className="tag" style={{ cursor: "pointer" }}><input type="checkbox" checked={(a.roles || []).includes(r.key)} onChange={e => setA(i, "roles", e.target.checked ? [...(a.roles || []), r.key] : (a.roles || []).filter((x: string) => x !== r.key))} />{N(r)}</label>)}</div>}</div>)}
        <div><button className="btn sm" onClick={() => setV({ ...v, actions: [...v.actions, { type: "notify", roles: ["pmo_director"], message: "" }] })}><Plus />{T("أضف إجراءً", "Add action")}</button></div></div>
    </div></Modal>;
}

export function Automation() {
  const { T, N, can, date, fail, toast, meta } = useApp();
  const [tab, setTab] = useState("rules");
  const rules = useLoad<any[]>("/r/automation_rules");
  const runs = useLoad<any[]>(tab === "runs" ? "/automation/runs?limit=200" : null);
  const [edit, setEdit] = useState<any>(null);
  const write = can("automation.write");
  const run = (r: any) => api.post(`/automation/rules/${r.id}/run`, {}).then(x => { toast(`${T("النتيجة", "Result")}: ${x.result || x.error || x.status}`, x.status === "failed" ? "error" : "ok"); rules.reload(); runs.reload(); }).catch(fail);
  const sev = (meta?.severities || []).map((s: string) => [s, s]) as [string, string][];
  return <div className="page">
    <div className="page-head"><div><h1>{T("سير العمل والأتمتة", "Workflow and automation")}</h1><p>{T("قواعد تشغيلية بلا برمجة: حدث أو موعد أو شرط، ثم إجراء. لكل تنفيذ سجل بحالته ونتيجته وأخطائه.", "Operating rules without code: an event, a schedule or a condition, then an action. Every run is logged with its status, result and errors.")}</p></div></div>
    <Tabs value={tab} onChange={setTab} tabs={[["rules", T("قواعد الأتمتة", "Automation rules")], ["runs", T("سجل التنفيذ", "Run log")], ["alerts", T("قواعد الإنذار المبكر", "Early-warning rules")]]} />
    {tab === "rules" && <section className="panel"><header><h2>{T("قواعد الأتمتة", "Automation rules")}</h2>{write && <button className="btn primary sm" onClick={() => setEdit({})}><Plus />{T("قاعدة جديدة", "New rule")}</button>}</header>
      <Async q={rules}>{rows => <div className="tbl-wrap"><table className="tbl"><thead><tr><th>{T("القاعدة", "Rule")}</th><th>{T("المشغّل", "Trigger")}</th><th>{T("الشروط", "Conditions")}</th><th>{T("الإجراءات", "Actions")}</th><th>{T("آخر تشغيل", "Last run")}</th><th>{T("مفعّلة", "Enabled")}</th><th /></tr></thead>
        <tbody>{rows.map((r: any) => <tr key={r.id}><td className="strong">{N(r)}</td><td><span className="tag">{T(...TRIG[r.trigger_type])}</span> {r.event && T(...(EVT[r.event] || [r.event, r.event]))}{r.schedule && ` · ${r.schedule}`}</td>
          <td className="small"><bdi>{(r.conditions || []).map((c: any) => `${c.field} ${c.op} ${Array.isArray(c.value) ? c.value.join("|") : c.value}`).join(" & ") || "—"}</bdi></td><td className="small">{(r.actions || []).map((a: any) => T(...(ACT[a.type] || [a.type, a.type]))).join(T("، ", ", "))}</td><td>{date(r.last_run_at)}</td>
          <td>{write ? <input type="checkbox" checked={r.enabled} aria-label={T("مفعّلة", "Enabled")} onChange={e => api.patch(`/r/automation_rules/${r.id}`, { enabled: e.target.checked }).then(() => rules.reload()).catch(fail)} /> : r.enabled ? T("نعم", "Yes") : T("لا", "No")}</td>
          <td className="act">{write && <><button className="btn ghost sm" onClick={() => run(r)}><Play className="flip" />{T("شغّل الآن", "Run now")}</button><button className="btn ghost sm" onClick={() => setEdit(r)}>{T("عدّل", "Edit")}</button>
            <button className="btn ghost sm icon danger" aria-label={T("حذف", "Delete")} onClick={() => api.del(`/r/automation_rules/${r.id}`).then(() => rules.reload()).catch(fail)}><Trash2 /></button></>}</td></tr>)}</tbody></table></div>}</Async></section>}
    {tab === "runs" && <section className="panel"><header><div><h2>{T("سجل التنفيذ", "Run log")}</h2><p>{T("آخر 200 تنفيذ. الفاشل منها يذكر الخطأ كما وقع.", "The last 200 runs. Failed ones show the error as it happened.")}</p></div></header>
      <Async q={runs}>{rows => rows.length === 0 ? <div className="empty">{T("لم تُنفذ أي قاعدة بعد.", "No rule has run yet.")}</div> : <div className="tbl-wrap" style={{ maxHeight: "65vh" }}><table className="tbl"><thead><tr><th>{T("الوقت (UTC)", "Time (UTC)")}</th><th>{T("القاعدة", "Rule")}</th><th>{T("المشغّل", "Trigger")}</th><th>{T("الحالة", "Status")}</th><th>{T("النتيجة أو الخطأ", "Result or error")}</th></tr></thead>
        <tbody>{rows.map((r: any) => <tr key={r.id}><td className="small"><bdi>{String(r.started_at).replace("T", " ").slice(0, 19)}</bdi></td><td>{N(r, "rule_name")}</td><td><bdi>{r.trigger}</bdi></td><td><Status v={r.status} /></td><td className="small" style={{ color: r.error ? "var(--critical)" : undefined }}><bdi>{r.error || r.result || "—"}</bdi></td></tr>)}</tbody></table></div>}</Async></section>}
    {tab === "alerts" && <Register resource="alert_rules" perm="automation.write" noun={["قاعدة إنذار", "Alert rule"]} title={T("قواعد الإنذار المبكر", "Early-warning rules")}
      sub={T("لكل قاعدة حد ومستوى ومستلمون وتصعيد. التعديل يسري في الفحص التالي.", "Each rule has a threshold, a level, recipients and an escalation. Changes apply at the next check.")}
      cols={[{ key: "category", label: ["النوع", "Type"], render: r => T(...(CAT[r.category] || [r.category, r.category])) }, { key: "name", label: ["القاعدة", "Rule"], render: r => N(r) }, { key: "threshold", label: ["الحد", "Threshold"], type: "num" }, { key: "severity", label: ["المستوى", "Level"], type: "status" },
        { key: "recipient_roles", label: ["المستلمون", "Recipients"], render: r => (r.recipient_roles || []).map((k: string) => N((meta?.roles || []).find((x: any) => x.key === k))).join(T("، ", ", ")) }, { key: "channels", label: ["القنوات", "Channels"], render: r => (r.channels || []).join(", ") },
        { key: "escalate_after_days", label: ["التصعيد بعد (يوم)", "Escalate after (days)"], type: "num" }, { key: "enabled", label: ["مفعّلة", "Enabled"], render: r => r.enabled ? T("نعم", "Yes") : T("لا", "No") }]}
      fields={[{ key: "name_ar", label: ["الاسم (عربي)", "Name (Arabic)"], required: true }, { key: "name_en", label: ["الاسم (إنجليزي)", "Name (English)"] }, { key: "threshold", label: ["الحد", "Threshold"], type: "number" }, { key: "severity", label: ["مستوى الإنذار", "Alert level"], type: "select", required: true, options: sev },
        { key: "enabled", label: ["مفعّلة", "Enabled"], type: "bool" }, { key: "escalate_after_days", label: ["صعّد بعد (يوم)، 0 = بلا تصعيد", "Escalate after (days), 0 = never"], type: "number" }, { key: "escalate_to_role", label: ["صعّد إلى", "Escalate to"], type: "select", options: (meta?.roles || []).map((r: any) => [r.key, N(r)]) },
        { key: "channels", label: ["قنوات الإشعار", "Notification channels"], type: "multi", options: [["in_app", T("داخل المنصة", "In the platform")], ["email", T("بريد إلكتروني (يتطلب ربط خادم البريد)", "Email (needs mail-server integration)")], ["teams", T("Teams (يتطلب الربط)", "Teams (needs integration)")]] },
        { key: "recipient_roles", label: ["المستلمون", "Recipients"], type: "multi", options: (meta?.roles || []).map((r: any) => [r.key, N(r)]) }]} />}
    {edit && <RuleEditor rule={edit} onClose={() => setEdit(null)} onSaved={rules.reload} />}
  </div>;
}
