import { useState } from "react";
import { CheckCircle2, CircleDot, Lightbulb, Play, XCircle } from "lucide-react";
import { api } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { useStore } from "../lib/store";
import { AnalysisRunner, FilterBar, SPECS, VarMulti, VarSelect } from "../components/Analysis";
import ResultView from "../components/ResultView";
import { ErrorBox, NeedsData, Note, PageHeader, Tabs } from "../components/ui";
import { DataView } from "./Cleaning";

function TabbedPage({ titleKey, subtitle, kinds, extra, filterBar = true }: { titleKey: any; subtitle?: string; kinds: string[]; extra?: { key: string; label: string; node: JSX.Element }[]; filterBar?: boolean }) {
  const { t, lang } = useI18n();
  const all = [...(extra || []).map((e) => ({ key: e.key, label: e.label })), ...kinds.map((k) => ({ key: k, label: lang === "ar" ? SPECS[k].ar : SPECS[k].en }))];
  const [tab, setTab] = useState(all[0].key);
  const ex = extra?.find((e) => e.key === tab);
  return (
    <div>
      <PageHeader title={t(titleKey)} subtitle={subtitle} />
      <NeedsData>
        {filterBar && <FilterBar />}
        <Tabs tabs={all} value={tab} onChange={setTab} />
        {ex ? ex.node : <AnalysisRunner key={tab} kind={tab} />}
      </NeedsData>
    </div>
  );
}

export function EDA() {
  const { tr } = useI18n();
  return <TabbedPage titleKey="eda" subtitle={tr("الخطوة 7: التوزيعات والارتباطات الأولية والقيم المتطرفة", "Step 7: distributions, preliminary correlations and outliers")}
    kinds={["eda", "normality", "descriptive"]} extra={[{ key: "auto", label: tr("نظرة عامة", "Overview"), node: <AnalysisRunner kind="eda" autoRun /> }, { key: "data", label: tr("البيانات", "Data"), node: <DataView /> }]} />;
}

export function Survey() {
  const { tr } = useI18n();
  return <TabbedPage titleKey="survey" subtitle={tr("تحليل بنود وأبعاد مقياس ليكرت والأسئلة المفتوحة", "Likert items, dimensions and open-ended questions")}
    kinds={["text"]} extra={[{ key: "likert", label: tr("تحليل مقياس ليكرت", "Likert analysis"), node: <AnalysisRunner kind="likert" autoRun /> }]} />;
}

export function Descriptive() {
  const { tr } = useI18n();
  return <TabbedPage titleKey="descriptive" subtitle={tr("المقاييس الوصفية والتكرارات وفترات الثقة لكل سؤال وبعد ومحور", "Descriptives, frequencies and CIs per item, dimension and axis")} kinds={["descriptive", "likert", "normality"]} />;
}

export function Reliability() {
  const { tr } = useI18n();
  return (
    <TabbedPage titleKey="reliability" subtitle={tr("لا يُعتمد على مؤشر واحد: الثبات والصدق حجة تراكمية", "No single index suffices: reliability and validity are a cumulative argument")}
      kinds={["reliability", "validity", "normality"]} filterBar={false} />
  );
}

export function Correlation() {
  const { tr } = useI18n();
  return <TabbedPage titleKey="correlation" subtitle={tr("الارتباط لا يعني السببية", "Correlation does not imply causation")} kinds={["correlation", "linear", "hierarchical", "logistic", "ordinal"]} />;
}

export function Factor() {
  const { tr } = useI18n();
  return <TabbedPage titleKey="factor" subtitle={tr("الاستكشافي (EFA/PCA) منفصل عن التوكيدي (CFA) المبني على نموذج محدد مسبقاً", "Exploratory (EFA/PCA) kept separate from confirmatory CFA on a pre-specified model")} kinds={["efa", "pca", "cfa"]} filterBar={false} />;
}

export function Advanced() {
  const { tr } = useI18n();
  return <TabbedPage titleKey="advanced" subtitle={tr("تُستخدم عندما تتوافق مع تصميم الدراسة", "Use when they match the study design")}
    kinds={["mediation", "moderation", "sem", "multigroup", "manova", "cluster", "discriminant", "chisquare", "fisher", "mcnemar", "survival"]} />;
}

export function Inferential() {
  const { tr } = useI18n();
  return <TabbedPage titleKey="inferential" subtitle={tr("محرك اختيار الاختبار يفحص الافتراضات ويقترح الاختبار المناسب ولا ينفذه إلا بموافقتك", "The test advisor checks assumptions, recommends a test, and runs it only after your approval")}
    kinds={["ttest_ind", "mannwhitney", "anova", "kruskal", "anova_twoway", "ttest_paired", "wilcoxon", "rm_anova", "friedman", "ttest_one"]}
    extra={[{ key: "advisor", label: tr("محرك اختيار الاختبار", "Test advisor"), node: <TestAdvisor /> }]} />;
}

export const PURPOSES: { v: string; ar: string; en: string }[] = [
  { v: "difference", ar: "مقارنة مجموعات (فروق)", en: "Compare groups (differences)" },
  { v: "relationship", ar: "العلاقة بين متغيرات (ارتباط)", en: "Relationship (correlation)" },
  { v: "prediction", ar: "التنبؤ بمتغير (انحدار)", en: "Prediction (regression)" },
  { v: "association", ar: "الارتباط بين متغيرين فئويين", en: "Association of categorical variables" },
  { v: "repeated", ar: "قياسات مترابطة لنفس المشاركين", en: "Related measures (same participants)" },
  { v: "mediation", ar: "الوساطة", en: "Mediation" },
  { v: "moderation", ar: "التعديل (التفاعل)", en: "Moderation" },
  { v: "multivariate", ar: "عدة متغيرات تابعة (MANOVA)", en: "Several DVs (MANOVA)" },
];

/** Shared by the inferential page and hypothesis testing. onApprove runs the chosen test. */
export function TestAdvisor({ initial, onApprove }: { initial?: any; onApprove?: (kind: string, params: any) => Promise<any> }) {
  const { tr, lang } = useI18n();
  const { projectId, filters, bump } = useStore();
  const [req, setReq] = useState<any>(initial || { purpose: "difference", ivs: [] });
  const [rec, setRec] = useState<any>(null);
  const [res, setRes] = useState<any>(null);
  const [error, setError] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const ask = async () => {
    setError(null); setRes(null);
    try { setRec(await api(`/api/projects/${projectId}/recommend`, { method: "POST", json: { ...req, filters } })); } catch (e) { setError(e); setRec(null); }
  };
  const approve = async (r: any) => {
    setBusy(true); setError(null);
    try {
      const out = onApprove ? await onApprove(r.analysis, r.params)
        : await api(`/api/projects/${projectId}/run`, { method: "POST", json: { kind: r.analysis, params: r.params, filters, save: true } });
      setRes(out); bump();
    } catch (e) { setError(e); } finally { setBusy(false); }
  };
  const p = req.purpose;
  const dvKind = p === "association" ? "categorical" : p === "prediction" ? "any" : "numeric";
  const ivKind = p === "difference" ? "categorical" : p === "association" ? "categorical" : p === "relationship" || p === "repeated" || p === "mediation" || p === "moderation" ? "numeric" : "any";
  return (
    <div className="space-y-4">
      <div className="card space-y-3">
        <h3 className="flex items-center gap-2 font-semibold"><Lightbulb size={16} />{tr("محرك اختيار الاختبار الإحصائي", "Statistical test advisor")}</h3>
        <div className="grid gap-3 sm:grid-cols-2">
          <div><label className="label">{tr("طبيعة السؤال/الفرضية", "Question / hypothesis type")}</label>
            <select className="input" value={p} onChange={(e) => { setReq({ ...req, purpose: e.target.value }); setRec(null); }}>{PURPOSES.map((x) => <option key={x.v} value={x.v}>{lang === "ar" ? x.ar : x.en}</option>)}</select></div>
          {p !== "multivariate" && <div><label className="label">{p === "repeated" ? tr("القياس الأول", "First measure") : tr("المتغير التابع", "Dependent variable")}</label><VarSelect kind={dvKind as any} value={req.dv} onChange={(v) => setReq({ ...req, dv: v })} /></div>}
          {p === "multivariate" && <div className="sm:col-span-2"><label className="label">{tr("المتغيرات التابعة", "Dependent variables")}</label><VarMulti kind="numeric" value={req.dvs || []} onChange={(v) => setReq({ ...req, dvs: v })} /></div>}
          <div className="sm:col-span-2"><label className="label">{p === "repeated" ? tr("القياسات الأخرى", "Other measures") : p === "difference" || p === "multivariate" ? tr("متغير/متغيرا التجميع", "Grouping variable(s)") : tr("المتغير/المتغيرات المستقلة", "Independent variable(s)")}</label>
            <VarMulti kind={ivKind as any} value={req.ivs || []} onChange={(v) => setReq({ ...req, ivs: v })} /></div>
          {p === "mediation" && <div><label className="label">{tr("المتغير الوسيط", "Mediator")}</label><VarSelect kind="numeric" value={req.mediator} onChange={(v) => setReq({ ...req, mediator: v })} /></div>}
          {p === "moderation" && <div><label className="label">{tr("المتغير المعدِّل", "Moderator")}</label><VarSelect kind="numeric" value={req.moderator} onChange={(v) => setReq({ ...req, moderator: v })} /></div>}
        </div>
        <button className="btn-primary" onClick={ask}><Lightbulb size={14} />{tr("اقترح الاختبار المناسب", "Recommend a test")}</button>
        <ErrorBox error={error} />
      </div>
      {rec && (
        <div className="card space-y-3">
          <div className="grid gap-2 text-sm sm:grid-cols-2">
            <div><b>{tr("المتغير التابع", "DV")}:</b> {rec.identified.dv || "—"} <span className="text-ink-500">({rec.identified.dv_level})</span></div>
            <div><b>{tr("المستقل", "IV")}:</b> {(rec.identified.ivs || []).map((v: string) => `${v} (${rec.identified.iv_levels?.[v]})`).join("، ") || "—"}</div>
            {rec.identified.groups != null && <div><b>{tr("عدد المجموعات", "Groups")}:</b> {rec.identified.groups} <span className="text-ink-500" dir="ltr">{JSON.stringify(rec.identified.group_sizes)}</span></div>}
            {rec.identified.n != null && <div><b>n:</b> {rec.identified.n}</div>}
          </div>
          {rec.checks.length > 0 && (
            <ul className="space-y-1 text-sm">
              {rec.checks.map((c: any, i: number) => (
                <li key={i} className="flex gap-2">
                  {c.met === true ? <CheckCircle2 size={16} className="mt-1 shrink-0 text-emerald-600" /> : c.met === false ? <XCircle size={16} className="mt-1 shrink-0 text-red-600" /> : <CircleDot size={16} className="mt-1 shrink-0 text-ink-400" />}
                  <span><b>{lang === "ar" ? c.name_ar : c.name_en}:</b> {lang === "ar" ? c.detail_ar : c.detail_en}</span>
                </li>))}
            </ul>
          )}
          <div className="rounded-lg border-2 border-brand-500 p-3">
            <div className="text-xs font-semibold text-brand-700 dark:text-brand-300">{tr("الاختبار المقترح", "Recommended test")}</div>
            <div className="text-lg font-bold">{lang === "ar" ? rec.recommended.title_ar : rec.recommended.title_en}</div>
            <p className="text-sm">{lang === "ar" ? rec.recommended.reason_ar : rec.recommended.reason_en}</p>
            <button className="btn-primary mt-2" disabled={busy} onClick={() => approve(rec.recommended)}><Play size={14} className="icon-dir" />{tr("موافقة وتنفيذ", "Approve & run")}</button>
          </div>
          {rec.alternatives.length > 0 && (
            <div>
              <div className="mb-1 text-xs font-semibold text-ink-500">{tr("بدائل", "Alternatives")}</div>
              <div className="flex flex-wrap gap-2">
                {rec.alternatives.map((a: any, i: number) => (
                  <button key={i} className="btn-secondary" disabled={busy} title={lang === "ar" ? a.reason_ar : a.reason_en} onClick={() => approve(a)}>{lang === "ar" ? a.title_ar : a.title_en}</button>
                ))}
              </div>
            </div>
          )}
          <Note>{tr("لا يخترع المحرك فرضيات أو نتائج: يقترح فقط بناءً على مستوى القياس وحجم العينة والافتراضات المفحوصة على بياناتك.", "The advisor never invents hypotheses or results: it recommends based on measurement level, sample size and assumptions checked on your data.")}</Note>
        </div>
      )}
      {res && <ResultView result={res.result || res} />}
    </div>
  );
}
