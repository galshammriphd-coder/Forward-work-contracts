import { ReactNode } from "react";
import { AlertTriangle, FlaskConical, Info } from "lucide-react";
import { Link } from "react-router-dom";
import { ApiError } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { useStore } from "../lib/store";

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="h-title">{title}</h1>
        {subtitle && <p className="text-sm text-ink-500 dark:text-ink-400">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function ErrorBox({ error }: { error: any }) {
  const { lang } = useI18n();
  if (!error) return null;
  const msg = error instanceof ApiError ? (lang === "ar" ? error.ar : error.message) : String(error?.message || error);
  return (
    <div className="my-2 flex items-start gap-2 rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
      <AlertTriangle size={16} className="mt-1 shrink-0" />
      <span>{msg}</span>
    </div>
  );
}

export function Note({ children, tone = "info" }: { children: ReactNode; tone?: "info" | "warn" }) {
  const cls = tone === "warn"
    ? "border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100"
    : "border-brand-200 bg-brand-50 text-brand-900 dark:border-brand-900 dark:bg-brand-950/40 dark:text-brand-100";
  return (
    <div className={`my-2 flex items-start gap-2 rounded-lg border p-3 text-sm ${cls}`}>
      {tone === "warn" ? <AlertTriangle size={16} className="mt-1 shrink-0" /> : <Info size={16} className="mt-1 shrink-0" />}
      <div>{children}</div>
    </div>
  );
}

export function SyntheticBanner() {
  const { project } = useStore();
  const { lang } = useI18n();
  if (!project?.is_synthetic) return null;
  return (
    <div className="mb-4 flex items-center gap-2 rounded-lg border-2 border-amber-400 bg-amber-50 px-3 py-2 text-sm font-semibold text-amber-900 dark:bg-amber-950 dark:text-amber-100">
      <FlaskConical size={18} className="shrink-0" />
      {project.synthetic_notice?.[lang]}
    </div>
  );
}

/** Guard: requires a selected project with data (and optionally a confirmed dictionary). */
export function NeedsData({ children }: { children: ReactNode }) {
  const { project } = useStore();
  const { t, tr } = useI18n();
  if (!project) return <div className="card text-center text-ink-500">{t("noProject")} <Link className="text-brand-700 underline dark:text-brand-300" to="/projects">{t("projects")}</Link></div>;
  if (!project.dataset) return <div className="card text-center text-ink-500">{t("noData")} <Link className="text-brand-700 underline dark:text-brand-300" to="/upload">{t("goUpload")}</Link></div>;
  return (
    <>
      <SyntheticBanner />
      {!project.dictionary_confirmed && (
        <Note tone="warn">
          {tr("لم يؤكد الباحث قاموس البيانات بعد (الأنواع، الأبعاد، البنود العكسية). يُنصح بمراجعته وتأكيده قبل التحليل.",
            "The data dictionary (types, dimensions, reverse items) has not been confirmed yet. Review and confirm it before analysing.")}{" "}
          <Link className="underline" to="/upload">{tr("مراجعة القاموس", "Review dictionary")}</Link>
        </Note>
      )}
      {children}
    </>
  );
}

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: { key: T; label: string }[]; value: T; onChange: (k: T) => void }) {
  return (
    <div className="mb-4 flex gap-1 overflow-x-auto border-b border-ink-200 dark:border-ink-800">
      {tabs.map((t) => (
        <button key={t.key} onClick={() => onChange(t.key)}
          className={`whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium ${value === t.key ? "border-brand-600 text-brand-700 dark:text-brand-300" : "border-transparent text-ink-500 hover:text-ink-800 dark:hover:text-ink-200"}`}>
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function Kpi({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: string; tone?: "good" | "warn" | "bad" }) {
  const color = tone === "good" ? "text-emerald-600 dark:text-emerald-400" : tone === "warn" ? "text-amber-600 dark:text-amber-400" : tone === "bad" ? "text-red-600 dark:text-red-400" : "text-ink-900 dark:text-white";
  return (
    <div className="card">
      <div className="text-xs font-medium text-ink-500 dark:text-ink-400">{label}</div>
      <div className={`mt-1 text-2xl font-bold tabular-nums ${color}`}>{value}</div>
      {hint && <div className="text-xs text-ink-400">{hint}</div>}
    </div>
  );
}
