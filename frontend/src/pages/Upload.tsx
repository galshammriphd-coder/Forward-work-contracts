import { DragEvent, useEffect, useState } from "react";
import { CheckCircle2, FileUp, Plus, RotateCcw, Save, Trash2 } from "lucide-react";
import { api } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { useStore } from "../lib/store";
import { ErrorBox, Note, PageHeader, SyntheticBanner } from "../components/ui";

const DTYPES = ["numeric", "categorical", "text", "multiselect", "datetime", "id", "empty"];
const LEVELS = ["nominal", "ordinal", "interval", "ratio"];
const ROLES = ["item", "demographic", "independent", "dependent", "open_text", "id", "response_time", "date", "other", "exclude"];
const ROLE_AR: Record<string, string> = { item: "بند استبانة", demographic: "ديموغرافي", independent: "مستقل", dependent: "تابع", open_text: "سؤال مفتوح", id: "معرّف", response_time: "زمن الاستجابة", date: "تاريخ", other: "أخرى", exclude: "استبعاد" };
const LEVEL_AR: Record<string, string> = { nominal: "اسمي", ordinal: "رتبي", interval: "فتري", ratio: "نسبي" };
const DTYPE_AR: Record<string, string> = { numeric: "رقمي", categorical: "فئوي", text: "نصي", multiselect: "اختيار متعدد", datetime: "تاريخ/وقت", id: "معرّف", empty: "فارغ" };

export default function UploadPage() {
  const { t, tr, lang } = useI18n();
  const { project, projectId, bump } = useStore();
  const [file, setFile] = useState<File | null>(null);
  const [delimiter, setDelimiter] = useState("");
  const [preview, setPreview] = useState<any>(null);
  const [error, setError] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [drag, setDrag] = useState(false);

  const doPreview = async (f: File, delim = delimiter) => {
    setFile(f); setBusy(true); setError(null);
    const fd = new FormData(); fd.append("file", f); if (delim) fd.append("delimiter", delim);
    try { setPreview(await api(`/api/projects/${projectId}/preview`, { method: "POST", body: fd })); } catch (e) { setError(e); setPreview(null); } finally { setBusy(false); }
  };
  const commit = async () => {
    if (!file) return;
    setBusy(true);
    const fd = new FormData(); fd.append("file", file); if (delimiter) fd.append("delimiter", delimiter);
    try { await api(`/api/projects/${projectId}/upload`, { method: "POST", body: fd }); setPreview(null); setFile(null); bump(); } catch (e) { setError(e); } finally { setBusy(false); }
  };
  const onDrop = (e: DragEvent) => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files?.[0]; if (f) doPreview(f); };

  if (!projectId) return <div className="card">{t("noProject")}</div>;
  return (
    <div>
      <PageHeader title={t("upload")} subtitle={tr("الخطوات 2–4: رفع ملف CSV ← معاينة ← تأكيد قاموس البيانات", "Steps 2–4: upload CSV → preview → confirm the data dictionary")} />
      <SyntheticBanner />
      <div onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)} onDrop={onDrop}
        className={`card mb-4 flex flex-col items-center justify-center gap-2 border-2 border-dashed py-10 text-center ${drag ? "border-brand-500 bg-brand-50 dark:bg-brand-950/30" : ""}`}>
        <FileUp size={32} className="text-brand-600" />
        <p className="font-medium">{tr("اسحب ملف CSV وأفلته هنا", "Drag and drop a CSV file here")}</p>
        <p className="text-xs text-ink-500">{tr("يدعم UTF-8 وUTF-8 BOM وWindows-1256 وغيرها؛ ويكتشف الفاصلة والفاصلة المنقوطة والجدولة تلقائياً", "UTF-8, UTF-8 BOM, Windows-1256…; comma / semicolon / tab detected automatically")}</p>
        <label className="btn-secondary cursor-pointer">{tr("اختيار ملف", "Choose file")}<input type="file" accept=".csv,.txt,.tsv" className="hidden" onChange={(e) => e.target.files?.[0] && doPreview(e.target.files[0])} /></label>
        {project?.dataset && <p className="text-xs text-ink-500">{tr("الملف الحالي", "Current file")}: <span dir="ltr">{project.dataset.filename} (v{project.dataset.version}, {project.dataset.n_rows}×{project.dataset.n_cols}, {project.dataset.encoding})</span> — {tr("رفع ملف جديد ينشئ إصداراً جديداً ويحتفظ بالسابق", "uploading creates a new version; previous versions are kept")}</p>}
      </div>
      <ErrorBox error={error} />
      {busy && <p className="text-sm text-ink-500">{t("running")}</p>}
      {preview && (
        <div className="card mb-4 space-y-3">
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <b dir="ltr">{preview.filename}</b>
            <span className="badge bg-ink-100 dark:bg-ink-800">{tr("الصفوف", "Rows")}: {preview.n_rows}</span>
            <span className="badge bg-ink-100 dark:bg-ink-800">{tr("الأعمدة", "Columns")}: {preview.n_cols}</span>
            <span className="badge bg-ink-100 dark:bg-ink-800">{tr("الترميز", "Encoding")}: {preview.encoding}</span>
            <span className="badge bg-ink-100 dark:bg-ink-800">{tr("الفاصل", "Delimiter")}: <code dir="ltr">{preview.delimiter === "\t" ? "\\t" : preview.delimiter}</code></span>
            <span className="badge bg-ink-100 dark:bg-ink-800">{tr("صفوف مكررة", "Duplicate rows")}: {preview.duplicates}</span>
            <select className="input w-auto" value={delimiter} onChange={(e) => { setDelimiter(e.target.value); file && doPreview(file, e.target.value); }}>
              <option value="">{tr("فاصل تلقائي", "Auto delimiter")}</option><option value=",">,</option><option value=";">;</option><option value={"\t"}>Tab</option><option value="|">|</option>
            </select>
          </div>
          {preview.warnings?.map((w: any, i: number) => <Note key={i} tone="warn">{w[lang]}</Note>)}
          <div className="max-h-80 overflow-auto">
            <table className="tbl"><thead><tr>{preview.columns.map((c: string) => <th key={c}>{c}</th>)}</tr></thead>
              <tbody>{preview.rows.map((r: any, i: number) => <tr key={i}>{preview.columns.map((c: string) => <td key={c} dir="auto">{r[c]}</td>)}</tr>)}</tbody></table>
          </div>
          <div className="flex gap-2">
            <button className="btn-primary" disabled={busy} onClick={commit}><CheckCircle2 size={14} />{tr("استيراد البيانات", "Import data")}</button>
            <button className="btn-ghost" onClick={() => { setPreview(null); setFile(null); }}>{t("cancel")}</button>
          </div>
        </div>
      )}
      {project?.dataset && <DictionaryEditor />}
    </div>
  );
}

function DictionaryEditor() {
  const { tr, lang } = useI18n();
  const { projectId, dictionary, bump } = useStore();
  const [d, setD] = useState<any>(null);
  const [error, setError] = useState<any>(null);
  const [saved, setSaved] = useState(false);
  const [newDim, setNewDim] = useState("");
  useEffect(() => { if (dictionary) setD(JSON.parse(JSON.stringify(dictionary))); }, [dictionary]);
  if (!d) return null;
  const setVar = (name: string, patch: any) => setD({ ...d, variables: d.variables.map((v: any) => (v.name === name ? { ...v, ...patch } : v)) });
  const setDimOf = (name: string, dim: string) => {
    const dims = d.dimensions.map((x: any) => ({ ...x, items: x.items.filter((i: string) => i !== name) }));
    const target = dims.find((x: any) => x.name === dim);
    if (target) target.items.push(name);
    setD({ ...d, dimensions: dims, variables: d.variables.map((v: any) => (v.name === name ? { ...v, dimension: dim || null, ...(dim ? { is_likert: true, role: "item" } : {}) } : v)) });
  };
  const addDim = () => { if (!newDim.trim() || d.dimensions.some((x: any) => x.name === newDim.trim())) return; setD({ ...d, dimensions: [...d.dimensions, { name: newDim.trim(), label: newDim.trim(), items: [], axis: null }] }); setNewDim(""); };
  const delDim = (name: string) => setD({ ...d, dimensions: d.dimensions.filter((x: any) => x.name !== name), variables: d.variables.map((v: any) => (v.dimension === name ? { ...v, dimension: null } : v)) });
  const save = async (confirmIt: boolean, regenerate = false) => {
    setError(null);
    try {
      const body = { ...d, confirmed: confirmIt || d.confirmed, dimensions: d.dimensions.filter((x: any) => x.items.length), regenerate_bands: regenerate };
      await api(`/api/projects/${projectId}/dictionary`, { method: "PUT", json: body });
      setSaved(true); setTimeout(() => setSaved(false), 2500); bump();
    } catch (e) { setError(e); }
  };
  const reset = async () => { if (confirm(tr("إعادة توليد القاموس المقترح؟ ستفقد تعديلاتك.", "Regenerate the suggested dictionary? Your edits will be lost."))) { await api(`/api/projects/${projectId}/dictionary/reset`, { method: "POST" }); bump(); } };
  const lk = d.likert;
  const L = (m: Record<string, string>, k: string) => (lang === "ar" ? m[k] || k : k);
  return (
    <div className="space-y-4">
      <div className="card">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h3 className="font-semibold">{tr("قاموس البيانات (Data Dictionary)", "Data dictionary")}
            {d.confirmed ? <span className="badge ms-2 bg-emerald-100 text-emerald-800">{tr("مؤكد", "Confirmed")}</span> : <span className="badge ms-2 bg-amber-100 text-amber-800">{tr("مقترح — بانتظار التأكيد", "Suggested — awaiting confirmation")}</span>}
          </h3>
          <div className="flex gap-2">
            <button className="btn-ghost" onClick={reset}><RotateCcw size={14} />{tr("إعادة الاقتراح", "Re-suggest")}</button>
            <button className="btn-secondary" onClick={() => save(false)}><Save size={14} />{tr("حفظ", "Save")}</button>
            <button className="btn-primary" onClick={() => save(true)}><CheckCircle2 size={14} />{tr("تأكيد القاموس", "Confirm dictionary")}</button>
          </div>
        </div>
        {saved && <Note>{tr("تم الحفظ وتسجيل التعديلات في سجل العمليات.", "Saved and logged in the audit trail.")}</Note>}
        <ErrorBox error={error} />
        {!d.structure_confident && (
          <Note tone="warn">{tr("لم تتضح بنية الاستبانة من أسماء الأعمدة؛ لم تُفترض أي أبعاد غير موجودة. حدّد المحاور/الأبعاد وأسند إليها البنود يدوياً.",
            "The questionnaire structure is not clear from the column names; no dimensions were assumed. Please define the dimensions and assign items manually.")}
            {d.ungrouped_items?.length > 0 && <div className="mt-1 text-xs" dir="ltr">{d.ungrouped_items.join(", ")}</div>}</Note>
        )}
        <div className="max-h-[560px] overflow-auto">
          <table className="tbl">
            <thead><tr>
              <th>{tr("المتغير", "Variable")}</th><th>{tr("الوصف", "Label")}</th><th>{tr("النوع", "Type")}</th><th>{tr("مستوى القياس", "Level")}</th>
              <th>{tr("الدور", "Role")}</th><th>{tr("البعد", "Dimension")}</th><th>{tr("عكسي", "Reverse")}</th><th>{tr("القيم", "Values")}</th><th>{tr("المفقود", "Missing")}</th>
            </tr></thead>
            <tbody>
              {d.variables.map((v: any) => (
                <tr key={v.name}>
                  <td className="font-medium" dir="auto">{v.name}{v.is_likert && <span className="badge ms-1 bg-brand-100 text-brand-800">Likert</span>}</td>
                  <td><input className="input min-w-[120px] py-0.5" dir="auto" value={v.label || ""} onChange={(e) => setVar(v.name, { label: e.target.value })} /></td>
                  <td><select className="input py-0.5" value={v.dtype} onChange={(e) => setVar(v.name, { dtype: e.target.value })}>{DTYPES.map((x) => <option key={x} value={x}>{L(DTYPE_AR, x)}</option>)}</select></td>
                  <td><select className="input py-0.5" value={v.level} onChange={(e) => setVar(v.name, { level: e.target.value })}>{LEVELS.map((x) => <option key={x} value={x}>{L(LEVEL_AR, x)}</option>)}</select></td>
                  <td><select className="input py-0.5" value={v.role} onChange={(e) => setVar(v.name, { role: e.target.value, is_likert: e.target.value === "item" ? v.is_likert : false })}>{ROLES.map((x) => <option key={x} value={x}>{L(ROLE_AR, x)}</option>)}</select></td>
                  <td><select className="input py-0.5" value={v.dimension || ""} onChange={(e) => setDimOf(v.name, e.target.value)}>
                    <option value="">—</option>{d.dimensions.map((x: any) => <option key={x.name} value={x.name}>{x.label || x.name}</option>)}</select></td>
                  <td className="text-center">
                    <input type="checkbox" checked={!!v.reverse} disabled={!v.is_likert} onChange={(e) => setVar(v.name, { reverse: e.target.checked })} />
                    {v.reverse_suggested && !v.reverse && <div className="text-[10px] text-amber-600" title={v.reverse_reason}>{tr("مقترح", "suggested")}</div>}
                  </td>
                  <td className="max-w-[220px] truncate text-xs text-ink-500" dir="auto" title={v.values}>{v.values}</td>
                  <td className="text-xs tabular-nums">{v.n_missing}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-xs text-ink-500">{tr("البنود العكسية تُعاد ترميزها فقط بعد تأكيدك (عمود «عكسي»). الاقتراحات مبنية على اسم المتغير أو الارتباط السالب بالدرجة الكلية.",
          "Reverse items are recoded only after you tick “Reverse”. Suggestions come from the column name or a negative item-total correlation.")}</p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="card">
          <h3 className="mb-2 font-semibold">{tr("الأبعاد والمحاور", "Dimensions & axes")}</h3>
          <div className="space-y-2">
            {d.dimensions.map((x: any) => (
              <div key={x.name} className="rounded-lg border border-ink-200 p-2 dark:border-ink-700">
                <div className="flex items-center gap-2">
                  <input className="input py-0.5" dir="auto" value={x.label || ""} onChange={(e) => setD({ ...d, dimensions: d.dimensions.map((y: any) => (y.name === x.name ? { ...y, label: e.target.value } : y)) })} />
                  <input className="input w-36 py-0.5" dir="auto" placeholder={tr("المحور (اختياري)", "Axis (optional)")} value={x.axis || ""} onChange={(e) => setD({ ...d, dimensions: d.dimensions.map((y: any) => (y.name === x.name ? { ...y, axis: e.target.value } : y)) })} />
                  <button className="btn-ghost text-red-600" onClick={() => delDim(x.name)}><Trash2 size={14} /></button>
                </div>
                <div className="mt-1 text-xs text-ink-500" dir="ltr">{x.name}: {x.items.join(", ") || "—"}</div>
              </div>
            ))}
          </div>
          <div className="mt-2 flex gap-2">
            <input className="input" dir="auto" placeholder={tr("اسم بعد جديد", "New dimension name")} value={newDim} onChange={(e) => setNewDim(e.target.value)} />
            <button className="btn-secondary" onClick={addDim}><Plus size={14} /></button>
          </div>
        </div>
        <div className="card space-y-2">
          <h3 className="font-semibold">{tr("إعدادات مقياس ليكرت", "Likert scale settings")}</h3>
          <div className="grid grid-cols-3 gap-2">
            <div><label className="label">{tr("الحد الأدنى", "Minimum")}</label><input className="input" type="number" dir="ltr" value={lk.min} onChange={(e) => setD({ ...d, likert: { ...lk, min: Number(e.target.value) } })} /></div>
            <div><label className="label">{tr("الحد الأعلى", "Maximum")}</label><input className="input" type="number" dir="ltr" value={lk.max} onChange={(e) => setD({ ...d, likert: { ...lk, max: Number(e.target.value) } })} /></div>
            <div><label className="label">{tr("عدد فئات التفسير", "Interpretation bands")}</label><input className="input" type="number" min={2} max={7} dir="ltr" value={lk.bands ?? lk.interpretation.length} onChange={(e) => setD({ ...d, likert: { ...lk, bands: Number(e.target.value) } })} /></div>
          </div>
          <button className="btn-ghost text-xs" onClick={() => save(false, true)}>{tr("إعادة حساب الحدود بطول فئة متساوٍ", "Recompute equal-width bands")}</button>
          <table className="tbl">
            <thead><tr><th>{tr("من", "From")}</th><th>{tr("إلى", "To")}</th><th>{tr("التسمية (ع)", "Label (AR)")}</th><th>{tr("التسمية (En)", "Label (EN)")}</th></tr></thead>
            <tbody>{lk.interpretation.map((b: any, i: number) => (
              <tr key={i}>
                {(["from", "to"] as const).map((k) => <td key={k}><input className="input w-20 py-0.5" dir="ltr" type="number" step="0.01" value={b[k]} onChange={(e) => { const it = [...lk.interpretation]; it[i] = { ...b, [k]: Number(e.target.value) }; setD({ ...d, likert: { ...lk, interpretation: it } }); }} /></td>)}
                {(["ar", "en"] as const).map((k) => <td key={k}><input className="input py-0.5" dir="auto" value={b[k]} onChange={(e) => { const it = [...lk.interpretation]; it[i] = { ...b, [k]: e.target.value }; setD({ ...d, likert: { ...lk, interpretation: it } }); }} /></td>)}
              </tr>))}
            </tbody>
          </table>
          <div>
            <label className="label">{tr("الحد الأدنى للبنود المجاب عنها لحساب الدرجة المركبة", "Minimum share of answered items for a composite score")}</label>
            <input className="input w-28" type="number" step="0.05" min={0.1} max={1} dir="ltr" value={d.composite_min_answered ?? 0.5} onChange={(e) => setD({ ...d, composite_min_answered: Number(e.target.value) })} />
          </div>
          <div>
            <label className="label">{tr("رموز القيم المفقودة", "Missing-value codes")}</label>
            <input className="input" dir="ltr" value={(d.missing_tokens || []).filter(Boolean).join(", ")} onChange={(e) => setD({ ...d, missing_tokens: ["", ...e.target.value.split(",").map((s) => s.trim()).filter(Boolean)] })} />
          </div>
        </div>
      </div>
    </div>
  );
}
