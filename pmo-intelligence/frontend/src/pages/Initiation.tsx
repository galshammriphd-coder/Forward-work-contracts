import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { AlertTriangle, Check, ChevronLeft, ChevronRight, FileUp, Plus, RefreshCw, Rocket, Trash2, Upload } from "lucide-react";
import { api, useApp, useLoad } from "../lib/core";
import { Modal, Src, Status } from "../lib/ui";
import { useLists } from "./Portfolio";

const FIELD: Record<string, [string, string]> = { name: ["اسم المشروع", "Project name"], code: ["رمز المشروع", "Project ID"], description: ["الوصف", "Description"], sponsor: ["راعي المشروع", "Project sponsor"], manager: ["مدير المشروع", "Project manager"],
  business_owner: ["مالك الأعمال", "Business owner"], department: ["الإدارة", "Department"], priority: ["الأولوية", "Priority"], strategic_objective: ["الهدف الاستراتيجي", "Strategic objective"], business_case: ["مبررات المشروع", "Business case"],
  scope: ["النطاق", "Scope"], out_of_scope: ["خارج النطاق", "Out of scope"], budget: ["الميزانية", "Budget"], start_date: ["تاريخ البداية", "Start date"], end_date: ["تاريخ النهاية", "End date"], duration: ["المدة (شهر)", "Duration (months)"],
  objectives: ["الأهداف", "Objectives"], deliverables: ["المخرجات", "Deliverables"], stakeholders: ["أصحاب المصلحة", "Stakeholders"], success_criteria: ["معايير النجاح", "Success criteria"], kpis: ["مؤشرات الأداء", "KPIs"], assumptions: ["الافتراضات", "Assumptions"],
  constraints: ["القيود", "Constraints"], dependencies: ["الاعتماديات", "Dependencies"], requirements: ["المتطلبات", "Requirements"], approvals: ["الاعتمادات", "Approvals"], milestones: ["المعالم الرئيسية", "Milestones"], risks: ["المخاطر", "Risks"], milestone_dates: ["تواريخ بعض المعالم", "Dates of some milestones"] };
const STEPS: [string, string][] = [["رفع الميثاق", "Upload charter"], ["تحليل الوثيقة", "Document analysis"], ["بيانات المشروع", "Project intelligence"], ["هيكل العمل WBS", "Generate WBS"], ["الجدول الزمني", "Generate schedule"], ["إطار المخاطر", "Risk framework"], ["وثائق المشروع", "Project documents"], ["المراجعة والاعتماد", "Review & approval"], ["تفعيل المشروع", "Activate project"]];
const SECTION: Record<string, [string, string]> = { profile: ["بيانات المشروع المستخرجة", "Extracted project data"], wbs: ["هيكل العمل والأنشطة", "WBS and activities"], schedule: ["الجدول الزمني", "Schedule"], risks: ["سجل المخاطر", "Risk register"], budget: ["الميزانية وتوزيعها", "Budget and its distribution"], documents: ["وثائق إدارة المشروع", "Management documents"] };

const SrcRef = ({ s }: { s: any }) => { const { T } = useApp(); return s ? <span className="small muted" title={s.snippet}>{T("ص", "p.")}<bdi>{s.page}</bdi>{s.section ? ` · ${s.section}` : ""}</span> : <span className="small muted">—</span>; };

export default function Initiation() {
  const { sid } = useParams();
  const nav = useNavigate();
  const { T, N, fail, toast, date, money, num } = useApp();
  const list = useLoad<any[]>("/initiation");
  const lists = useLists();
  const [s, setS] = useState<any>(null);
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [over, setOver] = useState(false);
  const [doc, setDoc] = useState<any>(null);
  const [place, setPlace] = useState<any>({ portfolio_id: "", program_id: "", department_id: "" });
  useEffect(() => { if (sid) api.get(`/initiation/${sid}`).then(x => { setS(x); setStep(x.status === "activated" ? 8 : x.draft.documents ? 7 : x.draft.risks ? 5 : x.draft.schedule ? 4 : x.draft.activities ? 3 : 1); }).catch(fail); else { setS(null); setStep(0); } }, [sid]);  // eslint-disable-line
  const call = async (key: string, fn: () => Promise<any>, msg?: string) => { setBusy(key); setErr(""); try { const r = await fn(); setS(r); msg && toast(msg); return r; } catch (e: any) { e.message === "NETWORK" ? fail(e) : setErr(e.message); } finally { setBusy(""); } };
  const upload = async (f?: File | null) => { if (!f) return; const fd = new FormData(); fd.append("file", f); setBusy("upload"); setErr("");
    try { const r = await api.post("/initiation", fd); list.reload(); nav(`/initiation/${r.id}`); } catch (e: any) { e.message === "NETWORK" ? fail(e) : setErr(e.message); } finally { setBusy(""); } };
  const gen = (what: string) => call(what, () => api.post(`/initiation/${s.id}/generate/${what}`));
  const patch = (body: any) => call("patch", () => api.patch(`/initiation/${s.id}`, body));
  const approve = (section: string, approved = true) => call(section, () => api.post(`/initiation/${s.id}/approve`, { section, approved }));
  const d = s?.draft, done = s?.status === "activated";
  const ready = [true, !!s, !!s, !!d?.activities, !!d?.schedule, !!d?.risks, !!d?.documents, !!d?.documents, !!d?.documents];
  const next = async () => {
    if (step === 2 && !d.activities) await gen("wbs"); if (step === 3 && !d.schedule) await gen("schedule"); if (step === 4 && !d.risks) await gen("risks"); if (step === 5 && !d.documents) await gen("documents");
    setStep(Math.min(8, step + 1));
  };
  const Bar = () => <div className="row" style={{ justifyContent: "space-between", marginBlockStart: 16 }}>
    <button className="btn" disabled={step <= 1} onClick={() => setStep(step - 1)}><ChevronRight className="flip" style={{ transform: "scaleX(-1)" }} />{T("السابق", "Back")}</button>
    {step < 8 && <button className="btn primary" disabled={!!busy} onClick={next}>{busy ? <i className="spin" /> : null}{step >= 2 && step <= 5 && !ready[step + 1] ? T("ولّد ثم تابع", "Generate and continue") : T("التالي", "Next")}<ChevronLeft className="flip" style={{ transform: "scaleX(-1)" }} /></button>}</div>;
  const actRow = (i: number, key: string, val: any) => { const a = [...d.activities]; a[i] = { ...a[i], [key]: val, tag: "user" }; return a; };

  return <div className="page">
    <div className="page-head"><div><h1>{T("إنشاء مشروع من الميثاق", "Create a project from its charter")}</h1>
      <p>{T("ارفع ميثاق المشروع. يستخرج النظام بياناته مع مصدر كل معلومة، ويقترح هيكل العمل والجدول والمخاطر والوثائق. لا يُنشأ المشروع إلا بعد مراجعتك واعتمادك.", "Upload the project charter. The system extracts its data with a source for every item and proposes the WBS, schedule, risks and documents. The project is created only after you review and approve.")}</p></div></div>
    <div className="steps" role="list">{STEPS.map(([a, e], i) => <button key={i} className={`${i === step ? "now" : ""} ${i < step || (done && i <= 8) ? "done" : ""}`} disabled={!ready[i] || (i === 0 && !!s)} onClick={() => setStep(i)}>{T(a, e)}</button>)}</div>
    {err && <div className="note critical" role="alert" style={{ marginBlockEnd: 12 }}><AlertTriangle />{err}</div>}

    {!s && <div className="grid split"><section className="panel"><div className="body">
      <label className={`drop ${over ? "over" : ""}`} onDragOver={e => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)} onDrop={e => { e.preventDefault(); setOver(false); upload(e.dataTransfer.files[0]); }}>
        {busy === "upload" ? <><i className="spin" /><b>{T("يقرأ الوثيقة ويستخرج بياناتها…", "Reading the document and extracting its data…")}</b></> : <><FileUp size={28} strokeWidth={1.5} /><b>{T("اسحب ميثاق المشروع هنا أو اضغط لاختياره", "Drop the project charter here or select to choose it")}</b>
          <span className="small muted">PDF · DOCX · DOC · XLSX · XLS · PPTX · TXT — {T("عربي أو إنجليزي", "Arabic or English")}</span><span className="btn primary"><Upload />{T("اختر ملفاً", "Choose a file")}</span></>}
        <input type="file" hidden accept=".pdf,.docx,.doc,.xlsx,.xls,.pptx,.txt,.md" onChange={e => upload(e.target.files?.[0])} /></label>
      <p className="small muted" style={{ marginBlockStart: 10 }}>{T("التحليل يجري على هذا الخادم. لا تُرسل الوثيقة إلى أي جهة خارجية.", "Analysis runs on this server. The document is not sent to any outside party.")}</p></div></section>
      <section className="panel"><header><h2>{T("جلساتك السابقة", "Your earlier sessions")}</h2></header>{(list.data || []).length === 0 ? <div className="empty">{T("لا جلسات بعد.", "No sessions yet.")}</div> :
        <div>{(list.data || []).map(x => <button key={x.id} className="cite" style={{ border: 0, borderBlockEnd: "1px solid var(--line-2)", borderRadius: 0 }} onClick={() => x.status === "activated" ? nav(`/projects/${x.project_id}`) : nav(`/initiation/${x.id}`)}>
          <span className="row"><b className="grow">{x.name || x.filename}</b><Status v={x.status} /></span><span className="small muted"><bdi>{x.filename}</bdi> · {date(x.created_at)}</span></button>)}</div>}</section></div>}

    {s && step === 1 && <section className="panel"><header><div><h2>{T("نتيجة تحليل الوثيقة", "Document analysis result")}</h2><p><bdi>{s.filename}</bdi></p></div></header><div className="body stack">
      <div className="grid g4">{[[T("الصفحات", "Pages"), d.stats.pages], [T("المقاطع المقروءة", "Passages read"), d.stats.segments], [T("الجداول", "Tables"), d.stats.tables], [T("حقول مستخرجة", "Fields extracted"), d.stats.fields_found], [T("بنود قوائم", "List items"), d.stats.items_found], [T("لغة الوثيقة", "Document language"), d.language === "ar" ? "العربية" : "English"]]
        .map(([l, v]) => <div key={l as string}><div className="small muted">{l}</div><div className="strong" style={{ fontSize: "1.2rem" }}>{v}</div></div>)}</div>
      {d.missing.length > 0 ? <div className="note warning"><AlertTriangle /><div><b>{T("بيانات ناقصة في الميثاق", "Data missing from the charter")}</b><div>{d.missing.map((m: string) => T(...(FIELD[m] || [m, m]))).join(T("، ", ", "))}</div>
        <div className="small">{T("لن يختلقها النظام. أدخلها في الخطوة التالية أو اتركها ناقصة.", "The system will not invent them. Enter them in the next step or leave them missing.")}</div></div></div> : <div className="note"><Check />{T("كل البيانات الأساسية موجودة في الميثاق.", "All key data is present in the charter.")}</div>}
      {d.conflicts.map((c: any, i: number) => <div key={i} className="note critical"><AlertTriangle /><div><b>{T("تعارض داخل الميثاق", "Conflict inside the charter")} — {T(...(FIELD[c.field] || [c.field, c.field]))}</b><div>{T(c.message_ar, c.message_en)}</div></div></div>)}
      <Bar /></div></section>}

    {s && step === 2 && <div className="stack"><section className="panel"><header><div><h2>{T("ملف المشروع", "Project profile")}</h2><p>{T("عدّل أي قيمة خاطئة. ما تعدله يُوسم «مدخلة».", "Correct any wrong value. What you change is tagged “User defined”.")}</p></div></header>
      <div className="tbl-wrap"><table className="tbl"><thead><tr><th style={{ width: 180 }}>{T("البند", "Item")}</th><th>{T("القيمة", "Value")}</th><th>{T("التصنيف", "Tag")}</th><th>{T("المصدر في الميثاق", "Source in the charter")}</th></tr></thead>
        <tbody>{["name", "code", "sponsor", "manager", "business_owner", "department", "priority", "strategic_objective", "budget", "start_date", "end_date", "duration", "description", "business_case", "scope", "out_of_scope"].map(k => { const f = d.profile[k];
          return <tr key={k}><td>{T(...FIELD[k])}</td><td>{k === "duration" ? <span className="num">{f?.value ?? "—"}</span> : ["description", "business_case", "scope", "out_of_scope"].includes(k)
            ? <textarea className="input" dir="auto" disabled={done} defaultValue={f?.value || ""} key={`${k}${f?.value}`} placeholder={T("غير مذكور في الميثاق", "Not stated in the charter")} onBlur={e => e.target.value !== (f?.value || "") && patch({ profile: { [k]: e.target.value } })} />
            : <input className="input" dir="auto" disabled={done} type={k.endsWith("_date") ? "date" : k === "budget" ? "number" : "text"} defaultValue={f?.value ?? ""} key={`${k}${f?.value}`} placeholder={T("غير مذكور في الميثاق", "Not stated in the charter")}
              onBlur={e => String(e.target.value) !== String(f?.value ?? "") && patch({ profile: { [k]: k === "budget" && e.target.value ? +e.target.value : e.target.value } })} />}</td>
            <td>{f ? <Src v={f.tag} /> : <span className="tag warning">{T("ناقص", "Missing")}</span>}</td><td><SrcRef s={f?.source} /></td></tr>; })}</tbody></table></div></section>
      <div className="grid g2">{["objectives", "deliverables", "stakeholders", "kpis", "success_criteria", "assumptions", "constraints", "dependencies", "requirements"].map(k => <section className="panel" key={k}><header><h3>{T(...FIELD[k])}</h3><span className="small muted">{(d.lists[k] || []).length}</span></header>
        {(d.lists[k] || []).length ? <div className="tbl-wrap"><table className="tbl"><tbody>{d.lists[k].map((it: any, i: number) => <tr key={i}><td dir="auto">{it.name || it.text}{it.role ? <span className="muted"> — {it.role}</span> : null}{it.target_raw ? <span className="muted"> — {it.target_raw}</span> : null}</td><td style={{ width: 1 }}><Src v={it.tag} /></td><td style={{ width: 130 }}><SrcRef s={it.source} /></td></tr>)}</tbody></table></div>
          : <div className="body muted small">{T("غير مذكور في الميثاق.", "Not stated in the charter.")}</div>}</section>)}</div>
      <section className="panel"><div className="body row">{s.approvals.profile ? <span className="tag good"><Check />{T("اعتُمدت البيانات المستخرجة", "Extracted data approved")}</span> :
        <button className="btn" disabled={!!busy || done} onClick={() => approve("profile").then(() => toast(T("اعتُمدت البيانات، وولّدت الأتمتة هيكل العمل", "Data approved; automation generated the WBS")))}><Check />{T("اعتمد البيانات المستخرجة", "Approve extracted data")}</button>}
        <span className="small muted">{T("اعتماد هذه البيانات يشغّل قاعدة الأتمتة «عند اعتماد بيانات الميثاق: أنشئ WBS».", "Approving this data fires the automation rule “On charter data approved: generate the WBS”.")}</span></div></section><Bar /></div>}

    {s && step === 3 && d.activities && <div className="stack">
      {(d.wbs_assumptions || []).map((a: string, i: number) => <div key={i} className="note warning"><AlertTriangle />{a}</div>)}
      <section className="panel"><header><div><h2>{T("هيكل تقسيم العمل المقترح", "Proposed work breakdown structure")}</h2><p>{T(`${d.phases.length} مراحل، ${d.wbs.filter((w: any) => w.kind !== "phase").length} مخرج وحزمة عمل، ${d.activities.length} نشاطاً ومهمة فرعية. عدّل الأسماء والمدد، أضف أو احذف.`, `${d.phases.length} phases, ${d.wbs.filter((w: any) => w.kind !== "phase").length} deliverables and work packages, ${d.activities.length} activities and subtasks. Edit names and durations, add or remove.`)}</p></div>
        <div className="row"><button className="btn sm" disabled={!!busy || done} onClick={() => gen("wbs")}><RefreshCw />{T("ولّد من جديد", "Regenerate")}</button>
          <button className="btn sm" disabled={done} onClick={() => { const last = d.activities[d.activities.length - 1]; patch({ activities: [...d.activities, { ...last, key: `U${Date.now()}`, code: `ACT-${String(d.activities.length + 1).padStart(3, "0")}`, name: T("نشاط جديد", "New activity"), parent: null, deps: [{ pred: last.key, type: "FS", lag: 0 }], duration_days: 5, tag: "user", wbs_code: `${last.wbs_code.split(".").slice(0, -1).join(".")}.${d.activities.length + 1}`, estimated_cost: 0, weight: 0 }] }); }}><Plus />{T("أضف نشاطاً", "Add activity")}</button></div></header>
        <div className="tbl-wrap" style={{ maxHeight: 520 }}><table className="tbl"><thead><tr><th>WBS</th><th>{T("النشاط", "Activity")}</th><th>{T("المرحلة", "Phase")}</th><th className="num" style={{ width: 90 }}>{T("المدة", "Days")}</th><th>{T("يعتمد على", "Depends on")}</th><th className="num">{T("التكلفة التقديرية", "Estimated cost")}</th><th>{T("معيار الإنجاز", "Completion criterion")}</th><th>{T("التصنيف", "Tag")}</th><th /></tr></thead>
          <tbody>{d.activities.map((a: any, i: number) => { const sum = d.activities.some((x: any) => x.parent === a.key);
            return <tr key={a.key}><td className="num">{a.wbs_code}</td><td style={{ paddingInlineStart: a.parent ? 30 : 12, minWidth: 260 }}><input className="input inline" dir="auto" disabled={done} defaultValue={a.name} key={a.name} style={{ fontWeight: sum ? 600 : 400 }} onBlur={e => e.target.value !== a.name && patch({ activities: actRow(i, "name", e.target.value) })} aria-label={T("اسم النشاط", "Activity name")} /></td>
              <td className="small">{d.phases.find((p: any) => p.key === a.phase)?.name}</td>
              <td>{sum ? <span className="muted">—</span> : <input className="input inline num" type="number" min={1} disabled={done} defaultValue={a.duration_days} key={a.duration_days} onBlur={e => +e.target.value !== a.duration_days && patch({ activities: actRow(i, "duration_days", Math.max(1, +e.target.value)) })} aria-label={T("المدة", "Duration")} />}</td>
              <td className="small muted"><bdi>{a.deps.map((x: any) => `${d.activities.find((y: any) => y.key === x.pred)?.wbs_code || "?"} ${x.type}${x.lag ? (x.lag > 0 ? "+" : "") + x.lag : ""}`).join(", ") || "—"}</bdi></td>
              <td className="num">{money(a.estimated_cost)}</td><td className="small">{a.completion_criteria || "—"}</td><td><Src v={a.tag} /></td>
              <td className="act">{!done && !sum && <button className="btn ghost sm icon danger" aria-label={T("احذف النشاط", "Remove activity")} onClick={() => { const preds = a.deps; patch({ activities: d.activities.filter((x: any) => x.key !== a.key).map((x: any) => ({ ...x, deps: x.deps.flatMap((dp: any) => dp.pred === a.key ? preds : [dp]) })) }); }}><Trash2 /></button>}</td></tr>; })}</tbody></table></div></section><Bar /></div>}

    {s && step === 4 && d.schedule && <div className="stack">
      {d.schedule.warnings.map((w: string, i: number) => <div key={i} className="note warning"><AlertTriangle />{w}</div>)}
      <div className="kpis"><div className="kpi" style={{ cursor: "default" }}><span>{T("البداية", "Start")}</span><b>{date(d.schedule.start)}</b></div><div className="kpi" style={{ cursor: "default" }}><span>{T("الانتهاء المحسوب", "Calculated finish")}</span><b>{date(d.schedule.finish)}</b><small>{T("تاريخ الميثاق", "Charter date")}: {date(d.profile.end_date?.value)}</small></div>
        <div className="kpi" style={{ cursor: "default" }}><span>{T("أيام العمل", "Working days")}</span><b>{num(d.schedule.duration_days)}</b></div><div className="kpi" style={{ cursor: "default" }}><span>{T("أنشطة المسار الحرج", "Critical-path activities")}</span><b>{num(d.schedule.critical_path.length)}</b></div></div>
      <section className="panel"><header><div><h2>{T("الجدول الزمني المحسوب", "Calculated schedule")}</h2><p>{T("التواريخ والمسار الحرج من محرك الجدولة الحسابي، لا من الذكاء الاصطناعي. لتغييرها عدّل المدد في الخطوة السابقة.", "Dates and the critical path come from the scheduling engine, not from AI. To change them, edit durations in the previous step.")}</p></div><Src v="calculated" /></header>
        <div className="tbl-wrap" style={{ maxHeight: 420 }}><table className="tbl"><thead><tr><th>WBS</th><th>{T("النشاط", "Activity")}</th><th>{T("البداية", "Start")}</th><th>{T("النهاية", "End")}</th><th className="num">{T("المدة", "Days")}</th><th className="num">{T("الفائض", "Float")}</th><th>{T("المسار الحرج", "Critical path")}</th></tr></thead>
          <tbody>{d.activities.map((a: any) => <tr key={a.key}><td className="num">{a.wbs_code}</td><td style={{ paddingInlineStart: a.parent ? 30 : 12, fontWeight: a.is_summary ? 600 : 400 }}>{a.name}</td><td>{date(a.planned_start)}</td><td>{date(a.planned_end)}</td><td className="num">{a.is_summary ? "—" : a.duration_days}</td><td className="num">{a.total_float}</td><td>{a.is_critical && <span className="tag critical">{T("حرج", "Critical")}</span>}</td></tr>)}</tbody></table></div></section>
      <section className="panel"><header><h2>{T("المعالم الرئيسية", "Milestones")}</h2></header><div className="tbl-wrap"><table className="tbl"><thead><tr><th>{T("المعلم", "Milestone")}</th><th>{T("التاريخ المستهدف", "Target date")}</th><th>{T("التصنيف", "Tag")}</th><th>{T("المصدر", "Source")}</th></tr></thead>
        <tbody>{d.milestones.map((m: any, i: number) => <tr key={i}><td>{m.name}</td><td>{m.target_date ? date(m.target_date) : <span className="tag warning">{T("بلا تاريخ في الميثاق", "No date in the charter")}</span>}</td><td><Src v={m.tag} /></td><td><SrcRef s={m.source} /></td></tr>)}</tbody></table></div></section><Bar /></div>}

    {s && step === 5 && d.risks && <div className="stack"><section className="panel"><header><div><h2>{T("سجل المخاطر الأولي", "Initial risk register")}</h2><p>{T("مخاطر الميثاق مستخرجة كما هي. الباقي مقترح من قيود الميثاق وافتراضاته ومن بنية الجدول، على مستويات المشروع والمرحلة والمخرج وحزمة العمل والنشاط.", "Charter risks are extracted as written. The rest are proposed from the charter's constraints and assumptions and from the schedule, at project, phase, deliverable, work-package and activity level.")}</p></div>
      <button className="btn sm" disabled={!!busy || done} onClick={() => gen("risks")}><RefreshCw />{T("ولّد من جديد", "Regenerate")}</button></header>
      <div className="tbl-wrap" style={{ maxHeight: 560 }}><table className="tbl"><thead><tr><th>{T("الرمز", "ID")}</th><th>{T("المستوى", "Level")}</th><th>{T("الخطر", "Risk")}</th><th>{T("الفئة", "Category")}</th><th style={{ width: 70 }}>{T("ح", "P")}</th><th style={{ width: 70 }}>{T("أ", "I")}</th><th className="num">{T("الدرجة", "Score")}</th><th>{T("التصنيف", "Rating")}</th><th>{T("المعالجة", "Mitigation")}</th><th>{T("الوسم", "Tag")}</th><th /></tr></thead>
        <tbody>{d.risks.map((r: any, i: number) => { const setR = (k: string, v: any) => { const rs = [...d.risks]; const nr = { ...r, [k]: v, rating_estimated: false }; nr.score = nr.probability * nr.impact; rs[i] = nr; patch({ risks: rs }); };
          return <tr key={r.code}><td className="num">{r.code}</td><td className="small">{{ project: T("المشروع", "Project"), phase: T("المرحلة", "Phase"), deliverable: T("المخرج", "Deliverable"), work_package: T("حزمة العمل", "Work package"), activity: T("النشاط", "Activity") }[r.scope_level as string]}</td>
            <td style={{ minWidth: 240 }}>{r.title}{r.rating_estimated && <div className="small" style={{ color: "var(--warning)" }}>{T("الميثاق لم يحدد الاحتمالية والأثر؛ القيمتان تقدير يحتاج تأكيدك.", "The charter gives no probability or impact; both values are estimates for you to confirm.")}</div>}</td><td className="small">{r.category}</td>
            {["probability", "impact"].map(k => <td key={k}><select className="input inline" disabled={done} value={r[k]} onChange={e => setR(k, +e.target.value)} aria-label={k}>{[1, 2, 3, 4, 5].map(n => <option key={n}>{n}</option>)}</select></td>)}
            <td className="num strong">{r.probability * r.impact}</td><td><Status v={r.probability * r.impact <= 4 ? "low" : r.probability * r.impact <= 9 ? "moderate" : r.probability * r.impact <= 14 ? "high" : "critical"} /></td><td className="small" style={{ minWidth: 220 }}>{r.mitigation || <span className="muted">—</span>}</td><td><Src v={r.tag} /></td>
            <td className="act">{!done && <button className="btn ghost sm icon danger" aria-label={T("احذف الخطر", "Remove risk")} onClick={() => patch({ risks: d.risks.filter((_: any, j: number) => j !== i) })}><Trash2 /></button>}</td></tr>; })}</tbody></table></div></section><Bar /></div>}

    {s && step === 6 && d.documents && <div className="stack"><section className="panel"><header><div><h2>{T("مسودات وثائق إدارة المشروع", "Draft project management documents")}</h2><p>{T(`${d.documents.length} وثيقة بُنيت من البيانات التي راجعتها. تُحفظ كمسودات في قاعدة معرفة المشروع عند التفعيل.`, `${d.documents.length} documents built from the data you reviewed. They are stored as drafts in the project knowledge base on activation.`)}</p></div>
      <button className="btn sm" disabled={!!busy || done} onClick={() => gen("documents")}><RefreshCw />{T("أعد توليد الوثائق", "Regenerate documents")}</button></header>
      <div className="tbl-wrap"><table className="tbl"><tbody>{d.documents.map((x: any) => <tr key={x.key} className="click" onClick={() => setDoc(x)}><td>{x.title}</td><td className="small muted">{num(x.content.length)} {T("حرفاً", "characters")}</td><td><Src v={x.tag} /></td><td className="act"><button className="btn ghost sm">{T("اعرض وعدّل", "View and edit")}</button></td></tr>)}</tbody></table></div></section><Bar /></div>}

    {s && step === 7 && d.documents && <div className="stack"><section className="panel"><header><div><h2>{T("المراجعة والاعتماد", "Review and approval")}</h2><p>{T("لا تتحول مخرجات الذكاء الاصطناعي إلى بيانات معتمدة إلا باعتمادك لكل قسم.", "AI output becomes approved data only when you approve each section.")}</p></div></header>
      <div className="tbl-wrap"><table className="tbl"><thead><tr><th>{T("القسم", "Section")}</th><th>{T("المحتوى", "Contents")}</th><th>{T("الحالة", "Status")}</th><th /></tr></thead><tbody>{s.sections.map((k: string) => { const ap = s.approvals[k];
        const what: Record<string, string> = { profile: `${Object.keys(d.profile).length} ${T("حقلاً", "fields")}${d.missing.length ? ` · ${d.missing.length} ${T("ناقص", "missing")}` : ""}`, wbs: `${d.activities.length} ${T("نشاطاً", "activities")}`, schedule: `${date(d.schedule?.start)} → ${date(d.schedule?.finish)}`,
          risks: `${d.risks?.length} ${T("خطراً", "risks")}`, budget: d.profile.budget ? money(d.profile.budget.value) : T("لا ميزانية في الميثاق", "No budget in the charter"), documents: `${d.documents.length} ${T("وثيقة", "documents")}` };
        return <tr key={k}><td className="strong">{T(...SECTION[k])}</td><td>{what[k]}</td><td>{ap ? <span className="tag good"><Check />{T("اعتمده", "Approved by")} <bdi>{ap.by}</bdi></span> : <span className="tag warning">{T("بانتظار اعتمادك", "Awaiting your approval")}</span>}</td>
          <td className="act">{!done && (ap ? <button className="btn ghost sm" onClick={() => approve(k, false)}>{T("تراجع عن الاعتماد", "Withdraw approval")}</button> : <button className="btn sm primary" disabled={!!busy} onClick={() => approve(k)}><Check />{T("اعتمد", "Approve")}</button>)}</td></tr>; })}</tbody></table></div>
      <div className="body row"><Src v="extracted" /><Src v="ai" /><Src v="user" /><Src v="calculated" /><span className="small muted">{T("كل معلومة في المسودة تحمل أحد هذه التصنيفات الأربعة.", "Every item in the draft carries one of these four tags.")}</span></div></section><Bar /></div>}

    {s && step === 8 && <section className="panel"><header><h2>{done ? T("فُعّل المشروع", "Project activated") : T("تفعيل المشروع", "Activate the project")}</h2></header><div className="body stack">
      {done ? <><div className="note"><Check />{T("أُنشئ المشروع في قاعدة البيانات بكل أنشطته ومخاطره ووثائقه، وحُفظ خط الأساس الأول.", "The project was created in the database with all its activities, risks and documents, and the first baseline was saved.")}</div>
        <div><button className="btn primary" onClick={() => nav(`/projects/${s.project_id}`)}><Rocket />{T("افتح مركز قيادة المشروع", "Open the project command centre")}</button></div></> : <>
        {s.sections.filter((k: string) => !s.approvals[k]).length > 0 && <div className="note warning"><AlertTriangle />{T("أقسام لم تُعتمد بعد: ", "Sections not approved yet: ")}{s.sections.filter((k: string) => !s.approvals[k]).map((k: string) => T(...SECTION[k])).join(T("، ", ", "))}</div>}
        <div className="form-grid">{[["portfolio_id", "المحفظة", "Portfolio", lists.portfolios], ["program_id", "البرنامج", "Programme", lists.programs], ["department_id", "الإدارة", "Department", lists.departments]].map(([k, a, e, rows]: any) =>
          <label className="field" key={k}><span>{T(a, e)}</span><select className="input" value={place[k]} onChange={ev => setPlace({ ...place, [k]: ev.target.value })}><option value="">{T("— غير محدد —", "— None —")}</option>{rows.map((r: any) => <option key={r.id} value={r.id}>{N(r)}</option>)}</select></label>)}</div>
        <p className="small muted">{T("عند التفعيل: يُنشأ سجل المشروع، تُحسب التواريخ بمحرك الجدولة، يُحفظ خط الأساس، يُفهرس الميثاق في قاعدة المعرفة، وتبدأ دورة الاعتماد.", "On activation: the project record is created, dates are computed by the scheduling engine, the baseline is saved, the charter is indexed into the knowledge base, and the approval lifecycle starts.")}</p>
        <div><button className="btn primary" disabled={!!busy || s.sections.some((k: string) => !s.approvals[k])} onClick={async () => { setBusy("activate"); setErr("");
          try { const r = await api.post(`/initiation/${s.id}/activate`, Object.fromEntries(Object.entries(place).map(([k, v]) => [k, v ? +(v as string) : null]))); toast(T("أُنشئ المشروع", "Project created")); nav(`/projects/${r.project_id}`); } catch (e: any) { e.message === "NETWORK" ? fail(e) : setErr(e.message); } finally { setBusy(""); } }}>
          {busy === "activate" ? <i className="spin" /> : <Rocket />}{T("أنشئ المشروع", "Create the project")}</button></div></>}
      <Bar /></div></section>}

    {doc && <DocEditor doc={doc} readOnly={done} onClose={() => setDoc(null)} onSave={content => patch({ documents: d.documents.map((x: any) => x.key === doc.key ? { ...x, content, tag: "user" } : x) })} />}
  </div>;
}

function DocEditor({ doc, onClose, onSave, readOnly }: { doc: any; onClose: () => void; onSave: (c: string) => Promise<any>; readOnly: boolean }) {
  const { T } = useApp();
  const [v, setV] = useState(doc.content);
  return <Modal wide title={doc.title} onClose={onClose} footer={!readOnly && <><button className="btn" onClick={onClose}>{T("إلغاء", "Cancel")}</button><button className="btn primary" disabled={v === doc.content} onClick={() => onSave(v).then(onClose)}>{T("احفظ التعديل", "Save changes")}</button></>}>
    <textarea className="input" dir="auto" style={{ minHeight: "58vh", fontSize: ".9rem" }} value={v} readOnly={readOnly} onChange={e => setV(e.target.value)} aria-label={doc.title} /></Modal>;
}
