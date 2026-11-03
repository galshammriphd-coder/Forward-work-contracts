import { useEffect, useState } from "react";
import { Check, RotateCcw, Sparkles, Trash2, X } from "lucide-react";
import { api } from "../lib/api";
import { fmtNum, useI18n } from "../lib/i18n";
import { useStore } from "../lib/store";
import { VarMulti, VarSelect } from "../components/Analysis";
import { ErrorBox, Kpi, NeedsData, Note, PageHeader, Tabs } from "../components/ui";

export default function Cleaning() {
  const { t, tr, lang } = useI18n();
  const { projectId, project, bump, version } = useStore();
  const [q, setQ] = useState<any>(null);
  const [ops, setOps] = useState<any[]>([]);
  const [error, setError] = useState<any>(null);
  const [tab, setTab] = useState<"ops" | "manual" | "data">("ops");
  const load = () => {
    if (!projectId || !project?.dataset) return;
    api(`/api/projects/${projectId}/quality`).then(setQ).catch(setError);
    api(`/api/projects/${projectId}/cleaning`).then((r) => setOps(r.operations)).catch(setError);
  };
  useEffect(load, [projectId, project?.dataset, version]);
  const act = async (fn: () => Promise<any>) => { setError(null); try { await fn(); bump(); } catch (e) { setError(e); } };
  const decide = (id: string, status: string) => act(() => api(`/api/projects/${projectId}/cleaning/${id}`, { method: "PATCH", json: { status } }));
  const statusBadge = (s: string) => s === "accepted" ? "bg-emerald-100 text-emerald-800" : s === "rejected" ? "bg-red-100 text-red-800" : "bg-amber-100 text-amber-800";
  return (
    <div>
      <PageHeader title={t("cleaning")} subtitle={tr("الخطوتان 5–6: تقرير المشكلات ومراجعة كل عملية معالجة بالقبول أو الرفض", "Steps 5–6: issue report, then accept or reject each processing step")}
        actions={<>
          <button className="btn-secondary" onClick={() => act(() => api(`/api/projects/${projectId}/cleaning/propose`, { method: "POST" }))}><Sparkles size={14} />{tr("اقتراح عمليات المعالجة", "Propose operations")}</button>
          <button className="btn-ghost" onClick={() => confirm(tr("استعادة البيانات الأصلية؟ ستعود جميع العمليات إلى «قيد المراجعة».", "Restore original data? All operations return to pending.")) && act(() => api(`/api/projects/${projectId}/cleaning/restore`, { method: "POST" }))}><RotateCcw size={14} />{tr("استعادة الأصل", "Restore original")}</button>
        </>} />
      <NeedsData>
        <ErrorBox error={error} />
        {q && (
          <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-5">
            <Kpi label={tr("مؤشر الجودة", "Quality index")} value={fmtNum(q.quality_score, 1)} tone={q.quality_score >= 90 ? "good" : "warn"} />
            <Kpi label={tr("الصفوف الأصلية", "Original rows")} value={q.n_rows} />
            <Kpi label={tr("بعد المعالجة", "After processing")} value={q.rows_after_cleaning} />
            <Kpi label={tr("الحالات المكتملة", "Complete cases")} value={q.complete_cases} />
            <Kpi label={tr("القيم المفقودة", "Missing cells")} value={`${q.missing_cells} (${fmtNum(q.missing_pct, 1)}%)`} />
          </div>
        )}
        {q && <Note>{lang === "ar" ? q.score_note_ar : q.score_note_en}</Note>}
        <Note tone="warn">{tr("لا تُحذف أي بيانات تلقائياً: كل عملية مقترحة تبقى «قيد المراجعة» حتى تقبلها. الملف الأصلي محفوظ مشفراً ولا يُعدَّل، وتُسجَّل كل القرارات. القيم المتطرفة تُعرض للمراجعة فقط ولا يُقترح حذفها.",
          "Nothing is removed automatically: proposed operations stay pending until you accept them. The original file is stored encrypted and never modified, and every decision is logged. Outliers are flagged only — never proposed for removal.")}</Note>
        <Tabs value={tab} onChange={setTab} tabs={[{ key: "ops", label: tr("عمليات المعالجة", "Operations") }, { key: "manual", label: tr("إضافة معالجة يدوية", "Add manual step") }, { key: "data", label: tr("عرض البيانات", "Data view") }]} />
        {tab === "ops" && (
          <div className="space-y-3">
            {ops.length > 0 && (
              <div className="flex gap-2">
                <button className="btn-secondary" onClick={() => act(() => api(`/api/projects/${projectId}/cleaning/bulk`, { method: "POST", json: { status: "accepted" } }))}><Check size={14} />{tr("قبول كل المعلّق", "Accept all pending")}</button>
                <button className="btn-ghost" onClick={() => act(() => api(`/api/projects/${projectId}/cleaning/bulk`, { method: "POST", json: { status: "rejected" } }))}><X size={14} />{tr("رفض كل المعلّق", "Reject all pending")}</button>
              </div>
            )}
            {ops.length === 0 && <div className="card text-sm text-ink-500">{tr("لا توجد عمليات بعد. اضغط «اقتراح عمليات المعالجة».", "No operations yet. Click “Propose operations”.")}</div>}
            {ops.map((o) => (
              <div key={o.id} className="card flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <b>{lang === "ar" ? o.label_ar : o.label_en}</b>
                    <span className={`badge ${statusBadge(o.status)}`}>{t(o.status as any)}</span>
                    <span className="badge bg-ink-100 text-ink-600 dark:bg-ink-800 dark:text-ink-300">{o.source === "manual" ? tr("يدوي", "manual") : tr("مقترح آلياً", "auto-proposed")}</span>
                    {o.affected != null && <span className="text-xs text-ink-500">{tr("المتأثر", "affected")}: {o.affected}</span>}
                  </div>
                  <p className="mt-1 text-sm">{lang === "ar" ? o.reason_ar : o.reason_en}</p>
                  <details className="text-xs text-ink-500"><summary className="cursor-pointer">{tr("المعاملات", "Parameters")}</summary><pre dir="ltr" className="overflow-auto">{JSON.stringify(o.params, null, 1)}</pre></details>
                </div>
                <div className="flex gap-1">
                  <button className="btn-secondary" disabled={o.status === "accepted"} onClick={() => decide(o.id, "accepted")}><Check size={14} />{t("accept")}</button>
                  <button className="btn-secondary" disabled={o.status === "rejected"} onClick={() => decide(o.id, "rejected")}><X size={14} />{t("reject")}</button>
                  <button className="btn-ghost text-red-600" onClick={() => act(() => api(`/api/projects/${projectId}/cleaning/${o.id}`, { method: "DELETE" }))}><Trash2 size={14} /></button>
                </div>
              </div>
            ))}
            {q?.univariate_outliers?.length > 0 && (
              <div className="card">
                <h4 className="mb-1 text-sm font-semibold">{tr("قيم متطرفة (للمراجعة فقط)", "Extreme values (review only)")}</h4>
                <ul className="text-sm">{q.univariate_outliers.map((u: any) => <li key={u.column}>{u.column}: {u.count} — <span dir="ltr">{u.values.slice(0, 8).join(", ")}</span></li>)}</ul>
                {q.multivariate_outliers && <p className="text-sm">{tr("متعددة المتغيرات (ماهالانوبيس)", "Multivariate (Mahalanobis)")}: {q.multivariate_outliers.count}</p>}
              </div>
            )}
            {q?.op_log?.length > 0 && (
              <div className="card">
                <h4 className="mb-1 text-sm font-semibold">{tr("سجل التطبيق (قابل لإعادة التنفيذ)", "Application log (replayable)")}</h4>
                <table className="tbl"><thead><tr><th>#</th><th>{tr("العملية", "Operation")}</th><th>{tr("الصفوف قبل", "Rows before")}</th><th>{tr("بعد", "After")}</th><th>{tr("القيم المعدلة", "Changed")}</th></tr></thead>
                  <tbody>{q.op_log.map((l: any, i: number) => <tr key={i}><td>{i + 1}</td><td>{l.type}</td><td>{l.rows_before}</td><td>{l.rows_after}</td><td>{l.changed}</td></tr>)}</tbody></table>
              </div>
            )}
          </div>
        )}
        {tab === "manual" && <ManualOp onDone={() => { bump(); setTab("ops"); }} />}
        {tab === "data" && <DataView />}
      </NeedsData>
    </div>
  );
}

function ManualOp({ onDone }: { onDone: () => void }) {
  const { tr } = useI18n();
  const { projectId, dictionary } = useStore();
  const [type, setType] = useState("impute");
  const [cols, setCols] = useState<string[]>([]);
  const [col, setCol] = useState("");
  const [method, setMethod] = useState("median");
  const [mapping, setMapping] = useState("");
  const [range, setRange] = useState<{ min?: number; max?: number }>({});
  const [reason, setReason] = useState("");
  const [error, setError] = useState<any>(null);
  const submit = async () => {
    let params: any;
    if (type === "impute") params = { columns: cols, method, ...(method === "person_mean" ? { dimension_items: (dictionary?.dimensions || []).find((d: any) => d.items.includes(cols[0]))?.items || cols } : {}) };
    else if (type === "drop_columns" || type === "pseudonymize") params = { columns: cols };
    else if (type === "recode") params = { column: col, mapping: Object.fromEntries(mapping.split(/[\n,؛;]/).map((s) => s.split("=").map((x) => x.trim())).filter((p) => p.length === 2 && p[0])) };
    else if (type === "set_missing") params = { column: col, ...range };
    else if (type === "winsorize") params = { column: col, lower: range.min ?? 0.01, upper: range.max ?? 0.99 };
    try { await api(`/api/projects/${projectId}/cleaning`, { method: "POST", json: { type, params, reason_ar: reason, reason_en: reason } }); onDone(); } catch (e) { setError(e); }
  };
  const multi = ["impute", "drop_columns", "pseudonymize"].includes(type);
  return (
    <div className="card max-w-2xl space-y-3">
      <div><label className="label">{tr("نوع المعالجة", "Operation")}</label>
        <select className="input" value={type} onChange={(e) => setType(e.target.value)}>
          <option value="impute">{tr("تعويض القيم المفقودة", "Impute missing values")}</option>
          <option value="recode">{tr("إعادة ترميز / تصحيح قيم فئوية", "Recode / fix categories")}</option>
          <option value="set_missing">{tr("تحويل قيم خارج نطاق إلى مفقودة", "Set out-of-range to missing")}</option>
          <option value="winsorize">{tr("تهذيب القيم المتطرفة (Winsorize)", "Winsorize")}</option>
          <option value="drop_columns">{tr("حذف متغيرات", "Remove variables")}</option>
          <option value="pseudonymize">{tr("إخفاء الهوية (ترميز المعرّفات)", "Pseudonymize identifiers")}</option>
        </select></div>
      {multi ? <div><label className="label">{tr("المتغيرات", "Variables")}</label><VarMulti kind="any" value={cols} onChange={setCols} /></div>
        : <div><label className="label">{tr("المتغير", "Variable")}</label><VarSelect kind="any" value={col} onChange={setCol} /></div>}
      {type === "impute" && <div><label className="label">{tr("الطريقة", "Method")}</label>
        <select className="input" value={method} onChange={(e) => setMethod(e.target.value)}>
          <option value="median">{tr("الوسيط", "Median")}</option><option value="mean">{tr("المتوسط", "Mean")}</option><option value="mode">{tr("المنوال", "Mode")}</option>
          <option value="person_mean">{tr("متوسط المستجيب في البعد نفسه", "Respondent's mean within dimension")}</option></select></div>}
      {type === "recode" && <div><label className="label">{tr("التحويلات (القيمة=الجديدة، سطر لكل تحويل)", "Mappings (old=new, one per line)")}</label><textarea className="input h-24" dir="auto" value={mapping} onChange={(e) => setMapping(e.target.value)} placeholder={"male=Male\nFemal=Female"} /></div>}
      {(type === "set_missing" || type === "winsorize") && (
        <div className="grid grid-cols-2 gap-2">
          <div><label className="label">{type === "winsorize" ? tr("المئين الأدنى (0–1)", "Lower quantile") : tr("الحد الأدنى المقبول", "Min valid")}</label><input className="input" dir="ltr" type="number" step="any" onChange={(e) => setRange({ ...range, min: e.target.value === "" ? undefined : Number(e.target.value) })} /></div>
          <div><label className="label">{type === "winsorize" ? tr("المئين الأعلى (0–1)", "Upper quantile") : tr("الحد الأعلى المقبول", "Max valid")}</label><input className="input" dir="ltr" type="number" step="any" onChange={(e) => setRange({ ...range, max: e.target.value === "" ? undefined : Number(e.target.value) })} /></div>
        </div>)}
      <div><label className="label">{tr("المبرر العلمي (يُسجَّل في التقرير)", "Scientific justification (logged in the report)")}</label><input className="input" dir="auto" value={reason} onChange={(e) => setReason(e.target.value)} /></div>
      <ErrorBox error={error} />
      <button className="btn-primary" disabled={!reason || (multi ? !cols.length : !col)} onClick={submit}>{tr("إضافة وتطبيق", "Add & apply")}</button>
    </div>
  );
}

export function DataView() {
  const { tr } = useI18n();
  const { projectId, version } = useStore();
  const [stage, setStage] = useState("analysis");
  const [page, setPage] = useState(1);
  const [d, setD] = useState<any>(null);
  useEffect(() => { api(`/api/projects/${projectId}/data?stage=${stage}&page=${page}&size=50`).then(setD).catch(() => setD(null)); }, [projectId, stage, page, version]);
  return (
    <div className="card">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <select className="input w-auto" value={stage} onChange={(e) => { setStage(e.target.value); setPage(1); }}>
          <option value="raw">{tr("الأصلية (غير معدلة)", "Original (unchanged)")}</option><option value="typed">{tr("بعد تحديد الأنواع", "Typed")}</option>
          <option value="clean">{tr("بعد التنظيف", "Cleaned")}</option><option value="analysis">{tr("جاهزة للتحليل (مع الدرجات المركبة)", "Analysis-ready (with composites)")}</option>
        </select>
        {d && <span className="text-sm text-ink-500">{d.total} {tr("صف", "rows")}</span>}
        <button className="btn-ghost" disabled={page <= 1} onClick={() => setPage(page - 1)}>‹</button><span className="text-sm">{page}</span>
        <button className="btn-ghost" disabled={!d || page * 50 >= d.total} onClick={() => setPage(page + 1)}>›</button>
      </div>
      {d && <div className="max-h-[520px] overflow-auto"><table className="tbl"><thead><tr><th>#</th>{d.columns.map((c: string) => <th key={c}>{c}</th>)}</tr></thead>
        <tbody>{d.rows.map((r: any) => <tr key={r.__row__}><td className="text-ink-400">{r.__row__}</td>{d.columns.map((c: string) => <td key={c} dir="auto">{r[c] === null ? <span className="text-ink-300">·</span> : typeof r[c] === "number" ? +r[c].toFixed(3) : String(r[c])}</td>)}</tr>)}</tbody></table></div>}
    </div>
  );
}
