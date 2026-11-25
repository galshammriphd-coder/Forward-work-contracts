import { useMemo, useRef, useState } from "react";
import { Calculator, Flag, Plus, Trash2 } from "lucide-react";
import { api, useApp, useLoad } from "../lib/core";
import { Async, Confirm, FieldSpec, Form, Modal, Register, Src, Status } from "../lib/ui";
import { useTip } from "../lib/charts";

const DAY = 86400000;
const D = (s: string) => new Date(`${s}T00:00:00`);
const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const diff = (a: Date, b: Date) => Math.round((+b - +a) / DAY);
const add = (d: Date, n: number) => new Date(+d + n * DAY);

export function activityFields(T: any, s: any, meta: any, N: any): FieldSpec[] {
  return [
    { key: "name", label: ["اسم النشاط", "Activity name"], required: true, wide: true },
    { key: "wbs_code", label: ["رمز WBS", "WBS code"] },
    { key: "phase_id", label: ["المرحلة", "Phase"], type: "select", options: (s?.phases || []).map((p: any) => [p.id, p.name]) },
    { key: "wbs_id", label: ["عنصر WBS", "WBS element"], type: "select", options: (s?.wbs || []).map((w: any) => [w.id, `${w.code} ${w.name}`]) },
    { key: "parent_id", label: ["النشاط الأب", "Parent activity"], type: "select", options: (s?.activities || []).filter((a: any) => !a.parent_id).map((a: any) => [a.id, a.name]), hint: ["اختر أباً لجعل هذا النشاط مهمة فرعية", "Choose a parent to make this a subtask"] },
    { key: "duration_days", label: ["المدة (أيام عمل)", "Duration (working days)"], type: "number", def: 5, required: true, hint: ["0 = معلم", "0 = milestone"] },
    { key: "constraint_start", label: ["لا يبدأ قبل", "Start no earlier than"], type: "date" },
    { key: "progress", label: ["نسبة الإنجاز %", "Progress %"], type: "number", def: 0 },
    { key: "priority", label: ["الأولوية", "Priority"], type: "select", def: "medium", options: [["low", T("منخفضة", "Low")], ["medium", T("متوسطة", "Medium")], ["high", T("عالية", "High")]] },
    { key: "responsible_id", label: ["المسؤول", "Responsible"], type: "select", options: (meta?.users || []).map((u: any) => [u.id, N(u)]) },
    { key: "supporting_team", label: ["الفريق المساند", "Supporting team"] },
    { key: "required_resources", label: ["الموارد المطلوبة", "Required resources"] },
    { key: "estimated_cost", label: ["التكلفة التقديرية", "Estimated cost"], type: "number", def: 0 },
    { key: "weight", label: ["وزن النشاط %", "Activity weight %"], type: "number", def: 0 },
    { key: "completion_criteria", label: ["معيار الإنجاز", "Completion criteria"], wide: true },
    { key: "description", label: ["الوصف", "Description"], type: "textarea" },
  ];
}

function ActivityModal({ pid, s, act, onClose, onSaved }: { pid: number; s: any; act: any; onClose: () => void; onSaved: () => void }) {
  const { T, N, meta, fail, toast, can } = useApp();
  const [v, setV] = useState<any>(act.id ? { ...act } : { duration_days: 5, progress: 0, priority: "medium", ...act });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [dep, setDep] = useState<any>({ predecessor_id: "", type: "FS", lag_days: 0 });
  const [del, setDel] = useState(false);
  const write = can("schedule.write");
  const preds = s.dependencies.filter((d: any) => d.successor_id === act.id);
  const name = (id: number) => s.activities.find((a: any) => a.id === id)?.name || id;
  const run = async (fn: () => Promise<any>, msg?: string) => { setBusy(true); setErr(""); try { await fn(); msg && toast(msg); onSaved(); return true; } catch (e: any) { e.message === "NETWORK" ? fail(e) : setErr(e.message); return false; } finally { setBusy(false); } };
  const save = () => { if (!v.name) return setErr(T("أدخل اسم النشاط.", "Enter the activity name.")); run(() => act.id ? api.patch(`/r/activities/${act.id}`, v) : api.post("/r/activities", { ...v, project_id: pid }), T("حُفظ النشاط وأعيد حساب الجدول", "Activity saved and schedule recalculated")).then(ok => ok && onClose()); };
  return <Modal wide title={act.id ? T("تعديل النشاط", "Edit activity") : T("نشاط جديد", "New activity")} onClose={onClose} footer={write && <>
    {act.id && <button className="btn danger" style={{ marginInlineEnd: "auto" }} onClick={() => setDel(true)}><Trash2 />{T("احذف النشاط", "Delete activity")}</button>}
    <button className="btn" onClick={onClose}>{T("إلغاء", "Cancel")}</button><button className="btn primary" disabled={busy} onClick={save}>{T("حفظ", "Save")}</button></>}>
    <div className="stack">
      {err && <div className="note critical" role="alert">{err}</div>}
      {act.id && <div className="row small muted"><Src v={act.source_tag} /><span>{T("البداية", "Start")}: <bdi>{act.planned_start}</bdi></span><span>{T("النهاية", "End")}: <bdi>{act.planned_end}</bdi></span>
        <span>{T("الفائض الزمني", "Total float")}: <bdi>{act.total_float}</bdi></span>{act.is_critical && <span className="tag critical">{T("على المسار الحرج", "On the critical path")}</span>}</div>}
      <Form fields={activityFields(T, s, meta, N)} value={v} onChange={setV} />
      {act.id && <section className="stack tight"><h3>{T("الأنشطة السابقة (الاعتماديات)", "Predecessors (dependencies)")}</h3>
        {preds.length === 0 && <p className="muted small">{T("لا اعتماديات. يبدأ النشاط مع بداية المشروع أو حسب القيد.", "No dependencies. The activity starts with the project or its constraint.")}</p>}
        {preds.map((d: any) => <div key={d.id} className="row small"><span className="grow">{name(d.predecessor_id)}</span><span className="tag">{d.type}</span>
          <span>{T("فاصل", "Lag")} <bdi>{d.lag_days}</bdi></span>{write && <button className="btn ghost sm icon danger" aria-label={T("احذف الاعتمادية", "Remove dependency")} onClick={() => run(() => api.del(`/r/dependencies/${d.id}`))}><Trash2 /></button>}</div>)}
        {write && <div className="row">
          <select className="input grow" style={{ width: "auto" }} value={dep.predecessor_id} onChange={e => setDep({ ...dep, predecessor_id: e.target.value })} aria-label={T("النشاط السابق", "Predecessor")}>
            <option value="">{T("اختر نشاطاً سابقاً…", "Choose a predecessor…")}</option>
            {s.activities.filter((a: any) => a.id !== act.id && !a.is_summary && !preds.some((d: any) => d.predecessor_id === a.id)).map((a: any) => <option key={a.id} value={a.id}>{a.wbs_code} {a.name}</option>)}</select>
          <select className="input" style={{ width: 150 }} value={dep.type} onChange={e => setDep({ ...dep, type: e.target.value })} aria-label={T("نوع العلاقة", "Relationship")}>
            <option value="FS">FS — {T("نهاية لبداية", "Finish to start")}</option><option value="SS">SS — {T("بداية لبداية", "Start to start")}</option>
            <option value="FF">FF — {T("نهاية لنهاية", "Finish to finish")}</option><option value="SF">SF — {T("بداية لنهاية", "Start to finish")}</option></select>
          <input className="input" style={{ width: 90 }} type="number" value={dep.lag_days} onChange={e => setDep({ ...dep, lag_days: +e.target.value })} aria-label={T("الفاصل بالأيام (سالب = تقديم)", "Lag in days (negative = lead)")} title={T("الفاصل بالأيام (سالب = تقديم)", "Lag in days (negative = lead)")} />
          <button className="btn" disabled={!dep.predecessor_id || busy} onClick={() => run(() => api.post("/r/dependencies", { project_id: pid, predecessor_id: +dep.predecessor_id, successor_id: act.id, type: dep.type, lag_days: dep.lag_days })).then(() => setDep({ predecessor_id: "", type: "FS", lag_days: 0 }))}><Plus />{T("اربط", "Link")}</button>
        </div>}</section>}
    </div>
    {del && <Confirm title={T("حذف النشاط", "Delete activity")} text={T(`سيحذف «${act.name}» واعتمادياته ومهامه الفرعية، ثم يعاد حساب الجدول.`, `“${act.name}”, its links and subtasks will be deleted and the schedule recalculated.`)}
      onClose={() => setDel(false)} onYes={async () => { await api.del(`/r/activities/${act.id}`); onSaved(); onClose(); }} />}
  </Modal>;
}

function Gantt({ s, zoom, showBase, critOnly, onOpen, onChange, write }: { s: any; zoom: number; showBase: boolean; critOnly: boolean; onOpen: (a: any) => void; onChange: (id: number, patch: any) => void; write: boolean }) {
  const { T, date, lang } = useApp();
  const tip = useTip();
  const [drag, setDrag] = useState<{ id: number; mode: "move" | "size"; x0: number; dx: number } | null>(null);
  const moved = useRef(false);
  const rows = useMemo(() => {
    const kids: Record<string, any[]> = {};
    s.activities.forEach((a: any) => (kids[a.parent_id || 0] ||= []).push(a));
    const out: any[] = [];
    const walk = (pid: number, depth: number) => (kids[pid] || []).forEach(a => { if (!critOnly || a.is_critical) out.push({ ...a, depth }); walk(a.id, depth + 1); });
    walk(0, 0);
    return out;
  }, [s.activities, critOnly]);
  const base = s.baseline?.activities || {};
  const dates = rows.flatMap((a: any) => [a.planned_start, a.planned_end, showBase && base[a.id]?.start, showBase && base[a.id]?.end]).filter(Boolean).map(D);
  s.milestones.forEach((m: any) => m.target_date && dates.push(D(m.target_date)));
  if (!dates.length) return null;
  const t0 = add(new Date(Math.min(...dates.map(d => +d))), -4), t1 = add(new Date(Math.max(...dates.map(d => +d))), 10);
  const days = diff(t0, t1), W = days * zoom, RH = 32, HH = 44, H = HH + rows.length * RH + 30;
  const x = (d: string | Date) => diff(t0, typeof d === "string" ? D(d) : d) * zoom;
  const idx: Record<number, number> = {}; rows.forEach((a, i) => (idx[a.id] = i));
  const weekend = (s.calendar?.weekend || [4, 5]).map((p: number) => (p + 1) % 7);
  const isWork = (d: Date) => !weekend.includes(d.getDay()) && !(s.calendar?.holidays || []).includes(iso(d));
  const months: { x: number; label: string }[] = [];
  for (let d = new Date(t0.getFullYear(), t0.getMonth(), 1); d < t1; d = new Date(d.getFullYear(), d.getMonth() + 1, 1)) months.push({ x: Math.max(0, x(d)), label: new Intl.DateTimeFormat(lang === "ar" ? "ar-SA-u-nu-latn-ca-gregory" : "en-GB", { month: "short", year: "2-digit" }).format(d) });
  const weeks: number[] = []; for (let i = 0; i < days; i += 7) weeks.push(i * zoom);
  const today = new Date(); today.setHours(0, 0, 0, 0);

  const up = () => {
    if (!drag) return;
    const a = rows.find(r => r.id === drag.id), n = Math.round(drag.dx / zoom);
    setDrag(null);
    if (!a || !n) return;
    if (drag.mode === "move") onChange(a.id, { constraint_start: iso(add(D(a.planned_start), n)) });
    else { let w = 0; const end = add(D(a.planned_end), n); for (let d = D(a.planned_start); d <= end; d = add(d, 1)) w += isWork(d) ? 1 : 0; onChange(a.id, { duration_days: Math.max(1, w) }); }
  };
  const links = s.dependencies.filter((d: any) => idx[d.predecessor_id] !== undefined && idx[d.successor_id] !== undefined).map((d: any) => {
    const p = rows[idx[d.predecessor_id]], q = rows[idx[d.successor_id]];
    const x1 = d.type[0] === "F" ? x(p.planned_end) + zoom : x(p.planned_start), x2 = d.type[1] === "S" ? x(q.planned_start) : x(q.planned_end) + zoom;
    const y1 = HH + idx[p.id] * RH + RH / 2, y2 = HH + idx[q.id] * RH + RH / 2, mid = d.type[0] === "F" ? x1 + 6 : x1 - 6;
    return { id: d.id, crit: p.is_critical && q.is_critical, path: `M${x1},${y1} H${mid} V${y2 - (y2 > y1 ? 9 : -9)} H${x2 + (d.type[1] === "S" ? -7 : 7)} V${y2} H${x2}`, x2, y2, s: d.type[1] === "S" };
  });
  return <div className="gantt">
    <div className="g-list"><div className="g-row head"><span className="grow">{T("النشاط", "Activity")}</span><span>%</span></div>
      {rows.map(a => <div key={a.id} className={`g-row ${a.is_summary ? "summary" : ""}`} style={{ paddingInlineStart: 10 + a.depth * 14 }}>
        <button onClick={() => onOpen(a)} title={a.name}><bdi className="muted small">{a.wbs_code}</bdi> {a.name}</button><span className="num small muted">{Math.round(a.progress || 0)}</span></div>)}</div>
    <div className="g-chart" onPointerMove={e => { if (drag) { moved.current = true; setDrag({ ...drag, dx: e.clientX - drag.x0 }); } }} onPointerUp={up} onPointerLeave={up}>
      <svg width={W} height={H} style={{ display: "block", touchAction: drag ? "none" : "pan-x" }}>
        <rect width={W} height={HH} fill="var(--raised)" /><line x1={0} x2={W} y1={HH} y2={HH} stroke="var(--line)" />
        {weeks.map(w => <line key={w} x1={w} x2={w} y1={HH - 8} y2={H} stroke="var(--line-2)" />)}
        {months.map((m, i) => <g key={m.x}><line x1={m.x} x2={m.x} y1={0} y2={H} stroke="var(--line)" />{(i === months.length - 1 || months[i + 1].x - m.x > 52) && <text x={m.x + 6} y={18}>{m.label}</text>}</g>)}
        {rows.map((_, i) => <line key={i} x1={0} x2={W} y1={HH + (i + 1) * RH} y2={HH + (i + 1) * RH} stroke="var(--line-2)" />)}
        {today >= t0 && today <= t1 && <g><line x1={x(today)} x2={x(today)} y1={HH - 12} y2={H} stroke="var(--accent)" strokeWidth={1.5} /><text x={x(today) + 4} y={HH - 6} style={{ fill: "var(--accent)" }}>{T("اليوم", "Today")}</text></g>}
        {links.map((l: any) => <g key={l.id} fill="none" stroke={l.crit ? "var(--critical)" : "var(--ink-3)"} strokeWidth={1.1} opacity={.75}><path d={l.path} />
          <path d={l.s ? `M${l.x2 - 5},${l.y2 - 3.5} L${l.x2},${l.y2} L${l.x2 - 5},${l.y2 + 3.5}` : `M${l.x2 + 5},${l.y2 - 3.5} L${l.x2},${l.y2} L${l.x2 + 5},${l.y2 + 3.5}`} /></g>)}
        {rows.map((a, i) => {
          if (!a.planned_start) return null;
          const y = HH + i * RH, d = drag?.id === a.id ? drag : null;
          let bx = x(a.planned_start), bw = Math.max(zoom, x(a.planned_end) - bx + zoom);
          if (d?.mode === "move") bx += d.dx; if (d?.mode === "size") bw = Math.max(zoom, bw + d.dx);
          const b = base[a.id], color = a.is_critical ? "var(--critical)" : "var(--c1)", late = a.planned_end < iso(today) && (a.progress || 0) < 100;
          const info = <><b>{a.name}</b><br />{date(a.planned_start)} → {date(a.planned_end)} · {a.duration_days} {T("يوم عمل", "working days")}<br />{T("الإنجاز", "Progress")} {Math.round(a.progress || 0)}% · {T("الفائض", "Float")} {a.total_float}
            {a.is_critical && <><br />{T("على المسار الحرج", "On the critical path")}</>}{late && <><br />{T("متأخر", "Late")}</>}{b?.end && b.end !== a.planned_end && <><br />{T("خط الأساس ينتهي", "Baseline ends")} {date(b.end)}</>}</>;
          if (a.is_summary) return <g key={a.id} onMouseMove={e => tip.show(e, info)} onMouseLeave={tip.hide}><path d={`M${bx},${y + 19} V${y + 12} H${bx + bw} V${y + 19}`} fill="none" stroke="var(--ink)" strokeWidth={2.5} /></g>;
          if (!a.duration_days) return <path key={a.id} d={`M${bx},${y + 8} l8,8 l-8,8 l-8,-8Z`} fill="var(--gold)" stroke="var(--surface)" strokeWidth={1.5} onMouseMove={e => tip.show(e, info)} onMouseLeave={tip.hide} onClick={() => onOpen(a)} style={{ cursor: "pointer" }} />;
          return <g key={a.id}>
            {showBase && b?.start && <rect x={x(b.start)} y={y + 23} width={Math.max(zoom, x(b.end) - x(b.start) + zoom)} height={4} rx={2} fill="var(--ink-3)" opacity={.55} />}
            <g className={write ? "g-bar" : ""} onMouseMove={e => !drag && tip.show(e, info)} onMouseLeave={tip.hide}
              onPointerDown={e => { if (!write) return; moved.current = false; (e.currentTarget as any).setPointerCapture?.(e.pointerId); setDrag({ id: a.id, mode: "move", x0: e.clientX, dx: 0 }); tip.hide(); }}
              onClick={() => { if (!moved.current) onOpen(a); }}>
              <rect x={bx} y={y + 8} width={bw} height={13} rx={3} fill={color} opacity={.28} />
              <rect x={bx} y={y + 8} width={bw * Math.min(100, a.progress || 0) / 100} height={13} rx={3} fill={color} />
              {late && <rect x={bx} y={y + 8} width={bw} height={13} rx={3} fill="none" stroke="var(--critical)" strokeDasharray="3 2" />}
            </g>
            {write && <rect x={bx + bw - 5} y={y + 6} width={9} height={17} fill="transparent" style={{ cursor: "ew-resize" }}
              onPointerDown={e => { e.stopPropagation(); moved.current = true; (e.currentTarget as any).setPointerCapture?.(e.pointerId); setDrag({ id: a.id, mode: "size", x0: e.clientX, dx: 0 }); }} />}
          </g>;
        })}
        {s.milestones.map((m: any) => m.target_date && <g key={`m${m.id}`} onMouseMove={e => tip.show(e, <><b>{m.name}</b><br />{date(m.target_date)}</>)} onMouseLeave={tip.hide}>
          <line x1={x(m.target_date)} x2={x(m.target_date)} y1={HH} y2={H - 26} stroke="var(--gold)" strokeDasharray="2 4" />
          <path d={`M${x(m.target_date)},${H - 26} l6,6 l-6,6 l-6,-6Z`} fill={m.status === "achieved" ? "var(--s-good)" : "var(--gold)"} /></g>)}
      </svg>
    </div>{tip.node}</div>;
}

export default function Schedule({ pid }: { pid: number }) {
  const { T, can, date, toast, fail, num } = useApp();
  const q = useLoad<any>(`/projects/${pid}/schedule`);
  const [zoom, setZoom] = useState(5);
  const [showBase, setShowBase] = useState(true);
  const [critOnly, setCritOnly] = useState(false);
  const [open, setOpen] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const write = can("schedule.write");
  const change = async (id: number, patch: any) => { try { await api.patch(`/r/activities/${id}`, patch); toast(T("أعيد حساب الجدول والمسار الحرج", "Schedule and critical path recalculated")); } catch (e) { fail(e); } q.reload(); };
  const act = async (fn: () => Promise<any>, msg: string) => { setBusy(true); try { await fn(); toast(msg); await q.reload(); } catch (e) { fail(e); } finally { setBusy(false); } };
  return <Async q={q}>{s => {
    const leaf = s.activities.filter((a: any) => !a.is_summary), bf = s.baseline?.finish;
    const slip = bf && s.finish ? diff(D(bf), D(s.finish)) : 0;
    return <div className="stack">
      <div className="kpis">
        <div className="kpi" style={{ cursor: "default" }}><span>{T("الانتهاء المحسوب", "Calculated finish")}</span><b>{date(s.finish)}</b><small>{T("محسوب بمحرك المسار الحرج", "From the critical-path engine")}</small></div>
        <div className="kpi" style={{ cursor: "default" }}><span>{T("انتهاء خط الأساس", "Baseline finish")}</span><b>{date(bf)}</b><small>{s.baseline ? s.baseline.name : T("لا يوجد خط أساس", "No baseline yet")}</small></div>
        <div className="kpi" style={{ cursor: "default" }}><span>{T("الانحراف عن خط الأساس", "Variance to baseline")}</span><b className={slip > 0 ? "critical" : ""}>{num(slip)} {T("يوم", "days")}</b><small>{slip > 0 ? T("متأخر عن الخطة المعتمدة", "Later than the approved plan") : T("ضمن الخطة المعتمدة", "Within the approved plan")}</small></div>
        <button className="kpi" onClick={() => setCritOnly(!critOnly)}><span>{T("أنشطة المسار الحرج", "Critical-path activities")}</span><b>{num(s.critical_path.length)} / {num(leaf.length)}</b><small>{critOnly ? T("اعرض كل الأنشطة", "Show all activities") : T("اعرض الحرجة فقط", "Show critical only")}</small></button>
      </div>
      <div className="row no-print">
        {write && <button className="btn primary" onClick={() => setOpen({})}><Plus />{T("أضف نشاطاً", "Add activity")}</button>}
        {write && <button className="btn" disabled={busy} onClick={() => act(() => api.post(`/projects/${pid}/schedule/recalculate`), T("أعيد حساب الجدول", "Schedule recalculated"))}><Calculator />{T("أعد حساب الجدول", "Recalculate schedule")}</button>}
        {write && <button className="btn" disabled={busy} onClick={() => act(() => api.post(`/projects/${pid}/baselines`), T("حُفظ خط أساس جديد", "New baseline saved"))}><Flag />{T("احفظ خط أساس جديداً", "Save new baseline")}</button>}
        <span className="grow" />
        <label className="row small"><input type="checkbox" checked={showBase} onChange={e => setShowBase(e.target.checked)} />{T("خط الأساس", "Baseline")}</label>
        <label className="row small"><input type="checkbox" checked={critOnly} onChange={e => setCritOnly(e.target.checked)} />{T("الحرجة فقط", "Critical only")}</label>
        <select className="input" style={{ width: 130 }} value={zoom} onChange={e => setZoom(+e.target.value)} aria-label={T("مقياس الزمن", "Time scale")}>
          <option value={2.5}>{T("ربع سنوي", "Quarter")}</option><option value={5}>{T("شهري", "Month")}</option><option value={11}>{T("أسبوعي", "Week")}</option><option value={22}>{T("يومي", "Day")}</option></select>
      </div>
      {s.activities.length === 0 ? <section className="panel"><div className="empty">{T("لا أنشطة بعد. أضف أول نشاط ليبدأ الجدول.", "No activities yet. Add the first one to start the schedule.")}</div></section>
        : <Gantt s={s} zoom={zoom} showBase={showBase} critOnly={critOnly} onOpen={setOpen} onChange={change} write={write} />}
      <div className="legend"><span><i style={{ background: "var(--c1)" }} />{T("نشاط (الجزء الداكن = المنجز)", "Activity (dark part = done)")}</span><span><i style={{ background: "var(--critical)" }} />{T("مسار حرج", "Critical path")}</span>
        <span><i style={{ background: "var(--ink-3)" }} />{T("خط الأساس", "Baseline")}</span><span><i style={{ background: "var(--gold)", transform: "rotate(45deg)" }} />{T("معلم", "Milestone")}</span>
        {write && <span className="muted">{T("اسحب الشريط لتغيير البداية، واسحب طرفه لتغيير المدة.", "Drag a bar to move its start; drag its end to change duration.")}</span>}</div>
      <Register resource="milestones" projectId={pid} perm="schedule.write" noun={["معلماً", "Milestone"]} title={T("المعالم الرئيسية", "Milestones")} onChanged={q.reload}
        sort={(a, b) => String(a.target_date).localeCompare(String(b.target_date))}
        cols={[{ key: "name", label: ["المعلم", "Milestone"] }, { key: "target_date", label: ["التاريخ المستهدف", "Target date"], type: "date" }, { key: "actual_date", label: ["تاريخ التحقق", "Achieved on"], type: "date" },
          { key: "owner_name", label: ["المسؤول", "Owner"] }, { key: "acceptance_criteria", label: ["معيار الاعتماد", "Acceptance criterion"] }, { key: "status", label: ["الحالة", "Status"], type: "status" }, { key: "source_tag", label: ["المصدر", "Source"], type: "src" }]}
        fields={[{ key: "name", label: ["اسم المعلم", "Milestone name"], required: true, wide: true }, { key: "target_date", label: ["التاريخ المستهدف", "Target date"], type: "date", required: true },
          { key: "status", label: ["الحالة", "Status"], type: "select", def: "pending", required: true, options: [["pending", T("معلق", "Pending")], ["achieved", T("تحقق", "Achieved")], ["missed", T("فائت", "Missed")]] },
          { key: "owner_name", label: ["المسؤول", "Owner"] }, { key: "activity_id", label: ["النشاط المرتبط", "Linked activity"], type: "select", options: leaf.map((a: any) => [a.id, a.name]) },
          { key: "acceptance_criteria", label: ["معيار الاعتماد", "Acceptance criterion"], wide: true }, { key: "description", label: ["الوصف", "Description"], type: "textarea" }]} />
      {open && <ActivityModal pid={pid} s={s} act={open} onClose={() => setOpen(null)} onSaved={q.reload} />}
    </div>;
  }}</Async>;
}

/** Planning view: the WBS tree with activities as an editable table. */
export function Planning({ pid }: { pid: number }) {
  const { T, can, date, money, toast, fail } = useApp();
  const q = useLoad<any>(`/projects/${pid}/schedule`);
  const [open, setOpen] = useState<any>(null);
  const write = can("schedule.write");
  const set = async (a: any, patch: any) => { try { await api.patch(`/r/activities/${a.id}`, patch); toast(T("تم الحفظ", "Saved")); } catch (e) { fail(e); } q.reload(); };
  return <Async q={q}>{s => {
    const phase: Record<number, string> = {}; s.phases.forEach((p: any) => (phase[p.id] = p.name));
    const kids: Record<string, any[]> = {}; s.activities.forEach((a: any) => (kids[a.parent_id || 0] ||= []).push(a));
    const rows: any[] = []; const walk = (p: number, d: number) => (kids[p] || []).forEach(a => { rows.push({ ...a, depth: d }); walk(a.id, d + 1); }); walk(0, 0);
    return <div className="stack">
      <section className="panel"><header><div><h2>{T("هيكل تقسيم العمل والأنشطة", "Work breakdown structure and activities")}</h2>
        <p>{T("المشروع ← المراحل ← المخرجات ← حزم العمل ← الأنشطة ← المهام الفرعية. التواريخ يحسبها محرك الجدولة.", "Project → phases → deliverables → work packages → activities → subtasks. Dates come from the scheduling engine.")}</p></div>
        {write && <button className="btn primary sm" onClick={() => setOpen({})}><Plus />{T("أضف نشاطاً", "Add activity")}</button>}</header>
        {rows.length === 0 ? <div className="empty">{T("لا أنشطة بعد.", "No activities yet.")}</div> :
          <div className="tbl-wrap"><table className="tbl"><thead><tr><th>WBS</th><th>{T("النشاط", "Activity")}</th><th>{T("المرحلة", "Phase")}</th><th>{T("المسؤول", "Responsible")}</th><th>{T("البداية", "Start")}</th><th>{T("النهاية", "End")}</th>
            <th className="num">{T("المدة", "Days")}</th><th className="num">{T("التكلفة", "Cost")}</th><th className="num">{T("الوزن %", "Weight %")}</th><th style={{ width: 130 }}>{T("الإنجاز %", "Progress %")}</th><th>{T("الحالة", "Status")}</th><th>{T("المصدر", "Source")}</th></tr></thead>
            <tbody>{rows.map(a => <tr key={a.id} className="click" onClick={() => setOpen(a)}>
              <td className="num">{a.wbs_code}</td><td style={{ paddingInlineStart: 12 + a.depth * 18, fontWeight: a.is_summary ? 600 : 400 }}>{a.name} {a.is_critical && !a.is_summary && <span className="tag critical">{T("حرج", "Critical")}</span>}</td>
              <td>{phase[a.phase_id] || "—"}</td><td>{a.responsible_name || "—"}</td><td>{date(a.planned_start)}</td><td>{date(a.planned_end)}</td><td className="num">{a.is_summary ? "—" : a.duration_days}</td>
              <td className="num">{money(a.estimated_cost)}</td><td className="num">{a.weight}</td>
              <td onClick={e => e.stopPropagation()}>{a.is_summary || !write ? <span className="num">{a.is_summary ? "—" : Math.round(a.progress)}</span> :
                <input className="input inline num" type="number" min={0} max={100} step={5} defaultValue={Math.round(a.progress || 0)} key={`${a.id}-${a.progress}`} aria-label={T("نسبة الإنجاز", "Progress")}
                  onBlur={e => +e.target.value !== Math.round(a.progress || 0) && set(a, { progress: +e.target.value })} onKeyDown={e => e.key === "Enter" && (e.target as any).blur()} />}</td>
              <td><Status v={a.status} /></td><td><Src v={a.source_tag} /></td></tr>)}</tbody></table></div>}
      </section>
      <Register resource="deliverables" projectId={pid} perm="schedule.write" noun={["مخرجاً", "Deliverable"]} title={T("سجل المخرجات", "Deliverables")}
        cols={[{ key: "name", label: ["المخرج", "Deliverable"] }, { key: "due_date", label: ["الاستحقاق", "Due"], type: "date" }, { key: "acceptance_criteria", label: ["معيار القبول", "Acceptance criterion"] }, { key: "status", label: ["الحالة", "Status"], type: "status" }, { key: "source_tag", label: ["المصدر", "Source"], type: "src" }]}
        fields={[{ key: "name", label: ["اسم المخرج", "Deliverable name"], required: true, wide: true }, { key: "phase_id", label: ["المرحلة", "Phase"], type: "select", options: s.phases.map((p: any) => [p.id, p.name]) },
          { key: "due_date", label: ["الاستحقاق", "Due date"], type: "date" }, { key: "status", label: ["الحالة", "Status"], type: "select", def: "planned", options: [["planned", T("مخطط", "Planned")], ["in_progress", T("جارٍ", "In progress")], ["approved", T("معتمد", "Approved")]] },
          { key: "acceptance_criteria", label: ["معيار القبول", "Acceptance criterion"], wide: true }, { key: "description", label: ["الوصف", "Description"], type: "textarea" }]} />
      {open && <ActivityModal pid={pid} s={s} act={open} onClose={() => setOpen(null)} onSaved={q.reload} />}
    </div>;
  }}</Async>;
}
