import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { api } from "../lib/api";
import { fmtP, useI18n } from "../lib/i18n";
import { useStore } from "../lib/store";
import { VarMulti, VarSelect } from "../components/Analysis";
import ResultView from "../components/ResultView";
import { ErrorBox, NeedsData, Note, PageHeader } from "../components/ui";
import { PURPOSES, TestAdvisor } from "./Analyses";

export default function Hypotheses() {
  const { t, tr, lang } = useI18n();
  const { project, projectId, bump } = useStore();
  const [form, setForm] = useState<any>({ purpose: "difference", ivs: [], direction: "two-sided" });
  const [active, setActive] = useState<string | null>(null);
  const [shown, setShown] = useState<any>(null);
  const [error, setError] = useState<any>(null);
  const hyps: any[] = project?.hypotheses || [];
  const add = async () => {
    try { await api(`/api/projects/${projectId}/hypotheses`, { method: "POST", json: form }); setForm({ purpose: "difference", ivs: [], direction: "two-sided" }); bump(); } catch (e) { setError(e); }
  };
  const del = async (id: string) => { await api(`/api/projects/${projectId}/hypotheses/${id}`, { method: "DELETE" }); bump(); };
  const show = async (aid: string) => setShown(await api(`/api/projects/${projectId}/analyses/${aid}`));
  const decisionBadge = (d: any) => !d ? <span className="badge bg-ink-100 text-ink-600">{tr("لم تُختبر", "Not tested")}</span>
    : d.decision === "supported" ? <span className="badge bg-emerald-100 text-emerald-800">{tr("مدعومة إحصائياً", "Supported")}</span>
      : d.decision === "not_supported" ? <span className="badge bg-red-100 text-red-800">{tr("غير مدعومة", "Not supported")}</span> : <span className="badge bg-ink-100">{d.decision}</span>;
  return (
    <div>
      <PageHeader title={t("hypotheses")} subtitle={tr("الخطوات 8–10: حدّد الفرضيات ← اقتراح الاختبار ← التنفيذ بعد الموافقة ← القرار", "Steps 8–10: define hypotheses → test recommendation → run after approval → decision")} />
      <NeedsData>
        <div className="card mb-4 space-y-3">
          <h3 className="font-semibold">{tr("إضافة فرضية", "Add a hypothesis")}</h3>
          <div className="grid gap-3 sm:grid-cols-4">
            <div><label className="label">{tr("الرمز", "Code")}</label><input className="input" dir="ltr" placeholder={`H${hyps.length + 1}`} value={form.code || ""} onChange={(e) => setForm({ ...form, code: e.target.value })} /></div>
            <div className="sm:col-span-3"><label className="label">{tr("نص الفرضية (كما صاغها الباحث)", "Hypothesis text (as written by the researcher)")}</label><input className="input" dir="auto" value={form.text || ""} onChange={(e) => setForm({ ...form, text: e.target.value })} /></div>
            <div><label className="label">{tr("النوع", "Type")}</label><select className="input" value={form.purpose} onChange={(e) => setForm({ ...form, purpose: e.target.value })}>{PURPOSES.map((x) => <option key={x.v} value={x.v}>{lang === "ar" ? x.ar : x.en}</option>)}</select></div>
            <div><label className="label">{tr("المتغير التابع", "DV")}</label><VarSelect kind="any" value={form.dv} onChange={(v) => setForm({ ...form, dv: v })} /></div>
            <div><label className="label">{tr("الاتجاه", "Direction")}</label><select className="input" value={form.direction} onChange={(e) => setForm({ ...form, direction: e.target.value })}>
              <option value="two-sided">{tr("غير موجهة (ثنائية)", "Non-directional")}</option><option value="greater">{tr("موجهة: أكبر", "Directional: greater")}</option><option value="less">{tr("موجهة: أصغر", "Directional: less")}</option></select></div>
            <div><label className="label">α</label><input className="input" dir="ltr" type="number" step="0.01" value={form.alpha ?? project?.settings?.alpha ?? 0.05} onChange={(e) => setForm({ ...form, alpha: Number(e.target.value) })} /></div>
            <div className="sm:col-span-4"><label className="label">{tr("المتغير/المتغيرات المستقلة", "Independent variable(s)")}</label><VarMulti kind="any" value={form.ivs} onChange={(v) => setForm({ ...form, ivs: v })} /></div>
            {form.purpose === "mediation" && <div><label className="label">{tr("الوسيط", "Mediator")}</label><VarSelect kind="numeric" value={form.mediator} onChange={(v) => setForm({ ...form, mediator: v })} /></div>}
            {form.purpose === "moderation" && <div><label className="label">{tr("المعدِّل", "Moderator")}</label><VarSelect kind="numeric" value={form.moderator} onChange={(v) => setForm({ ...form, moderator: v })} /></div>}
          </div>
          <button className="btn-primary" disabled={!form.text || !form.dv} onClick={add}><Plus size={14} />{tr("إضافة", "Add")}</button>
          <ErrorBox error={error} />
        </div>
        {hyps.filter((h) => h.p_adjusted != null).length >= 2 && <Note>{tr("عند اختبار عدة فرضيات تُعرض قيم p المعدلة بطريقة هولم–بونفيروني للتحكم في معدل الخطأ العائلي.", "With several tested hypotheses, Holm–Bonferroni adjusted p-values control the family-wise error rate.")}</Note>}
        <div className="space-y-3">
          {hyps.map((h) => (
            <div key={h.id} className="card">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2"><b dir="ltr">{h.code}</b>{decisionBadge(h.decision)}
                    {h.p != null && <span className="text-xs text-ink-500" dir="ltr">p {fmtP(h.p)}{h.p_adjusted != null && ` · p(Holm) ${fmtP(h.p_adjusted)}`}</span>}</div>
                  <p className="mt-1" dir="auto">{h.text}</p>
                  <p className="text-xs text-ink-500" dir="ltr">{h.purpose} · DV: {h.dv} · IV: {(h.ivs || []).join(", ")} · α = {h.alpha}</p>
                  {h.decision && <p className="mt-1 text-sm">{h.decision[lang]}</p>}
                </div>
                <div className="flex gap-1">
                  <button className="btn-secondary" onClick={() => setActive(active === h.id ? null : h.id)}>{tr("اقتراح واختبار", "Recommend & test")}</button>
                  {h.analysis_id && <button className="btn-ghost" onClick={() => show(h.analysis_id)}>{tr("عرض النتيجة", "Show result")}</button>}
                  <button className="btn-ghost text-red-600" onClick={() => del(h.id)}><Trash2 size={14} /></button>
                </div>
              </div>
              {active === h.id && (
                <div className="mt-3 border-t border-ink-200 pt-3 dark:border-ink-800">
                  <TestAdvisor initial={{ purpose: h.purpose, dv: h.dv, ivs: h.ivs, mediator: h.mediator, moderator: h.moderator }}
                    onApprove={async (kind, params) => { const r = await api(`/api/projects/${projectId}/hypotheses/${h.id}/run`, { method: "POST", json: { kind, params } }); bump(); return r; }} />
                </div>
              )}
            </div>
          ))}
        </div>
        {shown && <div className="mt-4"><ResultView result={shown} /></div>}
      </NeedsData>
    </div>
  );
}
