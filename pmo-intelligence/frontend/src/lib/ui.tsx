import { ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, Check, Inbox, Pencil, Plus, Trash2, X } from "lucide-react";
import { api, STATUS, useApp, useLoad } from "./core";

export type L2 = [string, string];
export interface FieldSpec {
  key: string; label: L2; type?: "text" | "textarea" | "number" | "date" | "select" | "scale" | "bool" | "multi";
  options?: [any, string][] | (() => [any, string][]); required?: boolean; wide?: boolean; def?: any; hint?: L2; showIf?: (v: any) => boolean;
}
export interface ColSpec { key: string; label: L2; type?: "num" | "money" | "date" | "status" | "pct" | "src"; render?: (row: any) => ReactNode; width?: string; }

export function Status({ v }: { v: string | null | undefined }) {
  const { T } = useApp();
  if (!v) return <span className="muted">—</span>;
  const s = STATUS[v];
  return <span className={`tag ${s?.[2] || ""}`}>{s ? T(s[0], s[1]) : v}</span>;
}
export function Src({ v }: { v?: string }) {
  const { T } = useApp();
  const m: Record<string, L2> = { extracted: ["مستخرجة", "Extracted"], ai: ["مقترحة بالذكاء الاصطناعي", "AI generated"], user: ["مدخلة", "User defined"], calculated: ["محسوبة", "System calculated"] };
  if (!v || !m[v]) return null;
  return <span className={`src ${v}`}>{T(...m[v])}</span>;
}
export function Loading() { const { T } = useApp(); return <div className="loading"><i className="spin" />{T("جارٍ التحميل…", "Loading…")}</div>; }
export function ErrorBox({ error, retry }: { error: string; retry?: () => void }) {
  const { T } = useApp();
  return <div className="note critical"><AlertTriangle />
    <div className="grow">{error === "NETWORK" ? T("تعذر الاتصال بالخادم.", "Cannot reach the server.") : error}</div>
    {retry && <button className="btn sm" onClick={retry}>{T("أعد المحاولة", "Try again")}</button>}</div>;
}
export function Empty({ children, action }: { children: ReactNode; action?: ReactNode }) { return <div className="empty"><Inbox size={26} strokeWidth={1.4} /><div>{children}</div>{action}</div>; }
export function Async({ q, children }: { q: { data: any; error: string | null; loading: boolean; reload: () => any }; children: (d: any) => ReactNode }) {
  if (q.error) return <ErrorBox error={q.error} retry={q.reload} />;
  if (q.data === null) return <Loading />;
  return <>{children(q.data)}</>;
}

export function Modal({ title, onClose, children, footer, wide }: { title: ReactNode; onClose: () => void; children: ReactNode; footer?: ReactNode; wide?: boolean }) {
  const { T } = useApp();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", k);
    ref.current?.querySelector<HTMLElement>("input,select,textarea,button.primary")?.focus();
    return () => document.removeEventListener("keydown", k);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return (
    <div className="modal-back" onMouseDown={e => e.target === e.currentTarget && onClose()}>
      <div className={`modal ${wide ? "wide" : ""}`} role="dialog" aria-modal="true" ref={ref}>
        <header><h2>{title}</h2><button className="btn ghost icon" onClick={onClose} aria-label={T("إغلاق", "Close")}><X /></button></header>
        <div className="body">{children}</div>
        {footer && <footer>{footer}</footer>}
      </div>
    </div>
  );
}

export function Tabs({ tabs, value, onChange }: { tabs: [string, string][]; value: string; onChange: (v: string) => void }) {
  return <div className="tabs" role="tablist">{tabs.map(([k, l]) => <button key={k} role="tab" aria-selected={value === k} onClick={() => onChange(k)}>{l}</button>)}</div>;
}

export function Input({ f, value, onChange }: { f: FieldSpec; value: any; onChange: (v: any) => void }) {
  const { T } = useApp();
  const opts = typeof f.options === "function" ? f.options() : f.options || [];
  const v = value ?? "";
  if (f.type === "textarea") return <textarea className="input" value={v} onChange={e => onChange(e.target.value)} dir="auto" />;
  if (f.type === "select") return <select className="input" value={v} onChange={e => onChange(e.target.value === "" ? null : isNaN(+e.target.value) || e.target.value.trim() === "" ? e.target.value : typeof opts[0]?.[0] === "number" ? +e.target.value : e.target.value)}>
    {!f.required && <option value="">{T("— غير محدد —", "— None —")}</option>}{opts.map(([k, l]) => <option key={String(k)} value={k}>{l}</option>)}</select>;
  if (f.type === "scale") return <select className="input" value={v || 3} onChange={e => onChange(+e.target.value)}>{[1, 2, 3, 4, 5].map(n => <option key={n} value={n}>{n} — {[T("ضعيف جداً", "Very low"), T("ضعيف", "Low"), T("متوسط", "Medium"), T("عالٍ", "High"), T("عالٍ جداً", "Very high")][n - 1]}</option>)}</select>;
  if (f.type === "bool") return <label className="row"><input type="checkbox" checked={!!value} onChange={e => onChange(e.target.checked)} /> {T("نعم", "Yes")}</label>;
  if (f.type === "multi") {
    const cur: any[] = Array.isArray(value) ? value : [];
    return <div className="row">{opts.map(([k, l]) => <label key={String(k)} className="tag" style={{ cursor: "pointer" }}>
      <input type="checkbox" checked={cur.includes(k)} onChange={e => onChange(e.target.checked ? [...cur, k] : cur.filter(x => x !== k))} /> {l}</label>)}</div>;
  }
  return <input className="input" type={f.type === "number" ? "number" : f.type === "date" ? "date" : "text"} step="any" value={f.type === "date" ? String(v).slice(0, 10) : v}
    dir={f.type === "number" || f.type === "date" ? "ltr" : "auto"} onChange={e => onChange(f.type === "number" ? (e.target.value === "" ? null : +e.target.value) : e.target.value)} />;
}

export function Form({ fields, value, onChange }: { fields: FieldSpec[]; value: any; onChange: (v: any) => void }) {
  const { T } = useApp();
  return <div className="form-grid">{fields.filter(f => !f.showIf || f.showIf(value)).map(f =>
    <label key={f.key} className={`field ${f.wide || f.type === "textarea" || f.type === "multi" ? "wide" : ""}`}>
      <span>{T(...f.label)}{f.required && <em> *</em>}</span>
      <Input f={f} value={value[f.key]} onChange={v => onChange({ ...value, [f.key]: v })} />
      {f.hint && <small className="muted">{T(...f.hint)}</small>}
    </label>)}</div>;
}

export function FormModal({ title, fields, initial, onSave, onClose, saveLabel }: { title: string; fields: FieldSpec[]; initial: any; onSave: (v: any) => Promise<any>; onClose: () => void; saveLabel?: string }) {
  const { T, fail } = useApp();
  const [v, setV] = useState(() => { const o = { ...initial }; fields.forEach(f => { if (o[f.key] === undefined && f.def !== undefined) o[f.key] = f.def; }); return o; });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const submit = async () => {
    const miss = fields.filter(f => f.required && (!f.showIf || f.showIf(v)) && (v[f.key] === undefined || v[f.key] === null || v[f.key] === ""));
    if (miss.length) { setErr(T("أكمل الحقول المطلوبة: ", "Complete the required fields: ") + miss.map(f => T(...f.label)).join(T("، ", ", "))); return; }
    setBusy(true);
    try { await onSave(v); onClose(); } catch (e: any) { e.message === "NETWORK" ? fail(e) : setErr(e.message); } finally { setBusy(false); }
  };
  return <Modal title={title} onClose={onClose} footer={<>
    <button className="btn" onClick={onClose}>{T("إلغاء", "Cancel")}</button>
    <button className="btn primary" onClick={submit} disabled={busy}>{busy && <i className="spin" />}{saveLabel || T("حفظ", "Save")}</button></>}>
    <form onSubmit={e => { e.preventDefault(); submit(); }} className="stack">
      {err && <div className="note critical" role="alert"><AlertTriangle />{err}</div>}
      <Form fields={fields} value={v} onChange={setV} />
      <button type="submit" hidden />
    </form>
  </Modal>;
}

export function Confirm({ title, text, onYes, onClose, yes, danger = true }: { title: string; text: ReactNode; onYes: () => Promise<any>; onClose: () => void; yes?: string; danger?: boolean }) {
  const { T, fail } = useApp();
  const [busy, setBusy] = useState(false);
  return <Modal title={title} onClose={onClose} footer={<>
    <button className="btn" onClick={onClose}>{T("إلغاء", "Cancel")}</button>
    <button className={`btn ${danger ? "danger" : "primary"}`} disabled={busy} onClick={async () => { setBusy(true); try { await onYes(); onClose(); } catch (e) { fail(e); setBusy(false); } }}>{yes || T("حذف", "Delete")}</button></>}>
    <p>{text}</p></Modal>;
}

export function Cell({ c, row }: { c: ColSpec; row: any }) {
  const a = useApp();
  if (c.render) return <>{c.render(row)}</>;
  const v = row[c.key];
  if (c.type === "status") return <Status v={v} />;
  if (c.type === "src") return <Src v={v} />;
  if (c.type === "money") return <>{a.money(v)}</>;
  if (c.type === "num") return <>{a.num(v, Number.isInteger(v) || v == null ? 0 : 1)}</>;
  if (c.type === "pct") return <>{a.pct(v)}</>;
  if (c.type === "date") return <>{a.date(v)}</>;
  return <span dir="auto">{v === null || v === undefined || v === "" ? "—" : String(v)}</span>;
}

export function DataTable({ cols, rows, onRow, actions, empty }: { cols: ColSpec[]; rows: any[]; onRow?: (r: any) => void; actions?: (r: any) => ReactNode; empty?: ReactNode }) {
  const { T } = useApp();
  if (!rows.length) return <Empty>{empty || T("لا توجد سجلات بعد.", "No records yet.")}</Empty>;
  return <div className="tbl-wrap"><table className="tbl"><thead><tr>
    {cols.map(c => <th key={c.key} className={["num", "money", "pct"].includes(c.type || "") ? "num" : ""} style={{ width: c.width }}>{T(...c.label)}</th>)}{actions && <th />}</tr></thead>
    <tbody>{rows.map((r, i) => <tr key={r.id ?? i} className={onRow ? "click" : ""} onClick={onRow ? () => onRow(r) : undefined}>
      {cols.map(c => <td key={c.key} className={["num", "money", "pct"].includes(c.type || "") ? "num" : ""}><Cell c={c} row={r} /></td>)}
      {actions && <td className="act" onClick={e => e.stopPropagation()}>{actions(r)}</td>}</tr>)}</tbody></table></div>;
}

/** Generic register: list + add + edit + delete for one resource, honouring permissions. */
export function Register({ resource, projectId, cols, fields, title, perm, noun, extraActions, filter, sub, headerExtra, onChanged, base, sort }: {
  resource: string; projectId?: number | null; cols: ColSpec[]; fields: FieldSpec[]; title?: string; perm: string; noun: L2; extraActions?: (row: any, reload: () => void) => ReactNode;
  filter?: (r: any) => boolean; sub?: string; headerExtra?: ReactNode; onChanged?: () => void; base?: any; sort?: (a: any, b: any) => number;
}) {
  const { T, can, toast } = useApp();
  const q = useLoad<any[]>(`/r/${resource}${projectId ? `?project_id=${projectId}` : ""}`);
  const [edit, setEdit] = useState<any>(null);
  const [del, setDel] = useState<any>(null);
  const write = can(perm);
  const rows = useMemo(() => { let r = (q.data || []).filter(filter || (() => true)); if (sort) r = [...r].sort(sort); return r; }, [q.data, filter, sort]);
  const changed = () => { q.reload(); onChanged?.(); };
  const save = async (v: any) => {
    if (v.id) await api.patch(`/r/${resource}/${v.id}`, v); else await api.post(`/r/${resource}`, { ...(base || {}), ...v, ...(projectId ? { project_id: projectId } : {}) });
    toast(T("تم الحفظ", "Saved")); changed();
  };
  const name = T(...noun);
  return <section className="panel">
    <header><div><h2>{title || name}</h2>{sub && <p>{sub}</p>}</div>
      <div className="row">{headerExtra}{write && <button className="btn primary sm" onClick={() => setEdit({})}><Plus />{T("أضف", "Add")} {name}</button>}</div></header>
    <Async q={q}>{() => <DataTable cols={cols} rows={rows} onRow={write ? setEdit : undefined}
      empty={<>{T(`لا يوجد ${name} بعد.`, `No ${name.toLowerCase()} yet.`)}</>}
      actions={r => <>{extraActions?.(r, changed)}{write && <>
        <button className="btn ghost sm icon" onClick={() => setEdit(r)} aria-label={T("تعديل", "Edit")}><Pencil /></button>
        <button className="btn ghost sm icon danger" onClick={() => setDel(r)} aria-label={T("حذف", "Delete")}><Trash2 /></button></>}</>} />}</Async>
    {edit && <FormModal title={`${edit.id ? T("تعديل", "Edit") : T("إضافة", "Add")} ${name}`} fields={fields} initial={edit} onSave={save} onClose={() => setEdit(null)} />}
    {del && <Confirm title={T(`حذف ${name}`, `Delete ${name.toLowerCase()}`)} text={T(`سيحذف «${del.name || del.title || del.name_ar || del.id}» نهائياً.`, `“${del.name || del.title || del.name_en || del.id}” will be permanently deleted.`)}
      onYes={async () => { await api.del(`/r/${resource}/${del.id}`); toast(T("تم الحذف", "Deleted")); changed(); }} onClose={() => setDel(null)} />}
  </section>;
}

export function Progress({ v, planned }: { v: number; planned?: number }) {
  const { pct } = useApp();
  return <div className="row" style={{ gap: 8, flexWrap: "nowrap" }}>
    <div className="bar grow" style={{ position: "relative", overflow: "visible" }}><i style={{ width: `${Math.min(100, v || 0)}%` }} />
      {planned !== undefined && <span title="planned" style={{ position: "absolute", top: -3, insetInlineStart: `${Math.min(100, planned)}%`, width: 2, height: 12, background: "var(--ink)" }} />}</div>
    <span className="num small">{pct(v)}</span></div>;
}
export const Yes = () => <Check size={14} />;
