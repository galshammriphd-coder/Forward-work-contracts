import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { FlaskConical, FolderOpen, Plus, Trash2 } from "lucide-react";
import { api } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { useStore } from "../lib/store";
import { ErrorBox, PageHeader } from "../components/ui";

export default function Projects() {
  const { t, tr } = useI18n();
  const { setProjectId, projectId, bump } = useStore();
  const [list, setList] = useState<any[]>([]);
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [error, setError] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const nav = useNavigate();
  const load = () => api("/api/projects").then(setList).catch(setError);
  useEffect(() => { load(); }, []);
  const create = async () => {
    setBusy(true);
    try { const p = await api("/api/projects", { method: "POST", json: { name, description: desc } }); setProjectId(p.id); nav("/upload"); } catch (e) { setError(e); } finally { setBusy(false); }
  };
  const demo = async () => {
    setBusy(true);
    try { const p = await api("/api/projects/demo", { method: "POST" }); setProjectId(p.id); bump(); nav("/upload"); } catch (e) { setError(e); } finally { setBusy(false); }
  };
  const remove = async (id: string) => {
    if (!confirm(tr("سيُحذف المشروع وجميع بياناته وملفاته نهائياً. هل أنت متأكد؟", "The project, its data and files will be permanently deleted. Continue?"))) return;
    await api(`/api/projects/${id}`, { method: "DELETE" });
    if (id === projectId) setProjectId(null);
    load();
  };
  return (
    <div>
      <PageHeader title={t("projects")} subtitle={tr("كل مشروع معزول ببياناته وتحليلاته وسجل عملياته", "Each project is isolated with its own data, analyses and audit log")} />
      <div className="mb-6 grid gap-4 md:grid-cols-2">
        <div className="card space-y-2">
          <h3 className="font-semibold">{t("newProject")}</h3>
          <input className="input" placeholder={tr("عنوان المشروع / الدراسة", "Project / study title")} value={name} onChange={(e) => setName(e.target.value)} />
          <textarea className="input h-20" placeholder={tr("وصف مختصر", "Short description")} value={desc} onChange={(e) => setDesc(e.target.value)} />
          <button className="btn-primary" disabled={!name || busy} onClick={create}><Plus size={14} />{t("create")}</button>
        </div>
        <div className="card space-y-2 border-amber-300 dark:border-amber-800">
          <h3 className="flex items-center gap-2 font-semibold"><FlaskConical size={16} />{t("demoProject")}</h3>
          <p className="text-sm text-ink-600 dark:text-ink-300">
            {tr("ينشئ مشروعاً ببيانات استبانة اصطناعية (323 استجابة، 4 أبعاد، بند عكسي، أسئلة مفتوحة) تتضمن مشكلات جودة مقصودة لعرض جميع الوظائف. البيانات موسومة بوضوح بأنها اصطناعية وليست نتائج دراسة فعلية، ويمكنك استبدالها بملف CSV حقيقي في أي وقت.",
              "Creates a project with a synthetic questionnaire dataset (323 responses, 4 dimensions, a reverse item, open questions) with deliberate quality issues. It is clearly labelled synthetic — not results of a real study — and can be replaced with a real CSV at any time.")}
          </p>
          <button className="btn-secondary" disabled={busy} onClick={demo}><FlaskConical size={14} />{tr("إنشاء المشروع التجريبي", "Create demo project")}</button>
        </div>
      </div>
      <ErrorBox error={error} />
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {list.map((p) => (
          <div key={p.id} className={`card ${p.id === projectId ? "ring-2 ring-brand-500" : ""}`}>
            <div className="flex items-start justify-between gap-2">
              <h4 className="font-semibold">{p.name}</h4>
              {p.is_synthetic && <span className="badge shrink-0 bg-amber-100 text-amber-800">{tr("اصطناعية", "Synthetic")}</span>}
            </div>
            <p className="line-clamp-2 text-xs text-ink-500">{p.description}</p>
            <div className="mt-2 text-xs text-ink-500">
              {p.dataset ? <span dir="ltr">{p.dataset.filename} · {p.dataset.n_rows}×{p.dataset.n_cols} · v{p.dataset.version}</span> : tr("لا توجد بيانات", "No data")}
              {" · "}{p.n_analyses} {tr("تحليل", "analyses")}
            </div>
            <div className="mt-3 flex gap-2">
              <button className="btn-primary" onClick={() => { setProjectId(p.id); nav("/"); }}><FolderOpen size={14} />{t("open")}</button>
              <button className="btn-ghost text-red-600" onClick={() => remove(p.id)}><Trash2 size={14} />{t("delete")}</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
