import { useDeferredValue, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { FileUp, Plus } from "lucide-react";
import { api, useApp, useLoad } from "../lib/core";
import { Async, FieldSpec, FormModal, Progress, Register, Status } from "../lib/ui";
import { PairBars } from "../lib/charts";

export function projectFields(T: any, meta: any, N: any, lists: any): FieldSpec[] {
  const opt = (rows: any[]) => (rows || []).map(r => [r.id, N(r)]) as [any, string][];
  return [
    { key: "name_ar", label: ["اسم المشروع (عربي)", "Project name (Arabic)"], required: true }, { key: "name_en", label: ["اسم المشروع (إنجليزي)", "Project name (English)"] },
    { key: "portfolio_id", label: ["المحفظة", "Portfolio"], type: "select", options: opt(lists.portfolios) }, { key: "program_id", label: ["البرنامج", "Programme"], type: "select", options: opt(lists.programs) },
    { key: "department_id", label: ["الإدارة", "Department"], type: "select", options: opt(lists.departments) }, { key: "objective_id", label: ["الهدف الاستراتيجي", "Strategic objective"], type: "select", options: opt(lists.objectives) },
    { key: "manager_id", label: ["مدير المشروع", "Project manager"], type: "select", options: (meta?.users || []).map((u: any) => [u.id, N(u)]) }, { key: "sponsor", label: ["راعي المشروع", "Sponsor"] },
    { key: "business_owner", label: ["مالك الأعمال", "Business owner"] },
    { key: "status", label: ["الحالة", "Status"], type: "select", def: "planned", required: true, options: [["planned", T("مخطط", "Planned")], ["active", T("نشط", "Active")], ["on_hold", T("متوقف", "On hold")], ["completed", T("مكتمل", "Completed")], ["cancelled", T("ملغى", "Cancelled")]] },
    { key: "priority", label: ["الأولوية", "Priority"], type: "select", def: "medium", required: true, options: [["low", T("منخفضة", "Low")], ["medium", T("متوسطة", "Medium")], ["high", T("عالية", "High")], ["critical", T("قصوى", "Critical")]] },
    { key: "stage", label: ["مرحلة دورة الحياة", "Lifecycle stage"], type: "select", def: "initiation", options: (meta?.lifecycle || []).map((s: string) => [s, STAGE[s] ? T(...STAGE[s]) : s]) },
    { key: "start_date", label: ["تاريخ البداية", "Start date"], type: "date" }, { key: "end_date", label: ["تاريخ النهاية", "End date"], type: "date" }, { key: "budget", label: ["الميزانية المعتمدة", "Approved budget"], type: "number", def: 0 },
    { key: "needs_intervention", label: ["يتطلب تدخلاً تنفيذياً", "Needs executive intervention"], type: "bool" }, { key: "intervention_reason", label: ["سبب طلب التدخل", "Why intervention is needed"], wide: true, showIf: v => v.needs_intervention },
    { key: "description", label: ["وصف المشروع", "Description"], type: "textarea" }, { key: "business_case", label: ["مبررات المشروع", "Business case"], type: "textarea" }, { key: "scope", label: ["النطاق", "Scope"], type: "textarea" },
    { key: "out_of_scope", label: ["خارج النطاق", "Out of scope"], type: "textarea" }, { key: "success_criteria", label: ["معايير النجاح", "Success criteria"], type: "textarea" },
    { key: "assumptions", label: ["الافتراضات", "Assumptions"], type: "textarea" }, { key: "constraints", label: ["القيود", "Constraints"], type: "textarea" }, { key: "dependencies_text", label: ["الاعتماديات", "Dependencies"], type: "textarea" }];
}
export const STAGE: Record<string, [string, string]> = { idea: ["الفكرة والطلب", "Idea & demand"], initiation: ["التهيئة", "Initiation"], charter: ["الميثاق", "Charter"], business_case: ["دراسة الجدوى", "Business case"],
  planning: ["التخطيط", "Planning"], execution: ["التنفيذ", "Execution"], monitoring: ["المراقبة والتحكم", "Monitoring & control"], closure: ["الإغلاق", "Closure"], benefits: ["تحقيق المنافع", "Benefits realisation"], lessons: ["الدروس المستفادة", "Lessons learned"] };

export function useLists() {
  const { can } = useApp();
  const ok = can("portfolio.read");  // roles without portfolio visibility do not ask for these lists at all
  const a = useLoad<any[]>(ok ? "/r/portfolios" : null), b = useLoad<any[]>(ok ? "/r/programs" : null), c = useLoad<any[]>("/r/departments"), d = useLoad<any[]>(ok ? "/r/objectives" : null);
  return { portfolios: a.data || [], programs: b.data || [], departments: c.data || [], objectives: d.data || [] };
}

export function Projects() {
  const { T, N, can, money, date, meta, toast } = useApp();
  const q = useLoad<any[]>("/projects");
  const lists = useLists();
  const [sp, setSp] = useSearchParams();
  const nav = useNavigate();
  const [add, setAdd] = useState(false);
  const [text, setText] = useState("");
  const f = sp.get("f") || "all";
  const needle = useDeferredValue(text).trim().toLowerCase();
  const F: Record<string, [string, string, (p: any) => boolean]> = { all: ["الكل", "All", () => true], active: ["النشطة", "Active", p => p.status === "active"], planned: ["المخطط لها", "Planned", p => p.status === "planned"],
    delayed: ["المتأخرة", "Delayed", p => p.metrics.delayed], on_hold: ["المتوقفة", "On hold", p => p.status === "on_hold"], completed: ["المكتملة", "Completed", p => p.status === "completed"],
    high_risk: ["عالية المخاطر", "High risk", p => p.metrics.risk_counts.critical > 0 && p.status !== "completed"], over_budget: ["تجاوزت الميزانية", "Over budget", p => p.metrics.over_budget || (p.metrics.evm.CPI ?? 1) < 0.9],
    intervention: ["تتطلب تدخلاً", "Need intervention", p => p.needs_intervention], on_track: ["على المسار", "On track", p => p.status === "active" && p.metrics.health === "green"] };
  return <div className="page">
    <div className="page-head"><div><h1>{T("المشاريع", "Projects")}</h1><p>{T("كل مشروع له سجل مستقل ومركز قيادة. تظهر هنا المشاريع التي تتيحها صلاحياتك فقط.", "Each project has its own record and command centre. Only projects in your scope are listed.")}</p></div>
      <div className="row">{can("initiation.use") && <Link className="btn" to="/initiation"><FileUp />{T("أنشئ من ميثاق", "Create from a charter")}</Link>}
        {can("project.write") && <button className="btn primary" onClick={() => setAdd(true)}><Plus />{T("مشروع جديد", "New project")}</button>}</div></div>
    <div className="row" style={{ marginBlockEnd: 12 }}>
      {Object.entries(F).map(([k, [a, e]]) => <button key={k} className={`btn sm ${f === k ? "primary" : ""}`} onClick={() => setSp(k === "all" ? {} : { f: k })} aria-pressed={f === k}>{T(a, e)}{q.data && ` ${q.data.filter(F[k][2]).length}`}</button>)}
      <span className="grow" /><input className="input" style={{ width: 220 }} placeholder={T("ابحث بالاسم أو الرمز…", "Filter by name or code…")} value={text} onChange={e => setText(e.target.value)} aria-label={T("تصفية", "Filter")} /></div>
    <section className="panel"><Async q={q}>{rows => { const list = rows.filter((F[f] || F.all)[2]).filter((p: any) => !needle || `${p.name_ar} ${p.name_en} ${p.code}`.toLowerCase().includes(needle));
      return list.length === 0 ? <div className="empty">{T("لا مشاريع تطابق هذه التصفية.", "No projects match this filter.")}</div> : <div className="tbl-wrap"><table className="tbl"><thead><tr><th>{T("المشروع", "Project")}</th><th>{T("الحالة", "Status")}</th><th>{T("الوضع", "Health")}</th><th>{T("مدير المشروع", "Manager")}</th>
        <th style={{ width: 160 }}>{T("الإنجاز", "Progress")}</th><th className="num">SPI</th><th className="num">CPI</th><th className="num">{T("الميزانية", "Budget")}</th><th className="num">{T("المصروف", "Actual")}</th><th>{T("النهاية", "End")}</th><th className="num">{T("مخاطر حرجة", "Critical risks")}</th></tr></thead>
        <tbody>{list.map((p: any) => <tr key={p.id} className="click" onClick={() => nav(`/projects/${p.id}`)}><td><Link to={`/projects/${p.id}`} onClick={e => e.stopPropagation()} style={{ fontWeight: 600, color: "var(--ink)", textDecoration: "none" }}>{N(p)}</Link><div className="small muted"><bdi>{p.code}</bdi></div></td>
          <td><Status v={p.status} /></td><td><Status v={p.metrics.health} /></td><td>{N(p, "manager_name") || "—"}</td><td><Progress v={p.metrics.progress} planned={p.metrics.planned_progress} /></td>
          <td className="num">{p.metrics.evm.SPI ?? "—"}</td><td className="num">{p.metrics.evm.CPI ?? "—"}</td><td className="num">{money(p.budget)}</td><td className="num">{money(p.metrics.actual)}</td><td>{date(p.end_date)}</td><td className="num">{p.metrics.risk_counts.critical}</td></tr>)}</tbody></table></div>; }}</Async></section>
    {add && <FormModal title={T("مشروع جديد", "New project")} saveLabel={T("أنشئ المشروع", "Create project")} fields={projectFields(T, meta, N, lists).slice(0, 15)} initial={{}} onClose={() => setAdd(false)}
      onSave={async v => { const p = await api.post("/projects", v); toast(T("أُنشئ المشروع وبدأت دورة الاعتماد", "Project created and approval lifecycle started")); nav(`/projects/${p.id}`); }} />}
  </div>;
}

export function Portfolios({ kind }: { kind: "portfolios" | "programs" }) {
  const { T, N, money, meta, pct } = useApp();
  const lists = useLists();
  const dash = useLoad<any>("/dashboard");
  const isP = kind === "portfolios";
  const users = (meta?.users || []).map((u: any) => [u.id, N(u)]) as [any, string][];
  const agg = (id: number) => (dash.data?.[isP ? "by_portfolio" : "by_program"] || []).find((g: any) => g.id === id);
  const risks = useLoad<any[]>("/r/risks");
  const nRisk = (id: number) => (risks.data || []).filter(r => r[isP ? "portfolio_id" : "program_id"] === id && !r.project_id).length;
  const shared = Object.values((risks.data || []).filter(r => r.shared_key && r.project_id).reduce((m: any, r: any) => ((m[r.shared_key] ||= []).push(r), m), {})).filter((g: any) => g.length > 1) as any[][];
  return <div className="page">
    <div className="page-head"><div><h1>{isP ? T("إدارة المحافظ", "Portfolio management") : T("إدارة البرامج", "Programme management")}</h1>
      <p>{isP ? T("المحافظ تربط البرامج والمشاريع بالأهداف الاستراتيجية وتوزع عليها الميزانية.", "Portfolios tie programmes and projects to strategic objectives and allocate budget to them.") : T("البرنامج يجمع مشاريع مترابطة تحت مدير واحد وأهداف ومنافع مشتركة.", "A programme groups related projects under one manager with shared objectives and benefits.")}</p></div></div>
    <div className="stack">
      {dash.data && <section className="panel"><header><div><h2>{isP ? T("أداء المحافظ", "Portfolio performance") : T("أداء البرامج", "Programme performance")}</h2><p>{T("الإنجاز الفعلي مقابل المخطط، مرجحاً بميزانيات المشاريع", "Actual against planned progress, weighted by project budgets")}</p></div></header>
        <div className="body"><PairBars names={[T("الفعلي %", "Actual %"), T("المخطط %", "Planned %")]} fmt={v => pct(v, 1)} rows={(dash.data[isP ? "by_portfolio" : "by_program"] || []).map((g: any) => ({ label: `${N(g)} (${g.projects})`, a: g.progress, b: g.planned }))} /></div></section>}
      <Register resource={kind} perm="portfolio.write" noun={isP ? ["محفظة", "Portfolio"] : ["برنامجاً", "Programme"]} title={isP ? T("المحافظ", "Portfolios") : T("البرامج", "Programmes")}
        cols={[{ key: "code", label: ["الرمز", "Code"] }, { key: "name", label: ["الاسم", "Name"], render: r => <b>{N(r)}</b> },
          ...(isP ? [{ key: "objective_id", label: ["الهدف الاستراتيجي", "Strategic objective"] as [string, string], render: (r: any) => N(lists.objectives.find(o => o.id === r.objective_id)) || "—" }]
            : [{ key: "portfolio_id", label: ["المحفظة", "Portfolio"] as [string, string], render: (r: any) => N(lists.portfolios.find(o => o.id === r.portfolio_id)) || "—" }]),
          { key: isP ? "owner_id" : "manager_id", label: isP ? ["المالك", "Owner"] : ["مدير البرنامج", "Programme manager"], render: r => users.find(u => u[0] === r[isP ? "owner_id" : "manager_id"])?.[1] || "—" },
          { key: "budget", label: ["الميزانية المخصصة", "Allocated budget"], type: "money" }, { key: "p", label: ["المشاريع", "Projects"], render: r => agg(r.id)?.projects ?? 0 },
          { key: "used", label: ["ميزانيات المشاريع", "Project budgets"], render: r => money(agg(r.id)?.budget ?? 0) }, { key: "spent", label: ["المصروف", "Actual"], render: r => money(agg(r.id)?.actual ?? 0) },
          { key: "prog", label: ["الإنجاز", "Progress"], render: r => <Progress v={agg(r.id)?.progress ?? 0} planned={agg(r.id)?.planned} /> }, { key: "rk", label: ["مخاطر المستوى", "Level risks"], render: r => nRisk(r.id) }]}
        fields={[{ key: "code", label: ["الرمز", "Code"], required: true }, { key: "name_ar", label: ["الاسم (عربي)", "Name (Arabic)"], required: true }, { key: "name_en", label: ["الاسم (إنجليزي)", "Name (English)"] },
          ...(isP ? [{ key: "objective_id", label: ["الهدف الاستراتيجي", "Strategic objective"] as [string, string], type: "select" as const, options: lists.objectives.map(o => [o.id, N(o)]) as [any, string][] }, { key: "owner_id", label: ["مالك المحفظة", "Portfolio owner"] as [string, string], type: "select" as const, options: users }]
            : [{ key: "portfolio_id", label: ["المحفظة", "Portfolio"] as [string, string], type: "select" as const, options: lists.portfolios.map(o => [o.id, N(o)]) as [any, string][] }, { key: "manager_id", label: ["مدير البرنامج", "Programme manager"] as [string, string], type: "select" as const, options: users }]),
          { key: "budget", label: ["الميزانية المخصصة", "Allocated budget"], type: "number" }, { key: "objectives", label: ["الأهداف", "Objectives"], type: "textarea" },
          ...(isP ? [] : [{ key: "outputs", label: ["المخرجات", "Outputs"] as [string, string], type: "textarea" as const }]), { key: "description", label: ["الوصف", "Description"], type: "textarea" }]} />
      {shared.length > 0 && <section className="panel"><header><div><h2>{T("المخاطر المشتركة والاعتماديات بين المشاريع", "Shared risks and cross-project dependencies")}</h2><p>{T("خطر واحد يمس أكثر من مشروع. يُحتسب مرة واحدة في المؤشرات المجمعة.", "One risk touching several projects. Counted once in aggregated indicators.")}</p></div></header>
        <div className="tbl-wrap"><table className="tbl"><thead><tr><th>{T("الخطر", "Risk")}</th><th>{T("المشاريع المتأثرة", "Projects affected")}</th><th className="num">{T("أعلى درجة", "Highest score")}</th></tr></thead>
          <tbody>{shared.map((g, i) => <tr key={i}><td>{g[0].title}</td><td>{g.map(r => <Link key={r.id} className="tag" to={`/projects/${r.project_id}/risks`} style={{ marginInlineEnd: 4 }}>{dash.data?.projects.find((p: any) => p.id === r.project_id)?.code || r.project_id}</Link>)}</td><td className="num">{Math.max(...g.map(r => r.score))}</td></tr>)}</tbody></table></div></section>}
    </div></div>;
}

export function Strategy() {
  const { T, N, money, pct } = useApp();
  const q = useLoad<any>("/strategy");
  return <div className="page">
    <div className="page-head"><div><h1>{T("المواءمة الاستراتيجية", "Strategic alignment")}</h1><p>{T("أي المشاريع يخدم أي هدف، وكم أُنجز منها، وكم تحقق من منافعها المقيسة.", "Which projects serve which objective, how far they have progressed, and how much measured benefit has been realised.")}</p></div></div>
    <div className="stack">
      <Async q={q}>{d => <>{d.objectives.map((o: any) => <section className="panel" key={o.id}><header><div><h2><bdi className="muted">{o.code}</bdi> {N(o)}</h2><p>{T("المستهدف", "Target")}: {o.target}</p></div>
        <div className="row gap-lg small"><span>{T("المشاريع", "Projects")} <b>{o.projects.length}</b></span><span>{T("الميزانية", "Budget")} <b>{money(o.budget)}</b></span><span>{T("الإنجاز", "Progress")} <b>{pct(o.progress, 1)}</b></span>
          <span>{T("تحقق المنافع", "Benefits realised")} <b>{o.benefit_realization == null ? T("لم يُقَس بعد", "Not measured yet") : pct(o.benefit_realization, 1)}</b> <span className="muted">({o.benefits_measured}/{o.benefits})</span></span></div></header>
        {o.projects.length ? <div className="tbl-wrap"><table className="tbl"><tbody>{o.projects.map((p: any) => <tr key={p.id}><td><Link to={`/projects/${p.id}`}>{N(p)}</Link> <bdi className="muted small">{p.code}</bdi></td><td><Status v={p.status} /></td><td><Status v={p.health} /></td>
          <td style={{ width: 200 }}><Progress v={p.progress} /></td><td className="num">{money(p.budget)}</td></tr>)}</tbody></table></div> : <div className="body muted">{T("لا مشروع مرتبط بهذا الهدف.", "No project is linked to this objective.")}</div>}</section>)}
        {d.unaligned.length > 0 && <div className="note warning">{T("مشاريع بلا هدف استراتيجي: ", "Projects with no strategic objective: ")}{d.unaligned.map((p: any) => <Link key={p.id} to={`/projects/${p.id}`} style={{ marginInlineEnd: 8 }}>{N(p)}</Link>)}</div>}</>}</Async>
      <Register resource="objectives" perm="portfolio.write" noun={["هدفاً استراتيجياً", "Strategic objective"]} title={T("الأهداف الاستراتيجية", "Strategic objectives")} onChanged={q.reload}
        cols={[{ key: "code", label: ["الرمز", "Code"] }, { key: "name", label: ["الهدف", "Objective"], render: r => N(r) }, { key: "target", label: ["المستهدف", "Target"] }]}
        fields={[{ key: "code", label: ["الرمز", "Code"], required: true }, { key: "name_ar", label: ["الهدف (عربي)", "Objective (Arabic)"], required: true }, { key: "name_en", label: ["الهدف (إنجليزي)", "Objective (English)"] }, { key: "target", label: ["المستهدف", "Target"] }, { key: "description", label: ["الوصف", "Description"], type: "textarea" }]} />
    </div></div>;
}
