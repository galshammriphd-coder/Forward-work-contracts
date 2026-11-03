import { useState } from "react";
import { CheckCircle2, ChevronDown, Copy, XCircle, CircleDot } from "lucide-react";
import Chart from "./Chart";
import { fmtNum, fmtP, pick, useI18n } from "../lib/i18n";

export type TableSpec = { id: string; title_en: string; title_ar: string; columns: { key: string; en: string; ar: string; fmt?: string | null }[]; rows: any[]; note_en?: string; note_ar?: string };

export function cell(v: any, fmt?: string | null): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "✓" : "✗";
  if (Array.isArray(v)) return v.map((x) => cell(x)).join(" | ");
  if (typeof v === "number") {
    if (fmt === "p") return fmtP(v);
    if (fmt && /^\d$/.test(fmt)) return v.toFixed(Number(fmt));
    return Number.isInteger(v) ? String(v) : Math.abs(v) < 1000 ? v.toFixed(3) : v.toFixed(1);
  }
  return String(v);
}

export function DataTableView({ t, max = 400 }: { t: TableSpec; max?: number }) {
  const { lang } = useI18n();
  const [all, setAll] = useState(false);
  const rows = all ? t.rows : t.rows.slice(0, max);
  return (
    <div className="card">
      <h4 className="mb-2 text-sm font-semibold">{pick(t, "title", lang)}</h4>
      <div className="max-h-[480px] overflow-auto">
        <table className="tbl">
          <thead><tr>{t.columns.map((c) => <th key={c.key}>{lang === "ar" ? c.ar : c.en}</th>)}</tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                {t.columns.map((c) => {
                  let key = c.key;
                  if (lang === "ar" && key.endsWith("_en") && r[key.slice(0, -3) + "_ar"] !== undefined) key = key.slice(0, -3) + "_ar";
                  const v = r[key];
                  const isP = c.fmt === "p" && typeof v === "number";
                  return <td key={c.key} className={`tabular-nums ${isP && v < 0.05 ? "font-semibold text-brand-700 dark:text-brand-300" : ""}`}>{typeof v === "number" ? <bdi dir="ltr">{cell(v, c.fmt)}</bdi> : <bdi>{cell(v, c.fmt)}</bdi>}</td>;
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {t.rows.length > max && !all && <button className="btn-ghost mt-1 text-xs" onClick={() => setAll(true)}>+{t.rows.length - max}</button>}
      {pick(t, "note", lang) && <p className="mt-2 text-xs italic text-ink-500 dark:text-ink-400">{pick(t, "note", lang)}</p>}
    </div>
  );
}

export default function ResultView({ result }: { result: any }) {
  const { lang, t } = useI18n();
  if (!result) return null;
  const it = result.interpretation || {};
  const text = pick(it, "apa", lang) || pick(it, "summary", lang);
  const natureLabel: Record<string, [string, string]> = {
    exploratory: ["استكشافي", "Exploratory"], confirmatory: ["تأكيدي", "Confirmatory"], descriptive: ["وصفي", "Descriptive"],
    inferential: ["استدلالي", "Inferential"], psychometric: ["سيكومتري", "Psychometric"], assumption: ["فحص افتراضات", "Assumption check"],
  };
  const nl = natureLabel[result.nature];
  return (
    <div className="space-y-4">
      <div className="card border-s-4 border-s-brand-600">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <h3 className="text-base font-bold">{pick(result, "title", lang)}</h3>
          {result.n != null && <span className="badge bg-ink-100 text-ink-700 dark:bg-ink-800 dark:text-ink-200">n = {result.n}</span>}
          {nl && <span className="badge bg-brand-100 text-brand-800 dark:bg-brand-900 dark:text-brand-100">{lang === "ar" ? nl[0] : nl[1]}</span>}
          {it.significant === true && <span className="badge bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-100">{t("significant")} (α = {result.alpha})</span>}
          {it.significant === false && <span className="badge bg-ink-200 text-ink-700 dark:bg-ink-700 dark:text-ink-100">{t("notSignificant")} (α = {result.alpha})</span>}
          {result.stale && <span className="badge bg-amber-100 text-amber-800">{t("stale")}</span>}
          {result.filters && Object.keys(result.filters).length > 0 && <span className="badge bg-violet-100 text-violet-800 dark:bg-violet-900 dark:text-violet-100">{lang === "ar" ? "مُرشَّح" : "Filtered"}: {Object.keys(result.filters).join(", ")}</span>}
        </div>
        {text && (
          <div>
            <div className="mb-1 flex items-center gap-2 text-xs font-semibold text-ink-500">{t("interpretationTitle")}
              <button className="btn-ghost px-1 py-0" title="copy" onClick={() => navigator.clipboard?.writeText(text)}><Copy size={12} /></button>
            </div>
            <p className="text-sm leading-8">{text}</p>
          </div>
        )}
        {pick(it, "effect", lang) && <p className="mt-1 text-sm"><b>{t("effect")}:</b> <span dir="ltr">{pick(it, "effect", lang)}</span></p>}
      </div>

      {result.assumptions?.length > 0 && (
        <div className="card">
          <h4 className="mb-2 text-sm font-semibold">{t("assumptions")}</h4>
          <ul className="space-y-1 text-sm">
            {result.assumptions.map((a: any, i: number) => (
              <li key={i} className="flex items-start gap-2">
                {a.met === true ? <CheckCircle2 size={16} className="mt-1 shrink-0 text-emerald-600" /> : a.met === false ? <XCircle size={16} className="mt-1 shrink-0 text-red-600" /> : <CircleDot size={16} className="mt-1 shrink-0 text-ink-400" />}
                <span><b>{pick(a, "name", lang)}</b> <span className="text-ink-500">({a.test})</span>: {pick(a, "detail", lang)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {result.warnings?.length > 0 && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100">
          <b>{t("warnings")}:</b>
          <ul className="list-inside list-disc">{result.warnings.map((w: any, i: number) => <li key={i}>{w[lang]}</li>)}</ul>
        </div>
      )}

      {result.tables?.map((tb: TableSpec) => <DataTableView key={tb.id} t={tb} />)}

      {result.charts?.length > 0 && (
        <div className="grid gap-4 lg:grid-cols-2">{result.charts.map((c: any) => <Chart key={c.id} spec={c} />)}</div>
      )}

      {it.limitations?.length > 0 && (
        <details className="card">
          <summary className="flex cursor-pointer items-center gap-1 text-sm font-semibold"><ChevronDown size={14} />{t("limitations")}</summary>
          <ul className="mt-2 list-inside list-disc text-sm text-ink-600 dark:text-ink-300">{it.limitations.map((l: any, i: number) => <li key={i}>{l[lang]}</li>)}</ul>
        </details>
      )}
    </div>
  );
}

export { fmtNum };
