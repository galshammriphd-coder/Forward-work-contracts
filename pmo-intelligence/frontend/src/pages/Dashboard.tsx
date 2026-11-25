import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AlertOctagon, AlertTriangle, BellRing, Check, Info, RefreshCw } from "lucide-react";
import { api, useApp, useLoad } from "../lib/core";
import { Async, Status } from "../lib/ui";
import { Gauge, HBars, Lines, PairBars, Ring, RiskMatrix, Segments, VBars } from "../lib/charts";

export const CAT: Record<string, [string, string]> = { schedule: ["الجدول", "Schedule"], financial: ["المالية", "Financial"], risk: ["المخاطر", "Risk"], performance: ["الأداء", "Performance"], governance: ["الحوكمة", "Governance"] };
const SEV_ICON: Record<string, any> = { critical: AlertOctagon, warning: AlertTriangle, advisory: BellRing, informational: Info };
const ALERT_TAB: Record<string, string> = { activity: "gantt", milestone: "gantt", risk: "risks", kpi: "value", approval: "governance", issue: "governance", decision: "governance", resource: "resources" };

export function AlertList({ alerts, onChange, showProject = true }: { alerts: any[]; onChange: () => void; showProject?: boolean }) {
  const { T, N, fail, date } = useApp();
  if (!alerts.length) return <div className="empty"><Check size={22} />{T("لا تنبيهات مفتوحة.", "No open alerts.")}</div>;
  return <div>{alerts.map(a => { const I = SEV_ICON[a.severity] || Info; const tab = ALERT_TAB[a.entity_type] || (a.category === "financial" ? "finance" : a.category === "schedule" ? "gantt" : "overview");
    return <div key={a.id} style={{ padding: "10px 16px", borderBlockEnd: "1px solid var(--line-2)", display: "grid", gap: 3, opacity: a.status === "acknowledged" ? .65 : 1 }}>
      <div className="row" style={{ gap: 6 }}><span className={`tag ${a.severity === "critical" ? "critical" : a.severity === "warning" ? "warning" : "info"}`}><I />{T(...(CAT[a.category] || ["", ""]))}</span>
        {showProject && <Link to={`/projects/${a.project_id}/${tab}`} className="small strong">{N(a, "project_name")}</Link>}<span className="grow" /><span className="small muted">{date(a.created_at)}</span></div>
      <Link to={`/projects/${a.project_id}/${tab}`} style={{ color: "var(--ink)", textDecoration: "none", fontWeight: 500 }}>{N(a, "title")}</Link>
      <p className="small muted">{N(a, "recommendation")}</p>
      {a.status === "open" && <div><button className="btn ghost sm" onClick={() => api.patch(`/alerts/${a.id}`, { status: "acknowledged" }).then(onChange).catch(fail)}><Check />{T("تم الاطلاع", "Acknowledge")}</button>{a.escalated && <span className="tag critical">{T("صُعِّد", "Escalated")}</span>}</div>}
    </div>; })}</div>;
}

export default function Dashboard() {
  const { T, N, num, money, pct, date, fail, toast } = useApp();
  const q = useLoad<any>("/dashboard");
  const nav = useNavigate();
  const [cat, setCat] = useState("");
  const [busy, setBusy] = useState(false);
  const go = (f: string) => nav(`/projects?f=${f}`);
  const run = async () => { setBusy(true); try { const r = await api.post("/alerts/run"); toast(T(`فُحصت كل المشاريع: ${r.created} تنبيه جديد، ${r.resolved} عولج`, `All projects checked: ${r.created} new alerts, ${r.resolved} resolved`)); q.reload(); } catch (e) { fail(e); } finally { setBusy(false); } };
  const SC: Record<string, string> = { active: "var(--c1)", planned: "var(--c3)", on_hold: "var(--c4)", completed: "var(--ink-3)", cancelled: "var(--line)" };
  const ST: Record<string, [string, string]> = { active: ["نشط", "Active"], planned: ["مخطط", "Planned"], on_hold: ["متوقف", "On hold"], completed: ["مكتمل", "Completed"], cancelled: ["ملغى", "Cancelled"] };
  const PR: Record<string, [string, string, string]> = { critical: ["قصوى", "Critical", "var(--seq-4)"], high: ["عالية", "High", "var(--seq-3)"], medium: ["متوسطة", "Medium", "var(--seq-2)"], low: ["منخفضة", "Low", "var(--seq-1)"] };
  const LV: [string, string, string, string][] = [["critical", "حرج", "Critical", "var(--s-critical)"], ["high", "عالٍ", "High", "var(--s-serious)"], ["moderate", "متوسط", "Moderate", "var(--s-warning)"], ["low", "منخفض", "Low", "var(--s-good)"]];
  return <div className="page">
    <div className="page-head"><div><h1>{T("لوحة القيادة التنفيذية", "Executive dashboard")}</h1>
      <p>{q.data ? T(`وضع المحافظ والبرامج والمشاريع ضمن صلاحياتك حتى ${date(q.data.as_of)}. اضغط أي رقم لعرض تفاصيله.`, `Portfolios, programmes and projects in your scope as of ${date(q.data.as_of)}. Select any figure for its detail.`) : " "}</p></div>
      <button className="btn" onClick={run} disabled={busy}><RefreshCw />{T("افحص الإنذارات الآن", "Check alerts now")}</button></div>
    <Async q={q}>{d => { const k = d.kpis, P = d.projects, alerts = d.alerts.filter((a: any) => !cat || a.category === cat);
      const tile = (label: string, value: any, f: string, sub?: string, cls = "") => <button className="kpi" onClick={() => go(f)}><span>{label}</span><b className={cls}>{value}</b>{sub && <small>{sub}</small>}</button>;
      const live = P.filter((p: any) => p.status !== "completed" && p.status !== "planned");
      return <div className="grid split" style={{ alignItems: "start" }}>
        <div className="stack">
          <div className="cards">
            <button className="card c-blue" onClick={() => go("active")}><span>{T("المشاريع النشطة", "Active projects")}</span><b>{num(k.active)}</b><small>{T("من", "of")} {num(k.total)} {T("مشروعاً", "projects")}</small></button>
            <button className="card c-teal" onClick={() => go("on_track")}><span>{T("تحقق مستهدفاتها", "Meeting their targets")}</span><b>{pct(k.on_target_pct)}</b><small>{T("من المشاريع النشطة", "of active projects")}</small></button>
            <button className="card c-orange" onClick={() => go("delayed")}><span>{T("المشاريع المتأخرة", "Delayed projects")}</span><b>{num(k.delayed)}</b><small>{T("أنشطة فائتة أو SPI دون 0.9", "Late activities or SPI below 0.9")}</small></button>
            <button className="card c-red" onClick={() => go("high_risk")}><span>{T("عالية المخاطر", "High-risk projects")}</span><b>{num(k.high_risk)}</b><small>{num(k.needs_intervention)} {T("تتطلب تدخلاً إدارياً", "need management action")}</small></button>
          </div>

          <div className="grid g4w">
            <section className="panel"><header><h2>{T("نسبة الإنجاز الكلية", "Overall progress")}</h2></header><div className="body"><Gauge value={k.progress} fmt={v => num(v)} color="var(--c-actual)" sub={T("مرجحة بالميزانية، %", "Weighted by budget, %")} /></div></section>
            <section className="panel"><header><h2>{T("الميزانية المصروفة", "Budget used")}</h2></header><div className="body"><Gauge value={k.actual} max={k.budget || 1} ends fmt={v => money(v).replace(/ [^ ]+$/, "")} color="var(--c-lime)" marker={k.actual + k.committed} sub={T(`المصروف من ${money(k.budget)}؛ الخط = مع الالتزامات`, `Spent of ${money(k.budget)}; line = with commitments`)} /></div></section>
            <section className="panel"><header><h2>{T("الالتزام بالجدول", "Schedule adherence")}</h2></header><div className="body"><Gauge value={k.schedule_adherence} color="var(--c1)" sub={T("مشاريع نشطة بـ SPI ≥ 0.9، %", "Active projects with SPI ≥ 0.9, %")} /></div></section>
            <section className="panel"><header><h2>{T("أداء المحفظة", "Portfolio score")}</h2></header><div className="body"><Gauge value={k.portfolio_score} color="var(--c-violet)" sub={T("40% مستهدفات، 30% جدول، 30% تكلفة", "40% targets, 30% schedule, 30% cost")} /></div></section>
          </div>

          <div className="grid g2">
            <section className="panel"><header><h2>{T("حالة المشاريع", "Project status")}</h2></header><div className="body rings">
              {([["on_track", "على المسار", "On track", "var(--c-actual)", (p: any) => p.status === "active" && p.health === "green"], ["all", "تحتاج متابعة", "At risk", "var(--c4)", (p: any) => p.status === "active" && p.health === "amber"],
                ["delayed", "متعثرة", "Behind", "var(--s-critical)", (p: any) => p.status !== "completed" && p.health === "red"], ["completed", "مكتملة", "Complete", "var(--c1)", (p: any) => p.status === "completed"],
                ["planned", "مخطط لها", "Planned", "var(--ink-3)", (p: any) => p.status === "planned"]] as any[]).map(([f, a, e, c, fn]) => { const n = P.filter(fn).length;
                return <Ring key={e} label={T(a, e)} color={c} count={n} pct={P.length ? Math.round((n / P.length) * 100) : 0} onPick={() => go(f)} />; })}</div></section>
            <section className="panel"><header><h2>{T("الميزانية مقابل الفعلي حسب المحفظة", "Budget against actual by portfolio")}</h2></header><div className="body">
              <VBars names={[T("الميزانية", "Budget"), T("الفعلي", "Actual")]} fmt={v => money(v).replace(/ [^ ]+$/, "")} rows={d.by_portfolio.map((g: any) => ({ label: N(g), a: g.budget, b: g.actual }))} /></div></section>
          </div>

          <div className="kpis">
            {tile(T("إجمالي المشاريع", "Total projects"), num(k.total), "all")}
            {tile(T("المخطط لها", "Planned"), num(k.planned), "planned")}
            {tile(T("المكتملة", "Completed"), num(k.completed), "completed")}
            {tile(T("المتوقفة", "On hold"), num(k.on_hold), "on_hold", undefined, k.on_hold ? "warning" : "")}
            {tile(T("الميزانية المعتمدة", "Approved budget"), money(k.budget), "all")}
            {tile(T("المصروفات الفعلية", "Actual spend"), money(k.actual), "all", `${pct(k.budget ? (k.actual / k.budget) * 100 : 0)} ${T("من الميزانية", "of budget")}`)}
            {tile(T("الالتزامات المالية", "Commitments"), money(k.committed), "all")}
            {tile(T("الالتزام بالميزانية", "Budget adherence"), pct(k.budget_adherence), "over_budget", T("مشاريع نشطة بـ CPI ≥ 0.9", "Active projects with CPI ≥ 0.9"))}
          </div>

          <section className="panel"><header><div><h2>{T("خريطة الأداء المؤسسي", "Performance heatmap")}</h2><p>{T("كل مشروع جارٍ في أربعة أبعاد. اضغط الصف لفتح مركز قيادة المشروع.", "Each running project on four dimensions. Select a row to open its command centre.")}</p></div></header>
            <div className="tbl-wrap"><table className="tbl"><thead><tr><th>{T("المشروع", "Project")}</th><th>{T("الوضع العام", "Overall")}</th><th style={{ width: 150 }}>{T("الإنجاز (الخط = المخطط)", "Progress (line = planned)")}</th><th>{T("الجدول SPI", "Schedule SPI")}</th><th>{T("التكلفة CPI", "Cost CPI")}</th><th>{T("مخاطر حرجة", "Critical risks")}</th><th>{T("انحراف الانتهاء", "Finish variance")}</th></tr></thead>
              <tbody>{live.map((p: any) => { const c = (v: number | null) => v == null ? "" : v < 0.8 ? "critical" : v < 0.9 ? "warning" : "good";
                return <tr key={p.id} className="click" onClick={() => nav(`/projects/${p.id}`)}><td><b>{N(p)}</b><div className="small muted"><bdi>{p.code}</bdi> · {N(p, "manager_name")}</div></td>
                  <td><Status v={p.health} />{p.needs_intervention && <div className="tag critical" style={{ marginBlockStart: 3 }}>{T("يحتاج قراراً", "Needs a decision")}</div>}</td>
                  <td><div className="bar" style={{ position: "relative", overflow: "visible" }}><i style={{ width: `${p.progress}%` }} /><span style={{ position: "absolute", top: -3, insetInlineStart: `${p.planned_progress}%`, width: 2, height: 12, background: "var(--ink)" }} /></div><span className="small num">{pct(p.progress)} / {pct(p.planned_progress)}</span></td>
                  <td><span className={`tag ${c(p.spi)}`}>{num(p.spi, 2)}</span></td><td><span className={`tag ${p.over_budget ? "critical" : c(p.cpi)}`}>{num(p.cpi, 2)}{p.over_budget && ` · ${T("تجاوز", "over")}`}</span></td>
                  <td><span className={`tag ${p.critical_risks ? "critical" : "good"}`}>{num(p.critical_risks)}</span></td><td className="num">{p.schedule_variance_days > 0 ? `+${num(p.schedule_variance_days)} ${T("يوم", "d")}` : "—"}</td></tr>; })}</tbody></table></div></section>

          <div className="grid g2">
            <section className="panel"><header><h2>{T("المشاريع حسب الحالة", "Projects by status")}</h2></header><div className="body"><Segments onPick={p => go(p.key)} parts={Object.entries(d.by_status).map(([s, v]: any) => ({ key: s, label: T(...(ST[s] || [s, s])), value: v, color: SC[s] || "var(--c1)" }))} /></div></section>
            <section className="panel"><header><h2>{T("المشاريع حسب الأولوية", "Projects by priority")}</h2></header><div className="body"><Segments parts={["critical", "high", "medium", "low"].filter(s => d.by_priority[s]).map(s => ({ label: T(PR[s][0], PR[s][1]), value: d.by_priority[s], color: PR[s][2] }))} /></div></section>
            <section className="panel"><header><h2>{T("المشاريع حسب الإدارة", "Projects by department")}</h2></header><div className="body"><HBars rows={d.by_department.map((g: any) => ({ label: N(g), value: g.projects, note: `${T("الميزانية", "Budget")}: ${money(g.budget)}` }))} /></div></section>
            <section className="panel"><header><div><h2>{T("المخاطر المفتوحة حسب المستوى", "Open risks by level")}</h2></div><Link className="btn sm" to="/risks">{T("افتح سجل المخاطر", "Open risk register")}</Link></header><div className="body"><Segments parts={LV.map(([key, a, e, c]) => ({ label: T(a, e), value: d.by_risk[key], color: c }))} /></div></section>
            <section className="panel"><header><div><h2>{T("الأداء الزمني", "Schedule performance")}</h2><p>{T("الإنجاز الفعلي مقابل المخطط لكل مشروع جارٍ", "Actual against planned progress for each running project")}</p></div></header>
              <div className="body"><PairBars names={[T("الفعلي %", "Actual %")!, T("المخطط %", "Planned %")!]} fmt={v => pct(v)} onPick={r => nav(`/projects/${r.key}/gantt`)} rows={live.map((p: any) => ({ key: p.id, label: N(p), a: p.progress, b: p.planned_progress }))} /></div></section>
            <section className="panel"><header><h2>{T("الميزانية مقابل الفعلي حسب الإدارة", "Budget against actual by department")}</h2></header>
              <div className="body"><VBars names={[T("الميزانية", "Budget"), T("الفعلي", "Actual")]} fmt={v => money(v).replace(/ [^ ]+$/, "")} rows={d.by_department.map((g: any) => ({ label: N(g), a: g.budget, b: g.actual }))} /></div></section>
            <section className="panel"><header><h2>{T("الإنجاز حسب البرنامج", "Progress by programme")}</h2></header><div className="body"><PairBars names={[T("الفعلي %", "Actual %"), T("المخطط %", "Planned %")]} fmt={v => pct(v, 1)} rows={d.by_program.map((g: any) => ({ label: N(g), a: g.progress, b: g.planned }))} /></div></section>
            <section className="panel"><header><h2>{T("الإنجاز حسب المحفظة", "Progress by portfolio")}</h2></header><div className="body"><PairBars names={[T("الفعلي %", "Actual %"), T("المخطط %", "Planned %")]} fmt={v => pct(v, 1)} rows={d.by_portfolio.map((g: any) => ({ label: N(g), a: g.progress, b: g.planned }))} /></div></section>
            <section className="panel"><header><div><h2>{T("اتجاه المخاطر عبر الزمن", "Risk trend")}</h2><p>{T("عدد المخاطر المفتوحة الحرجة والعالية أسبوعياً", "Open critical and high risks, week by week")}</p></div></header>
              <div className="body"><Lines x={d.risk_trend.map((r: any) => r.date)} series={[{ name: T("حرج", "Critical"), color: "var(--s-critical)", values: d.risk_trend.map((r: any) => r.critical) }, { name: T("عالٍ", "High"), color: "var(--s-serious)", values: d.risk_trend.map((r: any) => r.high) }]} /></div></section>
            <section className="panel"><header><h2>{T("مصفوفة مخاطر المحفظة", "Portfolio risk matrix")}</h2></header><div className="body"><RiskMatrix grid={d.heatmap} onPick={() => nav("/risks")} /></div></section>
          </div>
        </div>
        <section className="panel" style={{ position: "sticky", top: 64 }}><header><div><h2>{T("التنبيهات التنفيذية", "Executive alerts")}</h2><p>{T(`${num(d.alerts.length)} مفتوحة، الأشد أولاً`, `${num(d.alerts.length)} open, most severe first`)}</p></div>
          <select className="input" style={{ width: 130 }} value={cat} onChange={e => setCat(e.target.value)} aria-label={T("نوع التنبيه", "Alert type")}><option value="">{T("كل الأنواع", "All types")}</option>{Object.entries(CAT).map(([key, l]) => <option key={key} value={key}>{T(...l)}</option>)}</select></header>
          <div style={{ maxHeight: "calc(100vh - 150px)", overflowY: "auto" }}><AlertList alerts={alerts} onChange={q.reload} /></div></section>
      </div>; }}</Async>
  </div>;
}
