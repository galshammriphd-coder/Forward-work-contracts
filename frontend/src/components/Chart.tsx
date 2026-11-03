import { useEffect, useRef } from "react";
// @ts-ignore - plotly dist has no bundled types
import Plotly from "plotly.js-dist-min";
import { Download } from "lucide-react";
import { useI18n } from "../lib/i18n";
import { useStore } from "../lib/store";

export type ChartSpec = { id: string; title_en: string; title_ar: string; figure: { data: any[]; layout?: any } };

export default function Chart({ spec, height = 340, onClick }: { spec: ChartSpec; height?: number; onClick?: (pt: any) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const { lang } = useI18n();
  const { theme } = useStore();
  const title = lang === "ar" ? spec.title_ar : spec.title_en;
  useEffect(() => {
    if (!ref.current) return;
    const dark = theme === "dark";
    const fg = dark ? "#e2e8f0" : "#1e293b";
    const grid = dark ? "#334155" : "#e2e8f0";
    const base = spec.figure.layout || {};
    const axis = (a: any = {}) => ({ gridcolor: grid, zerolinecolor: grid, automargin: true, ...a });
    const layout = {
      ...base,
      height,
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      font: { family: "'IBM Plex Sans Arabic', 'IBM Plex Sans', sans-serif", color: fg, size: 12 },
      xaxis: axis(base.xaxis),
      yaxis: axis(base.yaxis),
      legend: { ...(base.legend || {}), font: { color: fg } },
      margin: { l: 50, r: 20, b: 50, ...(base.margin || {}), t: 20 },
    };
    Plotly.react(ref.current, spec.figure.data, layout, {
      responsive: true, displaylogo: false,
      toImageButtonOptions: { format: "png", filename: spec.id, scale: 2 },
      modeBarButtonsToRemove: ["lasso2d", "select2d"],
    });
    const el: any = ref.current;
    if (onClick) { el.removeAllListeners?.("plotly_click"); el.on?.("plotly_click", (e: any) => onClick(e.points?.[0])); }
  }, [spec, theme, height, onClick]);
  useEffect(() => () => { if (ref.current) Plotly.purge(ref.current); }, []);

  const save = (format: "png" | "svg") => {
    if (ref.current) Plotly.downloadImage(ref.current, { format, filename: spec.id, width: 1000, height: 600, scale: format === "png" ? 2 : 1 });
  };
  return (
    <div className="card min-w-0">
      <div className="mb-1 flex items-center justify-between gap-2">
        <h4 className="text-sm font-semibold">{title}</h4>
        <div className="flex gap-1">
          <button className="btn-ghost px-2 py-0.5 text-xs" onClick={() => save("png")} title="PNG"><Download size={12} />PNG</button>
          <button className="btn-ghost px-2 py-0.5 text-xs" onClick={() => save("svg")} title="SVG"><Download size={12} />SVG</button>
        </div>
      </div>
      <div ref={ref} dir="ltr" />
    </div>
  );
}
