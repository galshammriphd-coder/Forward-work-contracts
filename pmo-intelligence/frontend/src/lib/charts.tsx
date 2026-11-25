import { ReactNode, useRef, useState } from "react";
import { useApp } from "./core";

/* One tooltip for every chart: follows the pointer, text in the UI ink (never the series colour). */
export function useTip() {
  const [tip, setTip] = useState<{ x: number; y: number; body: ReactNode } | null>(null);
  const show = (e: React.MouseEvent | React.FocusEvent, body: ReactNode) => {
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const x = "clientX" in e && e.clientX ? e.clientX : r.left + r.width / 2;
    const y = "clientY" in e && e.clientY ? e.clientY : r.top;
    setTip({ x: Math.min(x + 12, window.innerWidth - 290), y: Math.max(8, y - 44), body });
  };
  const node = tip ? <div className="tip" style={{ left: tip.x, top: tip.y }}>{tip.body}</div> : null;
  return { show, hide: () => setTip(null), node };
}

export function Legend({ items }: { items: [string, string][] }) {
  return <div className="legend">{items.map(([label, color]) => <span key={label}><i style={{ background: color }} />{label}</span>)}</div>;
}

/** Horizontal bars, one hue (magnitude). Bars start at the inline-start edge, so RTL mirrors by itself. */
export function HBars({ rows, fmt, color = "var(--c1)", onPick, max }: { rows: { label: string; value: number; color?: string; note?: string; key?: any }[]; fmt?: (v: number) => string; color?: string; onPick?: (r: any) => void; max?: number }) {
  const { num } = useApp();
  const tip = useTip();
  const f = fmt || ((v: number) => num(v));
  const top = max ?? Math.max(1, ...rows.map(r => r.value));
  return <div className="chart" style={{ display: "grid", gap: 7 }}>
    {rows.map((r, i) => <div key={i} style={{ display: "grid", gridTemplateColumns: "minmax(90px, 34%) minmax(0, 1fr) auto", gap: 10, alignItems: "center", fontSize: ".84rem" }}
      onMouseMove={e => tip.show(e, <><b>{r.label}</b><br />{f(r.value)}{r.note ? <><br />{r.note}</> : null}</>)} onMouseLeave={tip.hide}>
      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: "var(--ink-2)" }}>{r.label}</span>
      <button onClick={() => onPick?.(r)} disabled={!onPick} aria-label={`${r.label}: ${f(r.value)}`}
        style={{ all: "unset", cursor: onPick ? "pointer" : "default", height: 16, display: "block", background: "var(--sunk)", borderRadius: 3 }}>
        <span style={{ display: "block", height: "100%", width: `${Math.max(r.value > 0 ? 1.5 : 0, (r.value / top) * 100)}%`, background: r.color || color, borderStartEndRadius: 4, borderEndEndRadius: 4 }} /></button>
      <span className="num strong">{f(r.value)}</span>
    </div>)}{tip.node}</div>;
}

/** Two measures on the same scale per category (plan vs actual): paired thin bars, legend above. */
export function PairBars({ rows, names, fmt, onPick }: { rows: { label: string; a: number; b: number; key?: any }[]; names: [string, string]; fmt?: (v: number) => string; onPick?: (r: any) => void }) {
  const { num } = useApp();
  const tip = useTip();
  const f = fmt || ((v: number) => num(v));
  const top = Math.max(1, ...rows.flatMap(r => [r.a, r.b]));
  const bar = (v: number, c: string) => <span style={{ display: "block", height: 8, width: `${Math.max(v > 0 ? 1 : 0, (v / top) * 100)}%`, background: c, borderStartEndRadius: 4, borderEndEndRadius: 4 }} />;
  return <div className="chart stack tight"><Legend items={[[names[0], "var(--c1)"], [names[1], "var(--c2)"]]} />
    {rows.map((r, i) => <div key={i} style={{ display: "grid", gridTemplateColumns: "minmax(90px, 30%) minmax(0, 1fr) auto", gap: 10, alignItems: "center", fontSize: ".84rem", cursor: onPick ? "pointer" : "default" }}
      onClick={() => onPick?.(r)} onMouseMove={e => tip.show(e, <><b>{r.label}</b><br />{names[0]}: {f(r.a)}<br />{names[1]}: {f(r.b)}</>)} onMouseLeave={tip.hide}>
      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: "var(--ink-2)" }}>{r.label}</span>
      <span style={{ display: "grid", gap: 2 }}>{bar(r.a, "var(--c1)")}{bar(r.b, "var(--c2)")}</span>
      <span className="num small">{f(r.a)} / {f(r.b)}</span>
    </div>)}{tip.node}</div>;
}

/** Parts of a whole as one segmented bar with a labelled legend (no pie). */
export function Segments({ parts, onPick }: { parts: { label: string; value: number; color: string; key?: any }[]; onPick?: (p: any) => void }) {
  const { num } = useApp();
  const tip = useTip();
  const total = parts.reduce((s, p) => s + p.value, 0) || 1;
  return <div className="chart stack tight">
    <div style={{ display: "flex", gap: 2, height: 22, borderRadius: 4, overflow: "hidden" }}>
      {parts.filter(p => p.value > 0).map(p => <button key={p.label} onClick={() => onPick?.(p)} aria-label={`${p.label}: ${p.value}`}
        onMouseMove={e => tip.show(e, <><b>{p.label}</b><br />{num(p.value)} ({num((p.value / total) * 100)}%)</>)} onMouseLeave={tip.hide}
        style={{ all: "unset", flex: p.value, background: p.color, cursor: onPick ? "pointer" : "default", minWidth: 4 }} />)}</div>
    <div className="legend">{parts.map(p => <button key={p.label} onClick={() => onPick?.(p)} style={{ all: "unset", cursor: onPick ? "pointer" : "default" }}>
      <i style={{ background: p.color }} />{p.label} <b className="num" style={{ color: "var(--ink)" }}>{num(p.value)}</b></button>)}</div>{tip.node}</div>;
}

/** Line chart on one shared axis. Time runs from the inline-start side (right in Arabic). */
export function Lines({ x, series, fmt, height = 220, marker }: { x: string[]; series: { name: string; color: string; values: (number | null | undefined)[]; dash?: boolean }[]; fmt?: (v: number) => string; height?: number; marker?: number }) {
  const { num, lang, date } = useApp();
  const tip = useTip();
  const ref = useRef<SVGSVGElement>(null);
  const [hover, setHover] = useState<number | null>(null);
  const f = fmt || ((v: number) => num(v));
  const W = 640, H = height, pl = 56, pr = 16, pt = 12, pb = 26;
  const rtl = lang === "ar";
  const all = series.flatMap(s => s.values.filter((v): v is number => v != null));
  const top = Math.max(1, ...all) * 1.08;
  const n = Math.max(2, x.length);
  const px = (i: number) => { const t = pl + (i / (n - 1)) * (W - pl - pr); return rtl ? W - t : t; };
  const py = (v: number) => pt + (1 - v / top) * (H - pt - pb);
  const ticks = [0, 0.25, 0.5, 0.75, 1].map(t => t * top);
  const path = (vals: any[]) => vals.map((v, i) => (v == null ? "" : `${i === 0 || vals[i - 1] == null ? "M" : "L"}${px(i).toFixed(1)},${py(v).toFixed(1)}`)).join(" ");
  const move = (e: React.MouseEvent) => {
    const r = ref.current!.getBoundingClientRect();
    let t = ((e.clientX - r.left) / r.width) * W; if (rtl) t = W - t;
    const i = Math.max(0, Math.min(n - 1, Math.round(((t - pl) / (W - pl - pr)) * (n - 1))));
    setHover(i);
    tip.show(e, <><b>{date(x[i])}</b>{series.map(s => s.values[i] != null && <div key={s.name}><i style={{ display: "inline-block", width: 8, height: 8, borderRadius: 2, background: s.color, marginInlineEnd: 6 }} />{s.name}: {f(s.values[i] as number)}</div>)}</>);
  };
  return <div className="chart stack tight">
    {series.length > 1 && <Legend items={series.map(s => [s.name, s.color])} />}
    <svg ref={ref} viewBox={`0 0 ${W} ${H}`} role="img" onMouseMove={move} onMouseLeave={() => { setHover(null); tip.hide(); }}>
      {ticks.map((t, i) => <g key={i}><line className="grid-l" x1={pl} x2={W - pr} y1={py(t)} y2={py(t)} />
        <text x={rtl ? W - pl + 6 : pl - 6} y={py(t) + 4} textAnchor={rtl ? "start" : "end"}>{f(t)}</text></g>)}
      {[0, Math.floor((n - 1) / 2), n - 1].filter((v, i, a) => a.indexOf(v) === i && x[v]).map(i => <text key={i} x={px(i)} y={H - 6} textAnchor="middle">{date(x[i])}</text>)}
      {marker != null && marker >= 0 && <line x1={px(marker)} x2={px(marker)} y1={pt} y2={H - pb} stroke="var(--ink-3)" strokeDasharray="3 3" />}
      {series.map(s => <path key={s.name} d={path(s.values)} fill="none" stroke={s.color} strokeWidth={2} strokeDasharray={s.dash ? "5 4" : undefined} strokeLinejoin="round" strokeLinecap="round" />)}
      {hover != null && <><line x1={px(hover)} x2={px(hover)} y1={pt} y2={H - pb} className="axis" />
        {series.map(s => s.values[hover] != null && <circle key={s.name} cx={px(hover)} cy={py(s.values[hover] as number)} r={4.5} fill={s.color} stroke="var(--surface)" strokeWidth={2} />)}</>}
    </svg>{tip.node}</div>;
}

/** 5×5 probability × impact matrix. Level is written in the legend; count is the cell label. */
export function RiskMatrix({ grid, onPick }: { grid: any[][]; onPick?: (cell: any) => void }) {
  const { T, num } = useApp();
  const tip = useTip();
  const lv: Record<string, [string, string]> = { low: ["منخفض", "Low"], moderate: ["متوسط", "Moderate"], high: ["عالٍ", "High"], critical: ["حرج", "Critical"] };
  return <div className="stack tight">
    <div className="heat">
      {grid.map((row, i) => [<div key={`a${i}`} className="ax num">{row[0].probability}</div>,
        ...row.map((c: any) => <button key={`${c.probability}-${c.impact}`} className={`lv-${c.level} ${c.count ? "" : "zero"}`} onClick={() => c.count && onPick?.(c)}
          aria-label={`${T("احتمالية", "Probability")} ${c.probability}, ${T("أثر", "impact")} ${c.impact}: ${c.count}`}
          onMouseMove={e => tip.show(e, <>{T("الاحتمالية", "Probability")} {c.probability} × {T("الأثر", "Impact")} {c.impact} = {c.score}<br />{T(...lv[c.level])} · {num(c.count)} {T("خطر", "risk(s)")}</>)} onMouseLeave={tip.hide}>{c.count || "·"}</button>)])}
      <div />{[1, 2, 3, 4, 5].map(i => <div key={i} className="ax num">{i}</div>)}
    </div>
    <div className="row small muted" style={{ justifyContent: "space-between" }}><span>{T("↑ الاحتمالية · الأثر ←", "↑ Probability · Impact →")}</span>
      <div className="legend">{Object.entries(lv).map(([k, l]) => <span key={k}><i className={`lv-${k}`} />{T(...l)}</span>)}</div></div>{tip.node}</div>;
}
