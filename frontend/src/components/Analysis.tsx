import { useEffect, useMemo, useState } from "react";
import { Filter, Play, X } from "lucide-react";
import { api } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { Filters, useStore, Variable } from "../lib/store";
import ResultView from "./ResultView";
import { ErrorBox } from "./ui";

type VarKind = "numeric" | "categorical" | "any" | "likert" | "text" | "dimension";
export type Field =
  | { key: string; type: "var"; kind: VarKind; ar: string; en: string; optional?: boolean }
  | { key: string; type: "vars"; kind: VarKind; ar: string; en: string; optional?: boolean }
  | { key: string; type: "select"; options: { v: string; ar: string; en: string }[]; ar: string; en: string; def?: string }
  | { key: string; type: "number"; ar: string; en: string; def?: number; optional?: boolean }
  | { key: string; type: "text"; ar: string; en: string; textarea?: boolean; optional?: boolean; placeholder?: string };

export type Spec = { kind: string; ar: string; en: string; fields: Field[]; descAr?: string; descEn?: string; toParams?: (v: any) => any };

const ALT = { key: "alternative", type: "select" as const, ar: "اتجاه الفرضية", en: "Alternative", def: "two-sided",
  options: [{ v: "two-sided", ar: "ثنائي الاتجاه", en: "Two-sided" }, { v: "greater", ar: "أكبر (أحادي)", en: "Greater" }, { v: "less", ar: "أصغر (أحادي)", en: "Less" }] };
const DV = { key: "dv", type: "var" as const, kind: "numeric" as VarKind, ar: "المتغير التابع", en: "Dependent variable" };
const GROUP = { key: "group", type: "var" as const, kind: "categorical" as VarKind, ar: "متغير التجميع (المستقل)", en: "Grouping variable" };

export const SPECS: Record<string, Spec> = {
  descriptive: { kind: "descriptive", ar: "الإحصاء الوصفي", en: "Descriptive statistics", fields: [
    { key: "variables", type: "vars", kind: "any", ar: "المتغيرات", en: "Variables" },
    { key: "group_by", type: "var", kind: "categorical", ar: "حسب المجموعة", en: "Split by group", optional: true },
    { key: "confidence", type: "number", ar: "مستوى الثقة", en: "Confidence level", def: 0.95 }] },
  likert: { kind: "likert", ar: "تحليل مقياس ليكرت", en: "Likert analysis", fields: [{ key: "dimension", type: "var", kind: "dimension", ar: "البعد", en: "Dimension", optional: true }] },
  normality: { kind: "normality", ar: "اختبارات التوزيع الطبيعي", en: "Normality tests", fields: [
    { key: "variables", type: "vars", kind: "numeric", ar: "المتغيرات", en: "Variables" },
    { key: "group_by", type: "var", kind: "categorical", ar: "حسب المجموعة", en: "By group", optional: true }] },
  reliability: { kind: "reliability", ar: "الثبات (ألفا، أوميغا، البند–الكلي)", en: "Reliability (α, ω, item-total)", fields: [
    { key: "dimensions", type: "vars", kind: "dimension", ar: "الأبعاد (فارغ = الكل)", en: "Dimensions (empty = all)", optional: true },
    { key: "items", type: "vars", kind: "likert", ar: "أو بنود مخصصة", en: "or custom items", optional: true }] },
  validity: { kind: "validity", ar: "الصدق البنائي (CR، AVE، فورنل–لاركر، HTMT)", en: "Construct validity (CR, AVE, Fornell–Larcker, HTMT)", fields: [] },
  ttest_ind: { kind: "ttest_ind", ar: "اختبار (ت) لعينتين مستقلتين", en: "Independent-samples t-test", fields: [DV, GROUP, ALT] },
  mannwhitney: { kind: "mannwhitney", ar: "مان–ويتني", en: "Mann–Whitney U", fields: [DV, GROUP, ALT] },
  anova: { kind: "anova", ar: "تحليل التباين الأحادي / ويلش", en: "One-way / Welch ANOVA", fields: [DV, GROUP,
    { key: "posthoc", type: "select", ar: "المقارنات البعدية", en: "Post hoc", def: "", options: [{ v: "", ar: "تلقائي (حسب ليفين)", en: "Auto (by Levene)" },
      { v: "tukey", ar: "توكي HSD", en: "Tukey HSD" }, { v: "games_howell", ar: "جيمس–هاول", en: "Games–Howell" }, { v: "bonferroni", ar: "بونفيروني", en: "Bonferroni" }] }] },
  kruskal: { kind: "kruskal", ar: "كروسكال–واليس", en: "Kruskal–Wallis", fields: [DV, GROUP] },
  anova_twoway: { kind: "anova_twoway", ar: "تحليل التباين الثنائي", en: "Two-way ANOVA", fields: [DV,
    { key: "factor_a", type: "var", kind: "categorical", ar: "العامل الأول", en: "Factor A" }, { key: "factor_b", type: "var", kind: "categorical", ar: "العامل الثاني", en: "Factor B" }] },
  ttest_paired: { kind: "ttest_paired", ar: "(ت) للعينات المترابطة", en: "Paired t-test", fields: [
    { key: "var1", type: "var", kind: "numeric", ar: "القياس الأول", en: "Measure 1" }, { key: "var2", type: "var", kind: "numeric", ar: "القياس الثاني", en: "Measure 2" }, ALT] },
  wilcoxon: { kind: "wilcoxon", ar: "ويلكوكسون", en: "Wilcoxon signed-rank", fields: [
    { key: "var1", type: "var", kind: "numeric", ar: "القياس الأول", en: "Measure 1" }, { key: "var2", type: "var", kind: "numeric", ar: "القياس الثاني", en: "Measure 2" }] },
  rm_anova: { kind: "rm_anova", ar: "تحليل التباين للقياسات المتكررة", en: "Repeated-measures ANOVA", fields: [{ key: "variables", type: "vars", kind: "numeric", ar: "القياسات", en: "Measures" }] },
  friedman: { kind: "friedman", ar: "فريدمان", en: "Friedman", fields: [{ key: "variables", type: "vars", kind: "numeric", ar: "القياسات", en: "Measures" }] },
  ttest_one: { kind: "ttest_one", ar: "(ت) لعينة واحدة", en: "One-sample t-test", fields: [{ key: "variable", type: "var", kind: "numeric", ar: "المتغير", en: "Variable" },
    { key: "test_value", type: "number", ar: "القيمة المختبرة (فارغ = منتصف المقياس)", en: "Test value (empty = scale midpoint)", optional: true }, ALT] },
  correlation: { kind: "correlation", ar: "تحليل الارتباط", en: "Correlation", fields: [
    { key: "variables", type: "vars", kind: "numeric", ar: "المتغيرات", en: "Variables" },
    { key: "method", type: "select", ar: "المعامل", en: "Coefficient", def: "pearson", options: [{ v: "pearson", ar: "بيرسون", en: "Pearson" }, { v: "spearman", ar: "سبيرمان", en: "Spearman" }, { v: "kendall", ar: "كندال τb", en: "Kendall τb" }] },
    { key: "adjust", type: "select", ar: "تصحيح تعدد الاختبارات", en: "Multiple-testing correction", def: "none", options: [{ v: "none", ar: "بدون", en: "None" }, { v: "holm", ar: "هولم", en: "Holm" }, { v: "bonferroni", ar: "بونفيروني", en: "Bonferroni" }, { v: "fdr", ar: "FDR (بنجاميني–هوخبرغ)", en: "FDR (BH)" }] }] },
  linear: { kind: "linear", ar: "الانحدار الخطي (بسيط/متعدد/متعدد الحدود)", en: "Linear regression (simple/multiple/polynomial)", fields: [DV,
    { key: "ivs", type: "vars", kind: "any", ar: "المتغيرات المستقلة", en: "Predictors" }, { key: "polynomial", type: "number", ar: "درجة كثيرة الحدود (1 = خطي)", en: "Polynomial degree (1 = linear)", def: 1 }] },
  hierarchical: { kind: "hierarchical", ar: "الانحدار الهرمي", en: "Hierarchical regression", fields: [DV,
    { key: "b1", type: "vars", kind: "any", ar: "الكتلة 1", en: "Block 1" }, { key: "b2", type: "vars", kind: "any", ar: "الكتلة 2", en: "Block 2" }, { key: "b3", type: "vars", kind: "any", ar: "الكتلة 3", en: "Block 3", optional: true }],
    toParams: (v) => ({ dv: v.dv, blocks: [v.b1, v.b2, v.b3].filter((b) => b && b.length) }) },
  logistic: { kind: "logistic", ar: "الانحدار اللوجستي الثنائي", en: "Binary logistic regression", fields: [
    { key: "dv", type: "var", kind: "categorical", ar: "المتغير التابع (ثنائي)", en: "Binary DV" }, { key: "ivs", type: "vars", kind: "any", ar: "المتنبئات", en: "Predictors" },
    { key: "event", type: "text", ar: "فئة الحدث (اختياري)", en: "Event category (optional)", optional: true }] },
  ordinal: { kind: "ordinal", ar: "الانحدار اللوجستي الرتبي", en: "Ordinal logistic regression", fields: [
    { key: "dv", type: "var", kind: "any", ar: "المتغير التابع الرتبي", en: "Ordinal DV" }, { key: "ivs", type: "vars", kind: "any", ar: "المتنبئات", en: "Predictors" }] },
  efa: { kind: "efa", ar: "التحليل العاملي الاستكشافي", en: "Exploratory factor analysis", fields: [
    { key: "items", type: "vars", kind: "likert", ar: "البنود (فارغ = كل بنود ليكرت)", en: "Items (empty = all Likert items)", optional: true },
    { key: "n_factors", type: "number", ar: "عدد العوامل (فارغ = التحليل الموازي)", en: "Factors (empty = parallel analysis)", optional: true },
    { key: "method", type: "select", ar: "طريقة الاستخراج", en: "Extraction", def: "minres", options: [{ v: "minres", ar: "أقل البواقي", en: "MinRes" }, { v: "ml", ar: "الاحتمال الأقصى", en: "Maximum likelihood" }, { v: "principal", ar: "المحاور الرئيسية", en: "Principal axis" }] },
    { key: "rotation", type: "select", ar: "التدوير", en: "Rotation", def: "oblimin", options: [{ v: "oblimin", ar: "Oblimin (مائل)", en: "Oblimin" }, { v: "promax", ar: "Promax (مائل)", en: "Promax" }, { v: "varimax", ar: "Varimax (متعامد)", en: "Varimax" }, { v: "", ar: "بدون", en: "None" }] }] },
  pca: { kind: "pca", ar: "تحليل المكونات الرئيسية", en: "Principal component analysis", fields: [
    { key: "items", type: "vars", kind: "likert", ar: "البنود", en: "Items", optional: true }, { key: "n_components", type: "number", ar: "عدد المكونات", en: "Components", optional: true },
    { key: "rotation", type: "select", ar: "التدوير", en: "Rotation", def: "varimax", options: [{ v: "varimax", ar: "Varimax", en: "Varimax" }, { v: "", ar: "بدون", en: "None" }] }] },
  cfa: { kind: "cfa", ar: "التحليل العاملي التوكيدي", en: "Confirmatory factor analysis",
    descAr: "يُبنى النموذج من الأبعاد المؤكدة في قاموس البيانات، أو من صيغة نموذج تدخلها بنفسك (lavaan).", descEn: "The model is built from the confirmed dimensions, or from lavaan-style syntax you enter.",
    fields: [{ key: "dimensions", type: "vars", kind: "dimension", ar: "الأبعاد (فارغ = الكل)", en: "Dimensions (empty = all)", optional: true },
      { key: "syntax", type: "text", textarea: true, ar: "صيغة نموذج مخصصة (اختياري)", en: "Custom model syntax (optional)", optional: true, placeholder: "F1 =~ Q1 + Q2 + Q3\nF2 =~ Q4 + Q5 + Q6" }] },
  sem: { kind: "sem", ar: "نمذجة المعادلات البنائية", en: "Structural equation modeling", fields: [
    { key: "syntax", type: "text", textarea: true, ar: "صيغة النموذج (قياس =~ وبنائي ~)", en: "Model syntax (=~ measurement, ~ structural)", placeholder: "SQ =~ SQ1 + SQ2 + SQ3\nSAT =~ SAT1 + SAT2 + SAT3\nSAT ~ SQ" }] },
  multigroup: { kind: "multigroup", ar: "التحليل متعدد المجموعات", en: "Multi-group analysis", fields: [GROUP, { key: "dimensions", type: "vars", kind: "dimension", ar: "الأبعاد", en: "Dimensions", optional: true }] },
  mediation: { kind: "mediation", ar: "تحليل الوساطة", en: "Mediation", fields: [
    { key: "x", type: "var", kind: "numeric", ar: "المستقل X", en: "Predictor X" }, { key: "mediator", type: "var", kind: "numeric", ar: "الوسيط M", en: "Mediator M" },
    { key: "y", type: "var", kind: "numeric", ar: "التابع Y", en: "Outcome Y" }, { key: "n_boot", type: "number", ar: "عدد عينات الإقلاع", en: "Bootstrap samples", def: 5000 }] },
  moderation: { kind: "moderation", ar: "تحليل التعديل", en: "Moderation", fields: [
    { key: "x", type: "var", kind: "numeric", ar: "المستقل X", en: "Predictor X" }, { key: "moderator", type: "var", kind: "numeric", ar: "المعدِّل W", en: "Moderator W" },
    { key: "y", type: "var", kind: "numeric", ar: "التابع Y", en: "Outcome Y" }] },
  manova: { kind: "manova", ar: "تحليل التباين المتعدد", en: "MANOVA", fields: [{ key: "dvs", type: "vars", kind: "numeric", ar: "المتغيرات التابعة", en: "Dependent variables" }, GROUP] },
  cluster: { kind: "cluster", ar: "التحليل العنقودي", en: "Cluster analysis", fields: [{ key: "variables", type: "vars", kind: "numeric", ar: "المتغيرات", en: "Variables" },
    { key: "k", type: "number", ar: "عدد العناقيد (فارغ = الصورة الظلية)", en: "k (empty = silhouette)", optional: true },
    { key: "method", type: "select", ar: "الطريقة", en: "Method", def: "kmeans", options: [{ v: "kmeans", ar: "K-means", en: "K-means" }, { v: "ward", ar: "هرمي (Ward)", en: "Hierarchical (Ward)" }] }] },
  discriminant: { kind: "discriminant", ar: "التحليل التمييزي", en: "Discriminant analysis", fields: [GROUP, { key: "predictors", type: "vars", kind: "numeric", ar: "المتنبئات", en: "Predictors" }] },
  chisquare: { kind: "chisquare", ar: "كاي تربيع", en: "Chi-square", fields: [{ key: "var1", type: "var", kind: "categorical", ar: "المتغير الأول", en: "Variable 1" }, { key: "var2", type: "var", kind: "categorical", ar: "المتغير الثاني", en: "Variable 2" }] },
  fisher: { kind: "fisher", ar: "فيشر الدقيق", en: "Fisher's exact", fields: [{ key: "var1", type: "var", kind: "categorical", ar: "المتغير الأول", en: "Variable 1" }, { key: "var2", type: "var", kind: "categorical", ar: "المتغير الثاني", en: "Variable 2" }] },
  mcnemar: { kind: "mcnemar", ar: "ماكنمار", en: "McNemar", fields: [{ key: "var1", type: "var", kind: "categorical", ar: "القياس الأول", en: "Measure 1" }, { key: "var2", type: "var", kind: "categorical", ar: "القياس الثاني", en: "Measure 2" }] },
  survival: { kind: "survival", ar: "تحليل البقاء", en: "Survival analysis", fields: [{ key: "time", type: "var", kind: "numeric", ar: "الزمن", en: "Time" },
    { key: "event", type: "var", kind: "any", ar: "الحدث (0/1)", en: "Event (0/1)" }, { key: "group", type: "var", kind: "categorical", ar: "المجموعة", en: "Group", optional: true }] },
  text: { kind: "text", ar: "تحليل الأسئلة المفتوحة", en: "Open-ended responses", fields: [{ key: "variable", type: "var", kind: "text", ar: "السؤال المفتوح", en: "Open question" },
    { key: "n_topics", type: "number", ar: "عدد الموضوعات (فارغ = تلقائي)", en: "Topics (empty = auto)", optional: true }] },
  eda: { kind: "eda", ar: "التحليل الاستكشافي", en: "EDA", fields: [{ key: "variables", type: "vars", kind: "numeric", ar: "المتغيرات (فارغ = الدرجات المركبة)", en: "Variables (empty = composites)", optional: true },
    { key: "group_by", type: "var", kind: "categorical", ar: "حسب المجموعة", en: "By group", optional: true }] },
};

export function useVarOptions(kind: VarKind) {
  const { variables, dictionary } = useStore();
  return useMemo(() => {
    if (kind === "dimension") return (dictionary?.dimensions || []).map((d: any) => ({ v: d.name, label: d.label || d.name }));
    const ok = (v: Variable) => {
      if (v.role === "exclude") return false;
      if (kind === "numeric") return v.numeric;
      if (kind === "categorical") return !v.numeric && v.dtype !== "text" && v.role !== "id" && v.n_unique <= 30 || (v.numeric && v.n_unique <= 10 && !v.composite);
      if (kind === "likert") return v.is_likert;
      if (kind === "text") return v.dtype === "text";
      return v.role !== "id";
    };
    return variables.filter(ok).map((v) => ({ v: v.name, label: v.composite ? `${v.name} ★` : v.label !== v.name ? `${v.name} — ${v.label}` : v.name }));
  }, [variables, dictionary, kind]);
}

export function VarSelect({ kind, value, onChange, optional }: { kind: VarKind; value: string; onChange: (v: string) => void; optional?: boolean }) {
  const opts = useVarOptions(kind);
  const { t } = useI18n();
  return (
    <select className="input" value={value || ""} onChange={(e) => onChange(e.target.value)}>
      <option value="">{t("select")}{optional ? " " + t("optional") : ""}</option>
      {opts.map((o: any) => <option key={o.v} value={o.v}>{o.label}</option>)}
    </select>
  );
}

export function VarMulti({ kind, value, onChange }: { kind: VarKind; value: string[]; onChange: (v: string[]) => void }) {
  const opts = useVarOptions(kind);
  const { tr } = useI18n();
  const sel = new Set(value || []);
  return (
    <div>
      <div className="flex max-h-36 flex-wrap gap-1 overflow-auto rounded-lg border border-ink-300 p-1.5 dark:border-ink-700">
        {opts.length === 0 && <span className="text-xs text-ink-400">{tr("لا توجد متغيرات مناسبة", "No suitable variables")}</span>}
        {opts.map((o: any) => (
          <button type="button" key={o.v} onClick={() => onChange(sel.has(o.v) ? value.filter((x) => x !== o.v) : [...(value || []), o.v])}
            className={`badge cursor-pointer border ${sel.has(o.v) ? "border-brand-600 bg-brand-600 text-white" : "border-ink-300 bg-white text-ink-700 dark:border-ink-600 dark:bg-ink-800 dark:text-ink-200"}`}>
            {o.label}
          </button>
        ))}
      </div>
      {opts.length > 1 && <div className="mt-1 flex gap-2 text-xs">
        <button type="button" className="text-brand-700 dark:text-brand-300" onClick={() => onChange(opts.map((o: any) => o.v))}>{tr("الكل", "All")}</button>
        <button type="button" className="text-ink-500" onClick={() => onChange([])}>{tr("لا شيء", "None")}</button>
      </div>}
    </div>
  );
}

export function FieldInput({ f, value, onChange }: { f: Field; value: any; onChange: (v: any) => void }) {
  const { lang } = useI18n();
  const label = lang === "ar" ? f.ar : f.en;
  return (
    <div className={f.type === "vars" || (f.type === "text" && (f as any).textarea) ? "sm:col-span-2" : ""}>
      <label className="label">{label}</label>
      {f.type === "var" && <VarSelect kind={f.kind} value={value} onChange={onChange} optional={f.optional} />}
      {f.type === "vars" && <VarMulti kind={f.kind} value={value || []} onChange={onChange} />}
      {f.type === "select" && (
        <select className="input" value={value ?? f.def ?? ""} onChange={(e) => onChange(e.target.value)}>
          {f.options.map((o) => <option key={o.v} value={o.v}>{lang === "ar" ? o.ar : o.en}</option>)}
        </select>
      )}
      {f.type === "number" && <input className="input" type="number" step="any" dir="ltr" value={value ?? ""} placeholder={f.def != null ? String(f.def) : ""}
        onChange={(e) => onChange(e.target.value === "" ? undefined : Number(e.target.value))} />}
      {f.type === "text" && (f.textarea
        ? <textarea className="input h-28 font-mono" dir="ltr" value={value || ""} placeholder={f.placeholder} onChange={(e) => onChange(e.target.value)} />
        : <input className="input" dir="auto" value={value || ""} onChange={(e) => onChange(e.target.value)} />)}
    </div>
  );
}

export function cleanParams(spec: Spec, values: any) {
  const out: any = {};
  for (const f of spec.fields) {
    let v = values[f.key];
    if (v === undefined && "def" in f && f.def !== undefined) v = f.def;
    if (v === "" || v === undefined || (Array.isArray(v) && v.length === 0)) continue;
    out[f.key] = v;
  }
  if ((spec.kind === "efa" || spec.kind === "pca") && values.rotation === "") out.rotation = null;
  return spec.toParams ? spec.toParams(out) : out;
}

export function useRun() {
  const { projectId, filters, bump } = useStore();
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const run = async (kind: string, params: any, save = true, useFilters = true) => {
    setBusy(true); setError(null);
    try {
      const r = await api(`/api/projects/${projectId}/run`, { method: "POST", json: { kind, params, filters: useFilters ? filters : {}, save } });
      setResult(r);
      if (save) bump();
      return r;
    } catch (e) { setError(e); setResult(null); } finally { setBusy(false); }
  };
  return { result, error, busy, run, setResult };
}

export function AnalysisRunner({ kind, initial, autoRun }: { kind: string; initial?: any; autoRun?: boolean }) {
  const spec = SPECS[kind];
  const { lang, t } = useI18n();
  const [values, setValues] = useState<any>(initial || {});
  const { result, error, busy, run } = useRun();
  const { filters } = useStore();
  useEffect(() => { if (autoRun) run(kind, cleanParams(spec, values), false); /* eslint-disable-next-line */ }, [autoRun, JSON.stringify(filters)]);
  return (
    <div className="space-y-4">
      <div className="card">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h3 className="font-semibold">{lang === "ar" ? spec.ar : spec.en}</h3>
          <ActiveFilters />
        </div>
        {(spec.descAr || spec.descEn) && <p className="mb-2 text-sm text-ink-500">{lang === "ar" ? spec.descAr : spec.descEn}</p>}
        <div className="grid gap-3 sm:grid-cols-2">
          {spec.fields.map((f) => <FieldInput key={f.key} f={f} value={values[f.key]} onChange={(v) => setValues({ ...values, [f.key]: v })} />)}
        </div>
        <div className="mt-3">
          <button className="btn-primary" disabled={busy} onClick={() => run(kind, cleanParams(spec, values))}><Play size={14} className="icon-dir" />{busy ? t("running") : t("run")}</button>
        </div>
        <ErrorBox error={error} />
      </div>
      <ResultView result={result} />
    </div>
  );
}

export function ActiveFilters() {
  const { filters, setFilters } = useStore();
  const { tr } = useI18n();
  const keys = Object.keys(filters).filter((k) => { const f: any = filters[k]; return Array.isArray(f) ? f.length : f && (f.min != null || f.max != null); });
  if (!keys.length) return null;
  return (
    <span className="badge gap-1 bg-violet-100 text-violet-800 dark:bg-violet-900 dark:text-violet-100">
      <Filter size={12} />{tr("مرشحات نشطة", "Active filters")}: {keys.join("، ")}
      <button onClick={() => setFilters({})}><X size={12} /></button>
    </span>
  );
}

/** Demographic filter bar: every analysis and chart updates when filters change. */
export function FilterBar() {
  const { variables, filters, setFilters } = useStore();
  const { t, tr } = useI18n();
  const demo = variables.filter((v) => v.role === "demographic" && v.values && v.values.length <= 15);
  const numericDemo = variables.filter((v) => v.role === "demographic" && v.numeric && !v.values);
  if (!demo.length && !numericDemo.length) return null;
  const toggle = (name: string, val: string) => {
    const cur = (filters[name] as string[]) || [];
    const next = cur.includes(val) ? cur.filter((x) => x !== val) : [...cur, val];
    const f = { ...filters, [name]: next };
    if (!next.length) delete (f as any)[name];
    setFilters(f);
  };
  return (
    <div className="card mb-4">
      <div className="mb-2 flex items-center justify-between">
        <span className="flex items-center gap-1 text-sm font-semibold"><Filter size={14} />{t("filters")} <span className="text-xs font-normal text-ink-400">{tr("(تُطبَّق على جميع الرسوم والتحليلات)", "(applied to all charts and analyses)")}</span></span>
        {Object.keys(filters).length > 0 && <button className="btn-ghost text-xs" onClick={() => setFilters({})}>{t("clear")}</button>}
      </div>
      <div className="flex flex-wrap gap-x-6 gap-y-2">
        {demo.map((v) => (
          <div key={v.name} className="flex flex-wrap items-center gap-1">
            <span className="text-xs font-medium text-ink-500">{v.label}:</span>
            {v.values!.map((val) => {
              const on = ((filters[v.name] as string[]) || []).includes(val);
              return <button key={val} onClick={() => toggle(v.name, val)} className={`badge border ${on ? "border-violet-600 bg-violet-600 text-white" : "border-ink-300 dark:border-ink-600"}`}>{val}</button>;
            })}
          </div>
        ))}
        {numericDemo.map((v) => {
          const f: any = filters[v.name] || {};
          const set = (k: "min" | "max", val: string) => {
            const nf: any = { ...f, [k]: val === "" ? undefined : Number(val) };
            const all = { ...filters, [v.name]: nf };
            if (nf.min == null && nf.max == null) delete (all as any)[v.name];
            setFilters(all);
          };
          return (
            <div key={v.name} className="flex items-center gap-1 text-xs">
              <span className="font-medium text-ink-500">{v.label}:</span>
              <input className="input w-20 py-0.5" dir="ltr" type="number" placeholder="min" value={f.min ?? ""} onChange={(e) => set("min", e.target.value)} />
              <span>–</span>
              <input className="input w-20 py-0.5" dir="ltr" type="number" placeholder="max" value={f.max ?? ""} onChange={(e) => set("max", e.target.value)} />
            </div>
          );
        })}
      </div>
    </div>
  );
}

export type { Filters };
