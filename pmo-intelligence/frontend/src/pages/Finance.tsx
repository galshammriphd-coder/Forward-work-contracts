import { useState } from "react";
import { useApp, useLoad } from "../lib/core";
import { Async, Register } from "../lib/ui";
import { HBars, Lines, PairBars } from "../lib/charts";

export default function Finance({ pid }: { pid: number }) {
  const { T, money, num, date, can } = useApp();
  const [n, setN] = useState(0);
  const q = useLoad<any>(`/projects/${pid}/finance`, [n]);
  const sch = useLoad<any>(`/projects/${pid}/schedule`);
  const bump = () => setN(n + 1);
  const names: Record<string, [string, string]> = { PV: ["القيمة المخططة", "Planned value"], EV: ["القيمة المكتسبة", "Earned value"], AC: ["التكلفة الفعلية", "Actual cost"], SV: ["انحراف الجدول", "Schedule variance"],
    CV: ["انحراف التكلفة", "Cost variance"], SPI: ["مؤشر أداء الجدول", "Schedule performance index"], CPI: ["مؤشر أداء التكلفة", "Cost performance index"], EAC: ["التكلفة المتوقعة عند الإنجاز", "Estimate at completion"],
    ETC: ["المتبقي للإنجاز", "Estimate to complete"], VAC: ["الانحراف عند الإنجاز", "Variance at completion"] };
  if (!can("finance.read")) return <div className="note warning">{T("دورك لا يتيح الاطلاع على البيانات المالية.", "Your role does not include financial data.")}</div>;
  return <div className="stack">
    <Async q={q}>{d => {
      const m = d.metrics, e = m.evm, idx = d.s_curve.findIndex((r: any) => r.AC === undefined) - 1;
      const bad = (v: number | null) => (v != null && v < 0.9 ? (v < 0.8 ? "critical" : "warning") : "");
      return <>
        <div className="kpis">
          <div className="kpi" style={{ cursor: "default" }}><span>{T("الميزانية المعتمدة", "Approved budget")}</span><b>{money(m.budget)}</b><small>BAC</small></div>
          <div className="kpi" style={{ cursor: "default" }}><span>{T("المصروف الفعلي", "Actual spend")}</span><b className={m.over_budget ? "critical" : ""}>{money(m.actual)}</b><small>{num(m.budget ? (m.actual / m.budget) * 100 : 0)}% {T("من الميزانية", "of budget")}</small></div>
          <div className="kpi" style={{ cursor: "default" }}><span>{T("الالتزامات", "Commitments")}</span><b>{money(m.committed)}</b><small>{T("أوامر شراء وعقود لم تُصرف", "Orders and contracts not yet paid")}</small></div>
          <div className="kpi" style={{ cursor: "default" }}><span>{T("المتبقي بعد الالتزامات", "Remaining after commitments")}</span><b className={m.remaining < 0 ? "critical" : ""}>{money(m.remaining)}</b><small>{T("الميزانية − الفعلي − الالتزامات", "Budget − actual − commitments")}</small></div>
          <div className="kpi" style={{ cursor: "default" }}><span>SPI</span><b className={bad(e.SPI)}>{num(e.SPI, 2)}</b><small>{T("أقل من 1 = متأخر عن الخطة", "Below 1 = behind plan")}</small></div>
          <div className="kpi" style={{ cursor: "default" }}><span>CPI</span><b className={bad(e.CPI)}>{num(e.CPI, 2)}</b><small>{T("أقل من 1 = أعلى من التكلفة المخططة", "Below 1 = over planned cost")}</small></div>
          <div className="kpi" style={{ cursor: "default" }}><span>{T("التكلفة المتوقعة عند الإنجاز", "Estimate at completion")}</span><b className={e.EAC > m.budget * 1.05 ? "critical" : ""}>{money(e.EAC)}</b><small>EAC = BAC ÷ CPI</small></div>
          <div className="kpi" style={{ cursor: "default" }}><span>{T("الانحراف عند الإنجاز", "Variance at completion")}</span><b className={e.VAC < 0 ? "critical" : ""}>{money(e.VAC)}</b><small>VAC = BAC − EAC</small></div>
        </div>
        <div className="grid g2">
          <section className="panel"><header><div><h2>{T("المخطط مقابل الفعلي", "Planned against actual")}</h2><p>{T("القيمة المخططة التراكمية والتكلفة الفعلية حتى تاريخ البيانات", "Cumulative planned value and actual cost up to the data date")}</p></div></header>
            <div className="body">{d.s_curve.length ? <Lines x={d.s_curve.map((r: any) => r.date)} fmt={money} marker={idx}
              series={[{ name: T("القيمة المخططة (PV)", "Planned value (PV)"), color: "var(--c1)", values: d.s_curve.map((r: any) => r.PV) }, { name: T("التكلفة الفعلية (AC)", "Actual cost (AC)"), color: "var(--c2)", values: d.s_curve.map((r: any) => r.AC) }]} />
              : <p className="muted">{T("حدد تاريخي بداية ونهاية للمشروع لعرض المنحنى.", "Set project start and end dates to see the curve.")}</p>}</div></section>
          <section className="panel"><header><div><h2>{T("القيمة المكتسبة", "Earned value")}</h2><p>{T("كل رقم محسوب بالمحرك الحسابي بالصيغة المبينة", "Every figure is computed by the calculation engine with the formula shown")}</p></div></header>
            <div className="tbl-wrap"><table className="tbl"><thead><tr><th>{T("المؤشر", "Indicator")}</th><th className="num">{T("القيمة", "Value")}</th><th>{T("طريقة الحساب", "Formula")}</th></tr></thead>
              <tbody>{Object.keys(names).map(k => <tr key={k}><td><b className="ltr">{k}</b> — {T(...names[k])}</td><td className="num strong">{k === "SPI" || k === "CPI" ? num(e[k], 3) : money(e[k])}</td><td className="small muted"><bdi>{e.formulas[k]}</bdi></td></tr>)}</tbody></table></div>
            <div className="body small muted">{T("مصدر البيانات", "Data source")}: {T("الميزانية من سجل المشروع، التكلفة الفعلية من حركات التكلفة، الإنجاز من الأنشطة. الترجيح حسب", "budget from the project record, actual cost from cost entries, progress from activities. Weighted by")} <bdi>{e.inputs.weighting}</bdi>.
              {" "}{T("تاريخ البيانات", "Data date")}: {date(e.data_date)} · {T("آخر حركة تكلفة", "Last cost entry")}: {date(d.source.last_cost_entry)} · {T("آخر تحديث للمشروع", "Last project update")}: {date(d.source.last_project_update)}</div></section>
        </div>
        <div className="grid g2">
          <section className="panel"><header><h2>{T("التكاليف حسب المرحلة", "Cost by phase")}</h2></header><div className="body">
            {d.by_phase.length ? <PairBars names={[T("المخطط", "Planned"), T("الفعلي", "Actual")]} fmt={money} rows={d.by_phase.map((p: any) => ({ label: p.phase, a: p.planned, b: p.actual }))} /> : <p className="muted">{T("لا مراحل بعد.", "No phases yet.")}</p>}</div></section>
          <section className="panel"><header><h2>{T("التدفق النقدي الشهري", "Monthly cash flow")}</h2></header><div className="body">
            {d.cash_flow.length ? <HBars fmt={money} rows={d.cash_flow.map((c: any) => ({ label: c.month, value: c.actual, note: c.commitment ? `${T("التزامات", "Commitments")}: ${money(c.commitment)}` : undefined }))} /> : <p className="muted">{T("لا حركات تكلفة بعد.", "No cost entries yet.")}</p>}</div></section>
        </div>
        <section className="panel"><header><h2>{T("أعلى الأنشطة تكلفة", "Highest-cost activities")}</h2></header><div className="body">
          <PairBars names={[T("المخطط", "Planned"), T("الفعلي", "Actual")]} fmt={money} rows={d.by_activity.slice(0, 8).map((a: any) => ({ label: a.activity, a: a.planned, b: a.actual }))} /></div></section>
      </>;
    }}</Async>
    <Register resource="budgets" projectId={pid} perm="finance.write" noun={["بند ميزانية", "Budget line"]} title={T("بنود الميزانية", "Budget lines")} onChanged={bump}
      cols={[{ key: "category", label: ["البند", "Line"] }, { key: "planned_amount", label: ["المخطط", "Planned"], type: "money" }, { key: "approved_amount", label: ["المعتمد", "Approved"], type: "money" }, { key: "fiscal_year", label: ["السنة المالية", "Fiscal year"] }]}
      fields={[{ key: "category", label: ["اسم البند", "Line name"], required: true }, { key: "phase_id", label: ["المرحلة", "Phase"], type: "select", options: () => (sch.data?.phases || []).map((p: any) => [p.id, p.name]) },
        { key: "planned_amount", label: ["المبلغ المخطط", "Planned amount"], type: "number", required: true }, { key: "approved_amount", label: ["المبلغ المعتمد", "Approved amount"], type: "number" }, { key: "fiscal_year", label: ["السنة المالية", "Fiscal year"], type: "number", def: new Date().getFullYear() }]} />
    <Register resource="costs" projectId={pid} perm="finance.write" noun={["حركة تكلفة", "Cost entry"]} title={T("المصروفات والالتزامات", "Expenses and commitments")} onChanged={bump} sort={(a, b) => String(b.cost_date).localeCompare(String(a.cost_date))}
      cols={[{ key: "cost_date", label: ["التاريخ", "Date"], type: "date" }, { key: "kind", label: ["النوع", "Kind"], render: r => <span className={`tag ${r.kind === "actual" ? "" : "info"}`}>{r.kind === "actual" ? T("مصروف فعلي", "Actual") : T("التزام", "Commitment")}</span> },
        { key: "description", label: ["الوصف", "Description"] }, { key: "vendor", label: ["المورد", "Vendor"] }, { key: "amount", label: ["المبلغ", "Amount"], type: "money" }]}
      fields={[{ key: "kind", label: ["النوع", "Kind"], type: "select", def: "actual", required: true, options: [["actual", T("مصروف فعلي", "Actual expense")], ["commitment", T("التزام", "Commitment")]] },
        { key: "amount", label: ["المبلغ", "Amount"], type: "number", required: true }, { key: "cost_date", label: ["التاريخ", "Date"], type: "date", def: new Date().toISOString().slice(0, 10), required: true },
        { key: "activity_id", label: ["النشاط", "Activity"], type: "select", options: () => (sch.data?.activities || []).filter((a: any) => !a.is_summary).map((a: any) => [a.id, a.name]) },
        { key: "phase_id", label: ["المرحلة", "Phase"], type: "select", options: () => (sch.data?.phases || []).map((p: any) => [p.id, p.name]) }, { key: "vendor", label: ["المورد", "Vendor"] }, { key: "description", label: ["الوصف", "Description"], wide: true }]} />
  </div>;
}
