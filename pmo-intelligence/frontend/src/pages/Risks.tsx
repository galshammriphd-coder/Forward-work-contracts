import { useState } from "react";
import { ListChecks, Plus, Trash2, X } from "lucide-react";
import { api, useApp, useLoad } from "../lib/core";
import { Async, FieldSpec, Modal, Register, Src, Status } from "../lib/ui";
import { RiskMatrix, Segments } from "../lib/charts";

function Responses({ risk, onClose, write }: { risk: any; onClose: () => void; write: boolean }) {
  const { T, date, fail } = useApp();
  const q = useLoad<any[]>("/r/risk_responses");
  const [v, setV] = useState<any>({ type: "mitigation", description: "", action_owner: "", target_date: "", progress: 0 });
  const rows = (q.data || []).filter(r => r.risk_id === risk.id);
  const run = (fn: () => Promise<any>) => fn().then(() => q.reload()).catch(fail);
  return <Modal wide title={`${T("خطط المعالجة", "Response plans")} — ${risk.title}`} onClose={onClose}>
    <div className="stack">
      <div className="grid g2 small"><div><b>{T("خطة التخفيف", "Mitigation plan")}</b><p>{risk.mitigation || "—"}</p></div><div><b>{T("خطة الطوارئ", "Contingency plan")}</b><p>{risk.contingency || "—"}</p></div></div>
      <div className="tbl-wrap"><table className="tbl"><thead><tr><th>{T("النوع", "Type")}</th><th>{T("الإجراء", "Action")}</th><th>{T("مالك الإجراء", "Action owner")}</th><th>{T("الموعد", "Target date")}</th><th style={{ width: 110 }}>{T("التقدم %", "Progress %")}</th><th /></tr></thead>
        <tbody>{rows.map(r => <tr key={r.id}><td>{r.type === "mitigation" ? T("تخفيف", "Mitigation") : T("طوارئ", "Contingency")}</td><td>{r.description}</td><td>{r.action_owner || "—"}</td><td>{date(r.target_date)}</td>
          <td>{write ? <input className="input inline num" type="number" min={0} max={100} defaultValue={r.progress} aria-label={T("التقدم", "Progress")} onBlur={e => +e.target.value !== r.progress && run(() => api.patch(`/r/risk_responses/${r.id}`, { progress: +e.target.value }))} /> : r.progress}</td>
          <td className="act">{write && <button className="btn ghost sm icon danger" aria-label={T("حذف", "Delete")} onClick={() => run(() => api.del(`/r/risk_responses/${r.id}`))}><Trash2 /></button>}</td></tr>)}
          {!rows.length && <tr><td colSpan={6} className="muted">{T("لا إجراءات مسجلة لهذا الخطر.", "No actions recorded for this risk.")}</td></tr>}</tbody></table></div>
      {write && <div className="row"><select className="input" style={{ width: 120 }} value={v.type} onChange={e => setV({ ...v, type: e.target.value })} aria-label={T("النوع", "Type")}><option value="mitigation">{T("تخفيف", "Mitigation")}</option><option value="contingency">{T("طوارئ", "Contingency")}</option></select>
        <input className="input grow" style={{ width: "auto" }} placeholder={T("الإجراء المطلوب", "Action to take")} value={v.description} onChange={e => setV({ ...v, description: e.target.value })} />
        <input className="input" style={{ width: 150 }} placeholder={T("مالك الإجراء", "Action owner")} value={v.action_owner} onChange={e => setV({ ...v, action_owner: e.target.value })} />
        <input className="input" style={{ width: 150 }} type="date" value={v.target_date} onChange={e => setV({ ...v, target_date: e.target.value })} aria-label={T("الموعد", "Target date")} />
        <button className="btn" disabled={!v.description} onClick={() => run(() => api.post("/r/risk_responses", { ...v, risk_id: risk.id })).then(() => setV({ ...v, description: "" }))}><Plus />{T("أضف إجراءً", "Add action")}</button></div>}
    </div></Modal>;
}

export default function Risks({ pid }: { pid?: number }) {
  const { T, can, num, N } = useApp();
  const [n, setN] = useState(0);
  const hm = useLoad<any>(`/risks/heatmap${pid ? `?project_id=${pid}` : ""}`, [n]);
  const sch = useLoad<any>(pid ? `/projects/${pid}/schedule` : null);
  const projects = useLoad<any[]>(pid ? null : "/projects");
  const [cell, setCell] = useState<any>(null);
  const [resp, setResp] = useState<any>(null);
  const write = can("risk.write");
  const pname = (id: number) => { const p = (projects.data || []).find(x => x.id === id); return p ? p.code : "—"; };
  const cats = ["جدول زمني", "مالية", "موردون", "موارد", "تقني", "نطاق", "جودة", "حوكمة", "أمن", "امتثال"];
  const fields: FieldSpec[] = [
    { key: "title", label: ["عنوان الخطر", "Risk title"], required: true, wide: true },
    { key: "scope_level", label: ["المستوى", "Level"], type: "select", def: pid ? "project" : "portfolio", required: true,
      options: pid ? [["project", T("المشروع", "Project")], ["phase", T("المرحلة", "Phase")], ["deliverable", T("المخرج", "Deliverable")], ["work_package", T("حزمة العمل", "Work package")], ["activity", T("النشاط", "Activity")]]
        : [["portfolio", T("المحفظة", "Portfolio")], ["program", T("البرنامج", "Programme")]] },
    { key: "category", label: ["الفئة", "Category"], type: "select", options: cats.map(c => [c, c]) },
    { key: "probability", label: ["الاحتمالية (1–5)", "Probability (1–5)"], type: "scale", def: 3 }, { key: "impact", label: ["الأثر (1–5)", "Impact (1–5)"], type: "scale", def: 3 },
    { key: "owner_name", label: ["مالك الخطر", "Risk owner"] }, { key: "status", label: ["الحالة", "Status"], type: "select", def: "open", required: true, options: [["open", T("مفتوح", "Open")], ["mitigating", T("قيد المعالجة", "Mitigating")], ["occurred", T("تحقق", "Occurred")], ["closed", T("مغلق", "Closed")]] },
    { key: "response_deadline", label: ["موعد الاستجابة", "Response deadline"], type: "date" }, { key: "trigger", label: ["المؤشر المنذر", "Trigger"] },
    { key: "mitigation", label: ["خطة التخفيف", "Mitigation plan"], type: "textarea" }, { key: "contingency", label: ["خطة الطوارئ", "Contingency plan"], type: "textarea" },
    { key: "residual_probability", label: ["الاحتمالية المتبقية", "Residual probability"], type: "scale" }, { key: "residual_impact", label: ["الأثر المتبقي", "Residual impact"], type: "scale" },
    ...(pid ? [{ key: "activity_ids", label: ["الأنشطة المرتبطة", "Related activities"] as [string, string], type: "multi" as const, options: () => (sch.data?.activities || []).filter((a: any) => !a.is_summary).map((a: any) => [a.id, a.name]) as [any, string][] }] : []),
    { key: "shared_key", label: ["مفتاح الخطر المشترك", "Shared-risk key"], hint: ["المخاطر التي تحمل المفتاح نفسه في عدة مشاريع تُحتسب مرة واحدة في المؤشرات المجمعة", "Risks with the same key across projects are counted once in aggregated indicators"] },
    { key: "description", label: ["الوصف", "Description"], type: "textarea" }];
  const lvl: Record<string, string> = { low: "var(--s-good)", moderate: "var(--s-warning)", high: "var(--s-serious)", critical: "var(--s-critical)" };
  return <div className="stack">
    <div className="grid g2">
      <section className="panel"><header><div><h2>{T("مصفوفة المخاطر", "Risk heatmap")}</h2><p>{T("الدرجة = الاحتمالية × الأثر. اضغط خانة لتصفية السجل.", "Score = probability × impact. Select a cell to filter the register.")}</p></div>
        {cell && <button className="btn sm" onClick={() => setCell(null)}><X />{T("أزل التصفية", "Clear filter")}</button>}</header>
        <div className="body"><Async q={hm}>{d => <RiskMatrix grid={d.grid} onPick={setCell} />}</Async></div></section>
      <section className="panel"><header><h2>{T("المخاطر المفتوحة حسب المستوى", "Open risks by level")}</h2></header>
        <div className="body stack"><Async q={hm}>{d => <>
          <Segments parts={[["critical", "حرج", "Critical"], ["high", "عالٍ", "High"], ["moderate", "متوسط", "Moderate"], ["low", "منخفض", "Low"]].map(([k, a, e]) => ({ label: T(a, e), value: d.counts[k], color: lvl[k] }))} />
          <p className="small muted">{T(`الحدود الحالية: منخفض حتى ${d.thresholds.low}، متوسط حتى ${d.thresholds.moderate}، عالٍ حتى ${d.thresholds.high}، وما فوقها حرج. تُعدَّل من الإعدادات.`,
            `Current limits: low up to ${d.thresholds.low}, moderate up to ${d.thresholds.moderate}, high up to ${d.thresholds.high}, critical above. Change them in Settings.`)}</p>
          {d.unique < d.total_rows && <div className="note">{T(`${num(d.total_rows)} سجل خطر يمثل ${num(d.unique)} خطراً فعلياً: المخاطر المشتركة بين المشاريع احتُسبت مرة واحدة.`, `${num(d.total_rows)} risk records represent ${num(d.unique)} distinct risks: risks shared between projects are counted once.`)}</div>}
        </>}</Async></div></section>
    </div>
    <Register resource="risks" projectId={pid} perm="risk.write" noun={["خطراً", "Risk"]} title={T("سجل المخاطر", "Risk register")} onChanged={() => setN(n + 1)}
      sub={cell ? T(`تصفية: الاحتمالية ${cell.probability} × الأثر ${cell.impact}`, `Filtered: probability ${cell.probability} × impact ${cell.impact}`) : undefined}
      filter={r => (!cell || cell.risk_ids.includes(r.id)) && (pid ? true : true)} sort={(a, b) => (b.status === "closed" ? -1 : b.score) - (a.status === "closed" ? -1 : a.score)}
      cols={[{ key: "code", label: ["الرمز", "ID"] }, ...(pid ? [] : [{ key: "project_id", label: ["المشروع", "Project"] as [string, string], render: (r: any) => r.project_id ? <bdi>{pname(r.project_id)}</bdi> : <span className="tag">{r.scope_level === "portfolio" ? T("محفظة", "Portfolio") : T("برنامج", "Programme")}</span> }]),
        { key: "title", label: ["الخطر", "Risk"], render: r => <span>{r.title}{r.shared_key && <span className="tag" style={{ marginInlineStart: 6 }}>{T("مشترك", "Shared")}</span>}</span> },
        { key: "category", label: ["الفئة", "Category"] }, { key: "probability", label: ["ح", "P"], type: "num" }, { key: "impact", label: ["أ", "I"], type: "num" }, { key: "score", label: ["الدرجة", "Score"], type: "num" },
        { key: "level", label: ["التصنيف", "Level"], type: "status" }, { key: "residual_score", label: ["المتبقي", "Residual"], type: "num" }, { key: "owner_name", label: ["المالك", "Owner"] },
        { key: "response_deadline", label: ["موعد الاستجابة", "Response due"], type: "date" }, { key: "status", label: ["الحالة", "Status"], type: "status" }, { key: "source_tag", label: ["المصدر", "Source"], type: "src" }]}
      fields={fields} extraActions={r => <button className="btn ghost sm" onClick={() => setResp(r)}><ListChecks />{T("المعالجة", "Responses")} ({r.responses?.length || 0})</button>} />
    {resp && <Responses risk={resp} write={write} onClose={() => { setResp(null); setN(n + 1); }} />}
  </div>;
}
