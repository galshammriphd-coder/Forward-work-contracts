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

/** Half-circle gauge: one value against a maximum, with scale labels around the arc. */
export function Gauge({ value, max = 100, color = "var(--c1)", fmt, sub, marker, ends }: { value: number | null | undefined; max?: number; color?: string; fmt?: (v: number) => string; sub?: string; marker?: number; ends?: boolean }) {
  const { num } = useApp();
  const tip = useTip();
  const f = fmt || ((v: number) => num(v));
  const v = Math.max(0, Math.min(max, value ?? 0)), R = 78, W = 30, cx = 130, cy = 118;
  const pt = (frac: number, r: number) => [cx - r * Math.cos(Math.PI * frac), cy - r * Math.sin(Math.PI * frac)];
  const arc = (to: number) => { const [x0, y0] = pt(0, R), [x1, y1] = pt(to, R); return `M${x0.toFixed(1)},${y0.toFixed(1)} A${R},${R} 0 0 1 ${x1.toFixed(1)},${y1.toFixed(1)}`; };
  const frac = max ? v / max : 0;
  return <div className="chart gauge" onMouseMove={e => tip.show(e, <><b>{value == null ? "—" : f(value)}</b> / {f(max)}{sub ? <><br />{sub}</> : null}</>)} onMouseLeave={tip.hide}>
    <svg viewBox="0 0 260 142" role="img" aria-label={`${value == null ? "—" : f(value)} / ${f(max)}`}>
      <path d={arc(1)} fill="none" stroke="var(--gauge-track)" strokeWidth={W} />
      {frac > 0.004 ? <path className="gauge-val" d={arc(frac)} fill="none" stroke={color} strokeWidth={W} pathLength={100} strokeDasharray="100" /> : null}
      {(ends ? [0, 1] : [0, .25, .5, .75, 1]).map(t => { const [x, y] = pt(t, R + W / 2 + (ends ? 4 : 12)); if (ends) return <text key={t} x={x} y={cy + 16} textAnchor="middle">{f(max * t)}</text>; return <text key={t} x={x} y={y + 4} textAnchor="middle">{f(max * t)}</text>; })}
      {marker != null ? (() => { const [x0, y0] = pt(marker / max, R - W / 2 - 3), [x1, y1] = pt(marker / max, R + W / 2 + 3); return <line x1={x0} y1={y0} x2={x1} y2={y1} stroke="var(--ink)" strokeWidth={2} />; })() : null}
      <text x={cx} y={cy - 6} textAnchor="middle" className="gauge-num">{value == null ? "—" : f(value)}</text>
    </svg>{sub ? <div className="gauge-sub">{sub}</div> : null}{tip.node}</div>;
}

/** Share ring: one percentage with its label underneath. */
export function Ring({ pct, label, color, count, onPick }: { pct: number; label: string; color: string; count?: number; onPick?: () => void }) {
  const { num } = useApp();
  const C = 2 * Math.PI * 30;
  return <button className="ring" onClick={onPick} disabled={!onPick} aria-label={`${label}: ${num(pct)}%`}>
    <svg viewBox="0 0 80 80" width="84" height="84"><circle cx="40" cy="40" r="30" fill="none" stroke="var(--gauge-track)" strokeWidth="9" />
      {pct > 0 ? <circle className="ring-val" cx="40" cy="40" r="30" fill="none" stroke={color} strokeWidth="9" strokeLinecap="round" strokeDasharray={`${(C * pct) / 100} ${C}`} transform="rotate(-90 40 40)" /> : null}
      <text x="40" y="45" textAnchor="middle">{num(pct)}%</text></svg>
    <b>{label}</b>{count != null ? <small>{num(count)}</small> : null}</button>;
}

/** Vertical grouped bars on one shared axis (budget against actual per category). */
export function VBars({ rows, names, fmt, height = 240 }: { rows: { label: string; a: number; b: number }[]; names: [string, string]; fmt?: (v: number) => string; height?: number }) {
  const { num } = useApp();
  const tip = useTip();
  const f = fmt || ((v: number) => num(v));
  const W = 560, H = height, pl = 64, pr = 10, pt = 10, pb = 34;
  const top = Math.max(1, ...rows.flatMap(r => [r.a, r.b])) * 1.1, n = Math.max(1, rows.length), slot = (W - pl - pr) / n, bw = Math.min(34, slot / 3.2);
  const y = (v: number) => pt + (1 - v / top) * (H - pt - pb);
  return <div className="chart stack tight"><Legend items={[[names[0], "var(--c-budget)"], [names[1], "var(--c-actual)"]]} />
    <svg viewBox={`0 0 ${W} ${H}`} role="img" style={{ direction: "ltr" }}>
      {[0, .25, .5, .75, 1].map(t => <g key={t}><line className="grid-l" x1={pl} x2={W - pr} y1={y(top * t)} y2={y(top * t)} /><text x={pl - 6} y={y(top * t) + 4} textAnchor="end">{f(top * t)}</text></g>)}
      {rows.map((r, i) => { const x0 = pl + slot * i + slot / 2;
        return <g key={i} onMouseMove={e => tip.show(e, <><b>{r.label}</b><br />{names[0]}: {f(r.a)}<br />{names[1]}: {f(r.b)}</>)} onMouseLeave={tip.hide}>
          <rect x={x0 - slot / 2} y={pt} width={slot} height={H - pt - pb} fill="transparent" />
          <rect className="vbar" x={x0 - bw - 1} y={y(r.a)} width={bw} height={Math.max(0, H - pb - y(r.a))} rx={2} fill="var(--c-budget)" />
          <rect className="vbar" x={x0 + 1} y={y(r.b)} width={bw} height={Math.max(0, H - pb - y(r.b))} rx={2} fill="var(--c-actual)" />
          <text x={x0} y={H - 14} textAnchor="middle">{r.label.length > 16 ? r.label.slice(0, 15) + "…" : r.label}</text></g>; })}
    </svg>{tip.node}</div>;
}
