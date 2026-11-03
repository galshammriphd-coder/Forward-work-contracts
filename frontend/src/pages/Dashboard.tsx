import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { fmtNum, pick, useI18n } from "../lib/i18n";
import { useStore } from "../lib/store";
import Chart from "../components/Chart";
import { DataTableView } from "../components/ResultView";
import { FilterBar } from "../components/Analysis";
import { ErrorBox, Kpi, NeedsData, PageHeader } from "../components/ui";

export default function Dashboard() {
  const { t, tr, lang } = useI18n();
  const { projectId, project, filters, version } = useStore();
  const [ov, setOv] = useState<any>(null);
  const [likert, setLikert] = useState<any>(null);
  const [eda, setEda] = useState<any>(null);
  const [drill, setDrill] = useState<string | null>(null);
  const [error, setError] = useState<any>(null);

  useEffect(() => {
    if (!projectId || !project?.dataset) return;
    api(`/api/projects/${projectId}/overview`).then(setOv).catch(setError);
  }, [projectId, project?.dataset, version]);
  useEffect(() => {
    if (!projectId || !project?.dataset) return;
    setError(null);
    const run = (kind: string, params: any) => api(`/api/projects/${projectId}/run`, { method: "POST", json: { kind, params, filters, save: false } });
    run("likert", drill ? { dimension: drill } : {}).then(setLikert).catch(() => setLikert(null));
    run("eda", {}).then(setEda).catch(setError);
  }, [projectId, project?.dataset, JSON.stringify(filters), drill, version]);

  const onDimClick = useCallback((pt: any) => { if (pt?.x) setDrill(String(pt.x)); }, []);

  if (!project?.dataset) return <><PageHeader title={t("dashboard")} /><NeedsData><span /></NeedsData></>;
  const k = ov?.kpis || {};
  const lc = ov?.project?.lifecycle || [];
  const dimChart = likert?.charts?.find((c: any) => c.id === "dim_means");
  const stack = likert?.charts?.find((c: any) => c.id === "likert_stack");
  const radar = likert?.charts?.find((c: any) => c.id === "dim_radar");
  const demoCharts = (eda?.charts || []).filter((c: any) => c.id.startsWith("demo_"));
  return (
    <div>
      <PageHeader title={t("dashboard")} subtitle={project.name} />
      <NeedsData>
        <ErrorBox error={error} />
        <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-8">
          <Kpi label={tr("إجمالي المشاركين", "Participants")} value={k.participants ?? "—"} hint={k.participants_raw !== k.participants ? `${tr("الأصلي", "original")}: ${k.participants_raw}` : undefined} />
          <Kpi label={tr("إجمالي المتغيرات", "Variables")} value={k.variables ?? "—"} />
          <Kpi label={tr("عدد الأسئلة", "Questions")} value={k.questions ?? "—"} />
          <Kpi label={tr("عدد الأبعاد", "Dimensions")} value={k.dimensions ?? "—"} />
          <Kpi label={tr("نسبة الاكتمال", "Completeness")} value={k.completeness_pct != null ? `${fmtNum(k.completeness_pct, 1)}%` : "—"} tone={k.completeness_pct >= 95 ? "good" : "warn"} />
          <Kpi label={tr("القيم المفقودة", "Missing")} value={k.missing_pct != null ? `${fmtNum(k.missing_pct, 1)}%` : "—"} tone={k.missing_pct > 5 ? "warn" : "good"} />
          <Kpi label={tr("السجلات المكررة", "Duplicates")} value={k.duplicates ?? "—"} tone={k.duplicates ? "warn" : "good"} />
          <Kpi label={tr("مؤشر جودة البيانات", "Data quality index")} value={k.quality_score != null ? fmtNum(k.quality_score, 1) : "—"} tone={k.quality_score >= 90 ? "good" : k.quality_score >= 75 ? "warn" : "bad"} hint="/100" />
        </div>

        <div className="card mb-4">
          <h3 className="mb-3 text-sm font-semibold">{tr("دورة حياة علم البيانات", "Data-science lifecycle")}</h3>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
            {lc.map((s: any, i: number) => (
              <div key={s.key}>
                <div className="mb-1 flex justify-between text-xs"><span>{i + 1}. {s[lang]}</span><span className="tabular-nums">{s.progress}%</span></div>
                <div className="h-2 overflow-hidden rounded-full bg-ink-200 dark:bg-ink-800">
                  <div className={`h-full rounded-full ${s.status === "done" ? "bg-emerald-500" : s.status === "in_progress" ? "bg-brand-500" : "bg-ink-300"}`} style={{ width: `${s.progress}%` }} />
                </div>
              </div>
            ))}
          </div>
        </div>

        <FilterBar />

        <div className="mb-4 grid gap-4 lg:grid-cols-2">
          {dimChart && !drill && <Chart spec={dimChart} onClick={onDimClick} />}
          {drill && (
            <div className="card lg:col-span-2">
              <div className="mb-2 flex items-center justify-between">
                <h3 className="text-sm font-semibold">{tr("تفاصيل البعد", "Dimension details")}: {drill}</h3>
                <button className="btn-secondary" onClick={() => setDrill(null)}>{tr("العودة إلى المؤشرات العامة", "Back to overview")}</button>
              </div>
              {likert?.tables?.[0] && <DataTableView t={likert.tables[0]} />}
            </div>
          )}
          {radar && !drill && <Chart spec={radar} />}
          {stack && <div className="lg:col-span-2"><Chart spec={stack} height={Math.max(300, 26 * (stack.figure.data[0]?.y?.length || 10))} /></div>}
          {demoCharts.slice(0, 4).map((c: any) => <Chart key={c.id} spec={c} height={280} />)}
        </div>
        {!drill && dimChart && <p className="-mt-2 mb-4 text-xs text-ink-500">{tr("انقر على أي بعد في المخطط للانتقال إلى تفاصيل أسئلته.", "Click a dimension bar to drill down into its items.")}</p>}

        <div className="grid gap-4 lg:grid-cols-2">
          <div className="card">
            <h3 className="mb-2 text-sm font-semibold">{tr("مشكلات الجودة المكتشفة", "Detected quality issues")}</h3>
            {(k.issues || []).length === 0 && <p className="text-sm text-ink-500">{tr("لا توجد مشكلات.", "No issues.")}</p>}
            <ul className="space-y-1 text-sm">
              {(k.issues || []).map((i: any, n: number) => (
                <li key={n} className="flex justify-between gap-2">
                  <span><span className={`me-2 inline-block h-2 w-2 rounded-full ${i.severity === "high" ? "bg-red-500" : i.severity === "medium" ? "bg-amber-500" : "bg-ink-400"}`} />{i[lang]}</span>
                  <b className="tabular-nums">{i.count}</b>
                </li>
              ))}
            </ul>
            <Link to="/cleaning" className="mt-2 inline-block text-sm text-brand-700 underline dark:text-brand-300">{t("cleaning")}</Link>
          </div>
          <div className="card">
            <h3 className="mb-2 text-sm font-semibold">{tr("أحدث التحليلات", "Recent analyses")}</h3>
            {(ov?.recent || []).length === 0 && <p className="text-sm text-ink-500">{tr("لم تُنفذ تحليلات بعد.", "No analyses yet.")}</p>}
            <ul className="space-y-1 text-sm">
              {(ov?.recent || []).map((a: any) => (
                <li key={a.id} className="flex justify-between gap-2">
                  <span>{pick(a, "title", lang)}</span>
                  {a.significant != null && <span className={`badge ${a.significant ? "bg-emerald-100 text-emerald-800" : "bg-ink-100 text-ink-600"}`}>{a.significant ? t("significant") : t("notSignificant")}</span>}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </NeedsData>
    </div>
  );
}
