import { useState } from "react";
import { api, useApp, useLoad } from "../lib/core";
import { Async, Register } from "../lib/ui";
import { HBars, useTip } from "../lib/charts";

export function Resources({ pid }: { pid?: number }) {
  const { T, num, N } = useApp();
  const [n, setN] = useState(0);
  const q = useLoad<any[]>(`/resources/utilization${pid ? `?project_id=${pid}` : ""}`, [n]);
  const res = useLoad<any[]>("/r/resources", [n]);
  const sch = useLoad<any>(pid ? `/projects/${pid}/schedule` : null);
  const projects = useLoad<any[]>(pid ? null : "/projects");
  const bump = () => setN(n + 1);
  return <div className="stack">
    <Async q={q}>{rows => {
      const over = rows.filter((r: any) => r.conflict), free = rows.filter((r: any) => r.free >= 40);
      return <div className="grid g2">
        <section className="panel"><header><div><h2>{T("استغلال الموارد اليوم", "Resource utilisation today")}</h2><p>{T("مجموع نسب التخصيص النشطة لكل مورد عبر جميع المشاريع", "Sum of each resource's active allocations across all projects")}</p></div></header>
          <div className="body">{rows.length ? <HBars max={Math.max(120, ...rows.map((r: any) => r.load))} fmt={v => `${num(v)}%`}
            rows={rows.map((r: any) => ({ label: r.name, value: r.load, color: r.conflict ? "var(--s-critical)" : "var(--c1)", note: `${r.title || ""} · ${T("الطاقة", "Capacity")} ${r.capacity_pct}% · ${r.projects} ${T("مشروع", "project(s)")}` }))} />
            : <p className="muted">{T("لا موارد مخصصة.", "No resources assigned.")}</p>}</div></section>
        <section className="panel"><header><h2>{T("التعارضات والفجوات", "Conflicts and gaps")}</h2></header><div className="body stack">
          {over.length === 0 && <div className="note">{T("لا يوجد مورد محمّل فوق طاقته.", "No resource is loaded beyond capacity.")}</div>}
          {over.map((r: any) => <div key={r.id} className="note critical"><div><b>{r.name}</b> — {T(`محمّل ${num(r.load)}% مقابل طاقة ${r.capacity_pct}%`, `loaded ${num(r.load)}% against ${r.capacity_pct}% capacity`)}
            <div className="small">{r.assignments.map((a: any) => `${a.project_code} ${num(a.allocation_pct)}%`).join(T(" ، ", ", "))}</div></div></div>)}
          <div><h4>{T("طاقة متاحة (40% فأكثر)", "Available capacity (40% or more)")}</h4>
            <p className="small">{free.length ? free.map((r: any) => `${r.name} (${num(r.free)}%)`).join(T(" ، ", ", ")) : T("لا يوجد.", "None.")}</p></div>
        </div></section></div>;
    }}</Async>
    <Register resource="assignments" projectId={pid} perm="resource.write" noun={["تخصيصاً", "Assignment"]} title={T("توزيع الموارد", "Resource assignments")} onChanged={bump}
      cols={[{ key: "resource_id", label: ["المورد", "Resource"], render: r => (res.data || []).find(x => x.id === r.resource_id)?.name || r.resource_id },
        ...(pid ? [] : [{ key: "project_id", label: ["المشروع", "Project"] as [string, string], render: (r: any) => N((projects.data || []).find(p => p.id === r.project_id)) || r.project_id }]),
        { key: "role", label: ["الدور", "Role"] }, { key: "allocation_pct", label: ["التخصيص %", "Allocation %"], type: "num" }, { key: "start_date", label: ["من", "From"], type: "date" }, { key: "end_date", label: ["إلى", "To"], type: "date" }]}
      fields={[{ key: "resource_id", label: ["المورد", "Resource"], type: "select", required: true, options: () => (res.data || []).map(r => [r.id, r.name]) },
        ...(pid ? [] : [{ key: "project_id", label: ["المشروع", "Project"] as [string, string], type: "select" as const, required: true, options: () => (projects.data || []).map(p => [p.id, N(p)]) as [any, string][] }]),
        { key: "role", label: ["الدور في المشروع", "Role on the project"] }, { key: "allocation_pct", label: ["نسبة التخصيص %", "Allocation %"], type: "number", def: 50, required: true },
        { key: "activity_id", label: ["النشاط", "Activity"], type: "select", options: () => (sch.data?.activities || []).filter((a: any) => !a.is_summary).map((a: any) => [a.id, a.name]) },
        { key: "start_date", label: ["من", "From"], type: "date" }, { key: "end_date", label: ["إلى", "To"], type: "date" }]} />
    {!pid && <Register resource="resources" perm="resource.write" noun={["مورداً", "Resource"]} title={T("سجل الموارد والفرق", "Resources and teams")} onChanged={bump}
      cols={[{ key: "name", label: ["الاسم", "Name"] }, { key: "title", label: ["المسمى", "Title"] }, { key: "team", label: ["الفريق", "Team"] }, { key: "skills", label: ["المهارات", "Skills"] }, { key: "capacity_pct", label: ["الطاقة %", "Capacity %"], type: "num" }, { key: "cost_rate", label: ["التكلفة اليومية", "Daily rate"], type: "num" }]}
      fields={[{ key: "name", label: ["الاسم", "Name"], required: true }, { key: "title", label: ["المسمى الوظيفي", "Job title"] }, { key: "team", label: ["الفريق", "Team"] }, { key: "skills", label: ["المهارات", "Skills"] },
        { key: "capacity_pct", label: ["الطاقة الاستيعابية %", "Capacity %"], type: "number", def: 100 }, { key: "cost_rate", label: ["التكلفة اليومية", "Daily rate"], type: "number" }]} />}
  </div>;
}

export function Stakeholders({ pid }: { pid: number }) {
  const { T } = useApp();
  const [n, setN] = useState(0);
  const q = useLoad<any[]>(`/r/stakeholders?project_id=${pid}`, [n]);
  const tip = useTip();
  const quad: [string, string, string][] = [["أبقِه راضياً", "Keep satisfied", "قوة عالية، اهتمام منخفض"], ["أدِره عن قرب", "Manage closely", "قوة عالية، اهتمام عالٍ"], ["راقبه", "Monitor", "قوة منخفضة، اهتمام منخفض"], ["أبقِه مطلعاً", "Keep informed", "قوة منخفضة، اهتمام عالٍ"]];
  const eng = [["supportive", T("داعم", "Supportive")], ["neutral", T("محايد", "Neutral")], ["resistant", T("معارض", "Resistant")]] as [string, string][];
  return <div className="stack">
    <div className="grid split">
      <Register resource="stakeholders" projectId={pid} perm="project.write" noun={["صاحب مصلحة", "Stakeholder"]} title={T("سجل أصحاب المصلحة", "Stakeholder register")} onChanged={() => setN(n + 1)}
        cols={[{ key: "name", label: ["الاسم", "Name"] }, { key: "role", label: ["الدور", "Role"] }, { key: "power", label: ["التأثير", "Power"], type: "num" }, { key: "interest", label: ["الاهتمام", "Interest"], type: "num" },
          { key: "engagement", label: ["الموقف", "Engagement"], type: "status" }, { key: "communication", label: ["خطة التواصل", "Communication"] }, { key: "last_interaction", label: ["آخر تفاعل", "Last contact"], type: "date" }]}
        fields={[{ key: "name", label: ["الاسم", "Name"], required: true }, { key: "organization", label: ["الجهة", "Organisation"] }, { key: "role", label: ["الدور", "Role"] }, { key: "contact", label: ["وسيلة التواصل", "Contact"] },
          { key: "power", label: ["التأثير (1–5)", "Power (1–5)"], type: "scale", def: 3 }, { key: "interest", label: ["الاهتمام (1–5)", "Interest (1–5)"], type: "scale", def: 3 },
          { key: "engagement", label: ["الموقف", "Engagement"], type: "select", def: "neutral", options: eng }, { key: "last_interaction", label: ["آخر تفاعل", "Last contact"], type: "date" }, { key: "communication", label: ["خطة التواصل", "Communication plan"], wide: true }]} />
      <section className="panel"><header><div><h2>{T("مصفوفة التأثير والاهتمام", "Power / interest grid")}</h2></div></header><div className="body">
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 3, position: "relative" }}>
          {quad.map(([a, e], i) => <div key={i} style={{ background: "var(--raised)", border: "1px solid var(--line-2)", minHeight: 120, padding: 8, borderRadius: 4 }}>
            <div className="small muted">{T(a, e)}</div><div className="row" style={{ marginBlockStart: 6, gap: 5 }}>
              {(q.data || []).filter(s => (s.power >= 3 ? 0 : 2) + (s.interest >= 3 ? 1 : 0) === i).map(s => <span key={s.id} className={`tag ${s.engagement === "resistant" ? "critical" : s.engagement === "supportive" ? "good" : ""}`}
                onMouseMove={ev => tip.show(ev, <>{s.name}<br />{T("التأثير", "Power")} {s.power} · {T("الاهتمام", "Interest")} {s.interest}</>)} onMouseLeave={tip.hide}>{s.name}</span>)}</div></div>)}
        </div><p className="small muted" style={{ marginBlockStart: 8 }}>{T("الصف العلوي: تأثير عالٍ. العمود الثاني: اهتمام عالٍ.", "Top row: high power. Second column: high interest.")}</p>{tip.node}</div></section>
    </div>
    <Raci pid={pid} key={n} />
  </div>;
}

function Raci({ pid }: { pid: number }) {
  const { T, can, fail } = useApp();
  const q = useLoad<any>(`/projects/${pid}/raci`);
  const [party, setParty] = useState("");
  const [extra, setExtra] = useState<string[]>([]);
  const write = can("project.write");
  const set = (activity_id: number, p: string, raci: string) => api.put(`/projects/${pid}/raci`, { activity_id, party: p, raci }).then(() => q.reload()).catch(fail);
  return <section className="panel"><header><div><h2>{T("مصفوفة RACI", "RACI matrix")}</h2><p>R = {T("منفذ", "Responsible")} · A = {T("مساءل", "Accountable")} · C = {T("مستشار", "Consulted")} · I = {T("مطّلع", "Informed")}</p></div>
    {write && <div className="row"><input className="input" style={{ width: 200 }} placeholder={T("طرف جديد (دور أو جهة)", "New party (role or body)")} value={party} onChange={e => setParty(e.target.value)} />
      <button className="btn sm" disabled={!party.trim()} onClick={() => { setExtra([...extra, party.trim()]); setParty(""); }}>{T("أضف عموداً", "Add column")}</button></div>}</header>
    <Async q={q}>{d => {
      const parties = [...d.parties, ...extra.filter(p => !d.parties.includes(p))];
      if (!d.activities.length) return <div className="empty">{T("أضف أنشطة أولاً.", "Add activities first.")}</div>;
      if (!parties.length) return <div className="empty">{T("أضف أصحاب مصلحة أو عموداً لبدء المصفوفة.", "Add stakeholders or a column to start the matrix.")}</div>;
      return <><div className="tbl-wrap" style={{ maxHeight: 460 }}><table className="tbl"><thead><tr><th>{T("النشاط", "Activity")}</th>{parties.map((p: string) => <th key={p}>{p}</th>)}</tr></thead>
        <tbody>{d.activities.map((a: any) => <tr key={a.id}><td>{a.name} {d.needs_one_accountable.includes(a.id) && <span className="tag warning" title={T("يجب أن يكون للنشاط مساءل واحد", "Each activity needs exactly one Accountable")}>A≠1</span>}</td>
          {parties.map((p: string) => <td key={p}><select className="input inline" style={{ width: 62 }} disabled={!write} value={d.cells[`${a.id}|${p}`] || ""} onChange={e => set(a.id, p, e.target.value)} aria-label={`${a.name} — ${p}`}>
            <option value="">·</option><option>R</option><option>A</option><option>C</option><option>I</option></select></td>)}</tr>)}</tbody></table></div>
        {d.needs_one_accountable.length > 0 && <div className="body small muted">{T(`${d.needs_one_accountable.length} نشاط ليس له مساءل (A) واحد بالضبط.`, `${d.needs_one_accountable.length} activities do not have exactly one Accountable (A).`)}</div>}</>;
    }}</Async></section>;
}
