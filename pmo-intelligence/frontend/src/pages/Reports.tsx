import { useEffect, useState } from "react";
import { Download, FileBarChart, Printer } from "lucide-react";
import { api, saveBlob, useApp, useLoad } from "../lib/core";
import { Register } from "../lib/ui";
import { PairBars } from "../lib/charts";

export function ReportBuilder({ fixedProject }: { fixedProject?: number }) {
  const { T, N, meta, lang, fail } = useApp();
  const projects = useLoad<any[]>(fixedProject ? null : "/projects");
  const ports = useLoad<any[]>(fixedProject ? null : "/r/portfolios");
  const types: any[] = (meta?.report_types || []).filter((t: any) => !fixedProject || t.needs_project || ["risk", "benefits", "lessons"].includes(t.key));
  const [v, setV] = useState<any>({ type: fixedProject ? "project_status" : "executive_portfolio", lang, project_id: fixedProject || "", portfolio_id: "", date_from: "", date_to: "", comment: "" });
  const [rep, setRep] = useState<any>(null);
  const [off, setOff] = useState<string[]>([]);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const t = types.find(x => x.key === v.type);
  const body = () => ({ ...v, project_id: v.project_id ? +v.project_id : null, portfolio_id: v.portfolio_id ? +v.portfolio_id : null, include: rep && off.length ? rep.sections.map((s: any) => s.key).filter((k: string) => !off.includes(k)) : null });
  const build = async () => { setBusy("build"); setErr(""); try { setRep(await api.post("/reports/build", { ...body(), include: null })); setOff([]); } catch (e: any) { e.message === "NETWORK" ? fail(e) : setErr(e.message); setRep(null); } finally { setBusy(""); } };
  const exportAs = async (format: string) => { setBusy(format); try { saveBlob(await api.blob("/reports/export", { ...body(), format }), `${v.type}.${format}`); } catch (e) { fail(e); } finally { setBusy(""); } };
  useEffect(() => { if (fixedProject) build(); }, []);  // eslint-disable-line
  const set = (k: string, val: any) => setV({ ...v, [k]: val });
  return <div className="stack">
    <section className="panel no-print"><header><div><h2>{T("منشئ التقارير", "Report builder")}</h2><p>{T("اختر التقرير والنطاق والفترة، ثم اعرضه أو صدّره.", "Choose the report, scope and period, then preview or export it.")}</p></div></header>
      <div className="body stack">
        <div className="form-grid">
          <label className="field"><span>{T("التقرير", "Report")}</span><select className="input" value={v.type} onChange={e => set("type", e.target.value)}>{types.map(x => <option key={x.key} value={x.key}>{N(x)}</option>)}</select></label>
          <label className="field"><span>{T("لغة التقرير", "Report language")}</span><select className="input" value={v.lang} onChange={e => set("lang", e.target.value)}><option value="ar">العربية</option><option value="en">English</option></select></label>
          {!fixedProject && <label className="field"><span>{T("المشروع", "Project")}{t?.needs_project && <em> *</em>}</span><select className="input" value={v.project_id} onChange={e => set("project_id", e.target.value)}><option value="">{t?.needs_project ? T("اختر مشروعاً…", "Choose a project…") : T("كل المشاريع", "All projects")}</option>{(projects.data || []).map(p => <option key={p.id} value={p.id}>{N(p)}</option>)}</select></label>}
          {!fixedProject && !t?.needs_project && <label className="field"><span>{T("المحفظة", "Portfolio")}</span><select className="input" value={v.portfolio_id} onChange={e => set("portfolio_id", e.target.value)}><option value="">{T("كل المحافظ", "All portfolios")}</option>{(ports.data || []).map(p => <option key={p.id} value={p.id}>{N(p)}</option>)}</select></label>}
          <label className="field"><span>{T("من تاريخ", "From")}</span><input className="input" type="date" value={v.date_from} onChange={e => set("date_from", e.target.value)} /></label>
          <label className="field"><span>{T("إلى تاريخ", "To")}</span><input className="input" type="date" value={v.date_to} onChange={e => set("date_to", e.target.value)} /></label>
          <label className="field wide"><span>{T("تعليق تنفيذي (يظهر في التقرير)", "Executive comment (printed in the report)")}</span><textarea className="input" dir="auto" value={v.comment} onChange={e => set("comment", e.target.value)} /></label>
        </div>
        {rep && <div className="row small"><b>{T("الأقسام المضمنة:", "Sections included:")}</b>{rep.sections.filter((s: any) => s.key !== "kpis").map((s: any) => <label key={s.key} className="tag" style={{ cursor: "pointer" }}>
          <input type="checkbox" checked={!off.includes(s.key)} onChange={e => setOff(e.target.checked ? off.filter(k => k !== s.key) : [...off, s.key])} />{s.title}</label>)}</div>}
        {err && <div className="note critical" role="alert">{err}</div>}
        <div className="row"><button className="btn primary" disabled={!!busy} onClick={build}>{busy === "build" ? <i className="spin" /> : <FileBarChart />}{T("اعرض التقرير", "Preview report")}</button>
          {["pdf", "docx", "xlsx"].map(f => <button key={f} className="btn" disabled={!!busy || !rep} onClick={() => exportAs(f)}>{busy === f ? <i className="spin" /> : <Download />}{f === "pdf" ? "PDF" : f === "docx" ? "Word" : "Excel"}</button>)}
          <button className="btn" disabled={!rep} onClick={() => window.print()}><Printer />{T("اطبع", "Print")}</button></div>
      </div></section>
    {rep && <section className="panel" dir={rep.lang === "ar" ? "rtl" : "ltr"} lang={rep.lang}><header><div><h2>{rep.title}</h2><p>{rep.scope}{rep.period && ` · ${rep.period}`} · <bdi>{rep.generated_at}</bdi></p></div></header>
      <div className="body stack">
        <div><h3>{rep.summary_label}</h3><ul style={{ margin: "6px 0", paddingInlineStart: 20 }}>{rep.summary.map((s: string, i: number) => <li key={i}>{s}</li>)}</ul></div>
        {rep.comment && <div><h3>{rep.comment_label}</h3><p dir="auto">{rep.comment}</p></div>}
        {rep.sections.filter((s: any) => !off.includes(s.key)).map((s: any, i: number) => <div key={i} className="stack tight"><h3>{s.title}</h3>
          {s.kind === "kpis" ? <div className="grid g4">{s.items.map((it: any) => <div key={it.label} style={{ borderInlineStart: "2px solid var(--line)", paddingInlineStart: 10 }}><div className="small muted">{it.label}</div><div className="strong num" style={{ textAlign: "start" }}>{String(it.value ?? "—")}</div></div>)}</div>
            : <>{s.chart && <PairBars names={[s.chart.series[0].name, s.chart.series[1]?.name || ""]} rows={s.chart.labels.map((l: string, j: number) => ({ label: l, a: s.chart.series[0].values[j], b: s.chart.series[1]?.values[j] ?? 0 }))} />}
              {s.rows.length ? <div className="tbl-wrap" style={{ maxHeight: 420 }}><table className="tbl"><thead><tr>{s.head.map((h: string) => <th key={h}>{h}</th>)}</tr></thead><tbody>{s.rows.map((r: any[], j: number) => <tr key={j}>{r.map((c, k) => <td key={k} dir="auto">{c === null || c === "" ? "—" : String(c)}</td>)}</tr>)}</tbody></table></div> : <p className="muted">—</p>}</>}
        </div>)}
      </div></section>}
  </div>;
}

export default function Reports() {
  const { T, N, meta } = useApp();
  const types = (meta?.report_types || []).map((t: any) => [t.key, N(t)]) as [string, string][];
  const freq = [["daily", T("يومي", "Daily")], ["weekly", T("أسبوعي", "Weekly")], ["monthly", T("شهري", "Monthly")]] as [string, string][];
  return <div className="page">
    <div className="page-head"><div><h1>{T("التقارير والتحليلات", "Reports and analytics")}</h1><p>{T("اثنا عشر تقريراً أساسياً بالعربية والإنجليزية، تُحسب أرقامها من المحركات نفسها التي تغذي الشاشات.", "Twelve core reports in Arabic and English, computed by the same engines that feed the screens.")}</p></div></div>
    <div className="stack"><ReportBuilder />
      <Register resource="report_schedules" perm="report.read" noun={["جدولة تقرير", "Report schedule"]} title={T("التقارير الدورية", "Scheduled reports")}
        sub={T("يُعد التقرير في موعده ويُشعَر المستلمون داخل المنصة. تقارير المشاريع تُحفظ في وثائق المشروع.", "The report is produced on schedule and recipients are notified in the platform. Project reports are stored in the project's documents.")}
        cols={[{ key: "report_type", label: ["التقرير", "Report"], render: r => types.find(t => t[0] === r.report_type)?.[1] || r.report_type }, { key: "frequency", label: ["الدورية", "Frequency"], render: r => freq.find(f => f[0] === r.frequency)?.[1] },
          { key: "lang", label: ["اللغة", "Language"] }, { key: "recipient_roles", label: ["المستلمون", "Recipients"], render: r => (r.recipient_roles || []).map((k: string) => N((meta?.roles || []).find((x: any) => x.key === k))).join(T("، ", ", ")) },
          { key: "last_run_at", label: ["آخر تشغيل", "Last run"], type: "date" }, { key: "enabled", label: ["مفعّل", "Enabled"], render: r => r.enabled ? T("نعم", "Yes") : T("لا", "No") }]}
        fields={[{ key: "report_type", label: ["التقرير", "Report"], type: "select", required: true, def: "executive_portfolio", options: types }, { key: "frequency", label: ["الدورية", "Frequency"], type: "select", required: true, def: "weekly", options: freq },
          { key: "lang", label: ["اللغة", "Language"], type: "select", required: true, def: "ar", options: [["ar", "العربية"], ["en", "English"]] }, { key: "enabled", label: ["مفعّل", "Enabled"], type: "bool", def: true },
          { key: "recipient_roles", label: ["الأدوار المستلمة", "Recipient roles"], type: "multi", def: ["pmo_director"], options: (meta?.roles || []).map((r: any) => [r.key, N(r)]) }]} />
    </div></div>;
}
