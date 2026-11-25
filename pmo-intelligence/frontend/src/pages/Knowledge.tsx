import { useEffect, useRef, useState } from "react";
import { Copy, Download, Eye, FileText, GitCompare, History, MessageSquarePlus, Paperclip, RefreshCw, Send, ShieldAlert, SlidersHorizontal, Sparkles, Table2, Trash2, Upload } from "lucide-react";
import { api, saveBlob, useApp, useLoad } from "../lib/core";
import { Async, Confirm, Empty, Form, FormModal, Modal, Status } from "../lib/ui";

export const DOC_TYPES: Record<string, [string, string]> = {
  charter: ["ميثاق المشروع", "Project charter"], management_plan: ["خطة إدارة", "Management plan"], business_case: ["دراسة جدوى", "Business case"], scope_statement: ["بيان النطاق", "Scope statement"],
  requirements: ["متطلبات", "Requirements"], technical: ["وثيقة فنية", "Technical document"], contract: ["عقد", "Contract"], meeting_minutes: ["محضر اجتماع", "Meeting minutes"], progress_report: ["تقرير تقدم", "Progress report"],
  financial_report: ["تقرير مالي", "Financial report"], risk_register: ["سجل مخاطر", "Risk register"], change_request: ["طلب تغيير", "Change request"], quality_report: ["تقرير جودة", "Quality report"],
  lessons_learned: ["دروس مستفادة", "Lessons learned"], presentation: ["عرض تقديمي", "Presentation"], spreadsheet: ["جدول بيانات", "Spreadsheet"], other: ["أخرى", "Other"] };
const CONF: [string, string][] = [["عام", "Public"], ["داخلي", "Internal"], ["سري", "Confidential"], ["مقيد", "Restricted"]];
const KIND: Record<string, [string, string]> = { documented: ["موثق في المستندات", "Documented in the files"], inferred: ["استنتاج من عدة مصادر", "Inferred from several sources"], analysis: ["تحليل وتوصيات مولدة", "Generated analysis and recommendations"],
  system: ["من بيانات النظام", "From system data"], calculated: ["محسوب بالمحركات الحسابية", "Calculated by the engines"], security: ["تنبيه أمني", "Security notice"], not_found: ["لا يوجد دليل", "No evidence"] };

/* ---------- document viewer: citations open here, at the cited passage ---------- */
export function Viewer({ docId, version, chunkId, snippet, onClose }: { docId: number; version?: number | null; chunkId?: number; snippet?: string; onClose: () => void }) {
  const { T } = useApp();
  const q = useLoad<any>(`/documents/${docId}/content${version ? `?version=${version}` : ""}`);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => { if (q.data) setTimeout(() => ref.current?.querySelector("[data-hit]")?.scrollIntoView({ block: "center" }), 60); }, [q.data]);
  const mark = (text: string) => { if (!snippet) return text; const key = snippet.replace(/^[^:：]{0,40}[:：]\s*/, "").slice(0, 50); const i = key.length > 6 ? text.indexOf(key) : -1; return i < 0 ? text : <>{text.slice(0, i)}<mark>{text.slice(i, i + key.length)}</mark>{text.slice(i + key.length)}</>; };
  return <Modal wide title={q.data ? `${q.data.document.name} — ${T("الإصدار", "version")} ${q.data.version}` : T("الوثيقة", "Document")} onClose={onClose}>
    <Async q={q}>{d => { let page = 0; return <div ref={ref} className="stack tight">{d.chunks.map((c: any) => <div key={c.id}>
      {c.page !== page && (page = c.page) && <div className="row small muted" style={{ borderBlockEnd: "1px solid var(--line)", marginBlock: "10px 6px" }}>{T("الصفحة", "Page")} <bdi>{c.page}</bdi></div>}
      <div data-hit={c.id === chunkId ? "" : undefined} style={{ padding: "6px 10px", borderRadius: 4, background: c.id === chunkId ? "var(--accent-soft)" : "transparent", borderInlineStart: c.flagged ? "3px solid var(--critical)" : "3px solid transparent" }} dir="auto">
        {c.section && <div className="small strong">{c.section}</div>}
        {c.flagged && <div className="small" style={{ color: "var(--critical)" }}><ShieldAlert size={13} /> {T("مقطع يشبه تعليمات موجهة للنظام؛ لا يُستخدم في الإجابات.", "This passage looks like instructions to the system; it is never used in answers.")}</div>}
        {c.kind === "table" ? <div className="tbl-wrap"><table className="tbl"><tbody>{c.text.split("\n").map((r: string, i: number) => <tr key={i}>{r.split("|").map((x, j) => <td key={j}>{x.trim()}</td>)}</tr>)}</tbody></table></div>
          : <p style={{ whiteSpace: "pre-wrap" }}>{c.id === chunkId ? mark(c.text) : c.text}</p>}</div></div>)}</div>; }}</Async>
  </Modal>;
}

/* ---------- one assistant message: labelled blocks + sources ---------- */
export function Answer({ msg, title }: { msg: any; title?: string }) {
  const { T, lang, date, fail, toast } = useApp();
  const [view, setView] = useState<any>(null);
  const cites: any[] = msg.citations || [];
  const exportAs = async (format: string) => {
    try { saveBlob(await api.blob("/export", { format, lang, title: title || "AI-Powered PMO Platform", text: (msg.blocks || []).map((b: any) => b.text).join("\n"), citations: cites,
      tables: (msg.blocks || []).filter((b: any) => b.table).map((b: any) => ({ title: b.text, ...b.table })) }), `answer.${format}`); } catch (e) { fail(e); }
  };
  return <div className="msg">
    {(msg.blocks || []).map((b: any, i: number) => <div key={i} className={`blk ${b.kind}`}>
      <span className="small muted">{T(...(KIND[b.kind] || ["", ""]))}</span>
      <pre dir="auto">{b.text}</pre>
      {b.table && <div className="tbl-wrap"><table className="tbl"><thead><tr>{b.table.head.map((h: string, j: number) => <th key={j}>{h}</th>)}</tr></thead>
        <tbody>{b.table.rows.map((r: any[], j: number) => <tr key={j}>{r.map((c, k) => <td key={k} dir="auto">{c === null ? "—" : String(c)}</td>)}</tr>)}</tbody></table></div>}
    </div>)}
    {cites.length > 0 && <div className="stack tight"><span className="small strong">{T("المصادر", "Sources")}</span>
      {cites.map((c: any) => <button key={c.n} className="cite" onClick={() => setView(c)}>
        <span><b className="ltr">[{c.n}]</b> <FileText size={13} /> {c.document}{c.version ? <> · {T("الإصدار ", "v")}<bdi>{c.version}</bdi></> : null} · {T("الصفحة", "page")} <bdi>{c.page ?? "—"}</bdi>{c.section ? <> · {c.section}</> : null}{c.doc_date ? <> · {date(c.doc_date)}</> : null}</span>
        <q dir="auto">{c.snippet}</q></button>)}</div>}
    <div className="row no-print">
      <button className="btn ghost sm" onClick={() => navigator.clipboard.writeText(msg.content || "").then(() => toast(T("نُسخت الإجابة", "Answer copied")))}><Copy />{T("انسخ", "Copy")}</button>
      {["docx", "pdf", "xlsx"].map(f => <button key={f} className="btn ghost sm" onClick={() => exportAs(f)}><Download />{f === "docx" ? "Word" : f === "pdf" ? "PDF" : "Excel"}</button>)}</div>
    {view && <Viewer docId={view.document_id} version={view.version} chunkId={view.chunk_id} snippet={view.snippet} onClose={() => setView(null)} />}
  </div>;
}

/* ---------- chat ---------- */
export function Chat({ pid }: { pid: number }) {
  const { T, can, fail, date, toast } = useApp();
  const convs = useLoad<any[]>(`/projects/${pid}/conversations`);
  const docs = useLoad<any[]>(`/projects/${pid}/documents`);
  const [cid, setCid] = useState<number | null>(null);
  const [conv, setConv] = useState<any>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [scope, setScope] = useState<any>({ doc_ids: [], date_from: "", date_to: "", versions: "current" });
  const [showScope, setShowScope] = useState(false);
  const [del, setDel] = useState<any>(null);
  const log = useRef<HTMLDivElement>(null);
  const file = useRef<HTMLInputElement>(null);
  useEffect(() => { if (cid) api.get(`/conversations/${cid}`).then(setConv).catch(fail); else setConv(null); }, [cid]);  // eslint-disable-line
  useEffect(() => { log.current?.scrollTo({ top: log.current.scrollHeight }); }, [conv?.messages?.length, busy]);
  const ask = async (q: string) => {
    if (!q.trim() || busy) return;
    setBusy(true); setText("");
    try {
      let id = cid;
      if (!id) { const c = await api.post(`/projects/${pid}/conversations`); id = c.id; setCid(id); }
      setConv((c: any) => ({ ...(c || { messages: [] }), messages: [...(c?.messages || []), { id: -1, role: "user", content: q }] }));
      await api.post(`/conversations/${id}/messages`, { question: q, ...scope, doc_ids: scope.doc_ids.length ? scope.doc_ids : null });
      setConv(await api.get(`/conversations/${id}`)); convs.reload();
    } catch (e) { fail(e); } finally { setBusy(false); }
  };
  const attach = async (f?: File) => {
    if (!f) return; const fd = new FormData(); fd.append("file", f);
    try { const d = await api.post(`/projects/${pid}/documents`, fd); docs.reload(); toast(d.processing_status === "indexed" ? T(`فُهرس «${d.name}» وأصبح متاحاً للمحادثة`, `“${d.name}” indexed and available to the chat`) : d.processing_error, d.processing_status === "indexed" ? "ok" : "error"); } catch (e) { fail(e); }
  };
  const ideas: [string, string][] = [["ما الأهداف الرئيسية للمشروع؟", "What are the main project objectives?"], ["ما الميزانية المعتمدة؟", "What is the approved budget?"], ["ما القرارات التي اتخذت في آخر اجتماع؟", "What was decided in the last meeting?"],
    ["ما الأنشطة التي تقع على المسار الحرج؟", "Which activities are on the critical path?"], ["هل توجد تعارضات بين الوثائق؟", "Are there conflicts between the documents?"], ["لخص الوضع الحالي للمشروع بناءً على أحدث الوثائق", "Summarise the current status from the latest documents"]];
  const indexed = (docs.data || []).filter(d => d.processing_status === "indexed");
  if (!can("chat.use")) return <div className="note warning">{T("دورك لا يتيح استخدام محادثة المشروع.", "Your role does not include the project chat.")}</div>;
  return <div className="chat">
    <aside className="panel"><header><h3>{T("المحادثات", "Conversations")}</h3><button className="btn sm" onClick={() => setCid(null)}><MessageSquarePlus />{T("جديدة", "New")}</button></header>
      <div style={{ maxHeight: "60vh", overflowY: "auto" }}>{(convs.data || []).map(c => <div key={c.id} className="row" style={{ padding: "6px 10px", gap: 4, background: c.id === cid ? "var(--raised)" : undefined, flexWrap: "nowrap" }}>
        <button style={{ all: "unset", cursor: "pointer", flex: 1, minWidth: 0, fontSize: ".86rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontWeight: c.id === cid ? 600 : 400 }} onClick={() => setCid(c.id)}>{c.title || T("محادثة بلا عنوان", "Untitled conversation")}</button>
        <button className="btn ghost sm icon" aria-label={T("حذف المحادثة", "Delete conversation")} onClick={() => setDel(c)}><Trash2 /></button></div>)}
        {convs.data?.length === 0 && <p className="muted small" style={{ padding: 12 }}>{T("محادثاتك مع وثائق هذا المشروع تظهر هنا. لا يراها غيرك.", "Your conversations with this project's documents appear here. Only you can see them.")}</p>}</div></aside>
    <section className="panel">
      <header><div><h2>{T("مساعد معرفة المشروع", "Project knowledge assistant")}</h2>
        <p>{T(`يجيب من ${indexed.length} وثيقة مفهرسة مصرح لك بها في هذا المشروع فقط، ويذكر مصدر كل معلومة.`, `Answers only from the ${indexed.length} indexed documents you may read in this project, and cites every source.`)}</p></div>
        <button className="btn sm" onClick={() => setShowScope(!showScope)} aria-expanded={showScope}><SlidersHorizontal />{T("نطاق البحث", "Search scope")}{scope.doc_ids.length ? ` (${scope.doc_ids.length})` : ""}</button></header>
      {showScope && <div className="body stack tight" style={{ borderBlockEnd: "1px solid var(--line-2)" }}>
        <div className="row">{indexed.map(d => <label key={d.id} className="tag" style={{ cursor: "pointer" }}><input type="checkbox" checked={scope.doc_ids.includes(d.id)} onChange={e => setScope({ ...scope, doc_ids: e.target.checked ? [...scope.doc_ids, d.id] : scope.doc_ids.filter((x: number) => x !== d.id) })} />{d.name}</label>)}</div>
        <div className="row small"><span>{T("وثائق مؤرخة من", "Documents dated from")}</span><input className="input" style={{ width: 150 }} type="date" value={scope.date_from} onChange={e => setScope({ ...scope, date_from: e.target.value })} aria-label={T("من تاريخ", "From date")} />
          <span>{T("إلى", "to")}</span><input className="input" style={{ width: 150 }} type="date" value={scope.date_to} onChange={e => setScope({ ...scope, date_to: e.target.value })} aria-label={T("إلى تاريخ", "To date")} />
          <select className="input" style={{ width: 190 }} value={scope.versions} onChange={e => setScope({ ...scope, versions: e.target.value })} aria-label={T("الإصدارات", "Versions")}><option value="current">{T("الإصدار الحالي فقط", "Current version only")}</option><option value="all">{T("جميع الإصدارات", "All versions")}</option></select>
          <span className="muted">{scope.doc_ids.length === 0 && T("بلا اختيار = جميع وثائق المشروع", "Nothing selected = all project documents")}</span></div></div>}
      <div className="chat-log" ref={log} aria-live="polite">
        {!conv?.messages?.length && <div className="stack"><p className="muted">{T("اسأل عن الميثاق أو الجدول أو المخاطر أو الميزانية أو محاضر الاجتماعات. جرّب:", "Ask about the charter, schedule, risks, budget or meeting minutes. Try:")}</p>
          <div className="row">{ideas.map(([a, e]) => <button key={e} className="btn sm" onClick={() => ask(T(a, e))}>{T(a, e)}</button>)}</div></div>}
        {(conv?.messages || []).map((m: any) => m.role === "user" ? <div key={m.id} className="msg user" dir="auto">{m.content}</div> : <Answer key={m.id} msg={m} title={conv.title} />)}
        {busy && <div className="row muted"><i className="spin" />{T("يبحث في الوثائق المصرح بها…", "Searching the permitted documents…")}</div>}
      </div>
      <form className="row body" style={{ borderBlockStart: "1px solid var(--line-2)" }} onSubmit={e => { e.preventDefault(); ask(text); }}>
        {can("docs.write") && <><input ref={file} type="file" hidden onChange={e => { attach(e.target.files?.[0]); e.target.value = ""; }} />
          <button type="button" className="btn icon" onClick={() => file.current?.click()} aria-label={T("أرفق ملفاً", "Attach a file")} title={T("أرفق ملفاً ليُفهرس ويُضاف إلى وثائق المشروع", "Attach a file to index it into the project documents")}><Paperclip /></button></>}
        <input className="input grow" style={{ width: "auto" }} dir="auto" value={text} onChange={e => setText(e.target.value)} placeholder={T("اكتب سؤالك عن وثائق المشروع…", "Ask about the project documents…")} aria-label={T("السؤال", "Question")} />
        <button className="btn primary" disabled={busy || !text.trim()}><Send className="flip" />{T("اسأل", "Ask")}</button>
      </form>
    </section>
    {del && <Confirm title={T("حذف المحادثة", "Delete conversation")} text={T("ستحذف المحادثة ورسائلها نهائياً.", "The conversation and its messages will be permanently deleted.")} onClose={() => setDel(null)}
      onYes={async () => { await api.del(`/conversations/${del.id}`); if (cid === del.id) setCid(null); convs.reload(); }} />}
  </div>;
}

/* ---------- documents ---------- */
export function Documents({ pid }: { pid: number }) {
  const { T, can, date, fail, toast, meta, N, user, lang } = useApp();
  const q = useLoad<any[]>(`/projects/${pid}/documents`);
  const conf = useLoad<any[]>(`/projects/${pid}/conflicts`);
  const [up, setUp] = useState(false);
  const [edit, setEdit] = useState<any>(null);
  const [view, setView] = useState<any>(null);
  const [del, setDel] = useState<any>(null);
  const [info, setInfo] = useState<any>(null);
  const [cmp, setCmp] = useState<any>({ a: "", b: "" });
  const [busy, setBusy] = useState(false);
  const [folder, setFolder] = useState("");
  const [search, setSearch] = useState("");
  const [hits, setHits] = useState<any[] | null>(null);
  const verRef = useRef<HTMLInputElement>(null);
  const verDoc = useRef<any>(null);
  const write = can("docs.write");
  const typeOpts = Object.entries(DOC_TYPES).map(([k, v]) => [k, T(...v)]) as [string, string][];
  const metaFields: any[] = [{ key: "name", label: ["اسم الوثيقة", "Document name"] }, { key: "doc_type", label: ["النوع", "Type"], type: "select", def: "other", required: true, options: typeOpts },
    { key: "doc_date", label: ["تاريخ الوثيقة", "Document date"], type: "date", hint: ["تاريخ المحتوى لا تاريخ الرفع؛ يحدد أيها الأحدث", "Date of the content, not of the upload; decides which is most recent"] },
    { key: "approval_status", label: ["حالة الاعتماد", "Approval status"], type: "select", def: "draft", required: true, options: [["draft", T("مسودة", "Draft")], ["approved", T("معتمد", "Approved")], ["superseded", T("مستبدل", "Superseded")]] },
    { key: "confidentiality", label: ["مستوى السرية", "Confidentiality"], type: "select", def: 1, required: true, options: CONF.map((c, i) => [i, T(...c)]).filter(([i]) => (i as number) <= (meta?.roles ? 3 : 3)) },
    { key: "folder", label: ["المجلد", "Folder"], def: "/" }, { key: "access_roles", label: ["أدوار محددة فقط (اختياري)", "Only these roles (optional)"], type: "multi", options: (meta?.roles || []).map((r: any) => [r.key, N(r)]) }];
  const upload = async (v: any) => {
    if (!v.file) throw new Error(T("اختر ملفاً.", "Choose a file."));
    const fd = new FormData(); fd.append("file", v.file);
    ["name", "doc_type", "doc_date", "approval_status", "confidentiality", "folder"].forEach(k => v[k] !== undefined && v[k] !== null && fd.append(k, String(v[k])));
    fd.append("access_roles", (v.access_roles || []).join(",")); fd.append("tags", v.tags || "");
    const d = await api.post(`/projects/${pid}/documents`, fd);
    q.reload(); toast(d.processing_status === "indexed" ? T("رُفعت الوثيقة وفُهرست", "Document uploaded and indexed") : d.processing_error, d.processing_status === "indexed" ? "ok" : "error");
  };
  const act = async (fn: () => Promise<any>, msg?: string) => { setBusy(true); try { const r = await fn(); msg && toast(msg); q.reload(); return r; } catch (e) { fail(e); } finally { setBusy(false); } };
  const folders = [...new Set((q.data || []).map(d => d.folder || "/"))].sort();
  const rows = (q.data || []).filter(d => !folder || d.folder === folder);
  return <div className="stack">
    <section className="panel"><header><div><h2>{T("قاعدة معرفة المشروع", "Project knowledge base")}</h2><p>{T("كل ملف يُحلَّل ويُقسَّم ويُفهرس على هذا الخادم، ويبقى معزولاً داخل هذا المشروع.", "Every file is parsed, chunked and indexed on this server, and stays isolated inside this project.")}</p></div>
      <div className="row"><form className="row" onSubmit={e => { e.preventDefault(); search.trim() ? api.get(`/projects/${pid}/knowledge/search?q=${encodeURIComponent(search)}`).then(setHits).catch(fail) : setHits(null); }}>
        <input className="input" style={{ width: 220 }} value={search} onChange={e => setSearch(e.target.value)} placeholder={T("ابحث داخل الوثائق…", "Search inside documents…")} aria-label={T("بحث في المحتوى", "Content search")} /></form>
        {folders.length > 1 && <select className="input" style={{ width: 150 }} value={folder} onChange={e => setFolder(e.target.value)} aria-label={T("المجلد", "Folder")}><option value="">{T("كل المجلدات", "All folders")}</option>{folders.map(f => <option key={f}>{f}</option>)}</select>}
        {write && <button className="btn primary sm" onClick={() => setUp(true)}><Upload />{T("ارفع وثيقة", "Upload document")}</button>}</div></header>
      {hits && <div className="body stack tight" style={{ borderBlockEnd: "1px solid var(--line-2)" }}><div className="row"><b>{T(`${hits.length} مقطع مطابق`, `${hits.length} matching passages`)}</b><button className="btn ghost sm" onClick={() => setHits(null)}>{T("أغلق النتائج", "Close results")}</button></div>
        {hits.map(h => <button key={h.chunk_id} className="cite" onClick={() => setView({ id: h.document_id, chunk: h.chunk_id })}><span><FileText size={13} /> {h.document} · {T("الصفحة", "page")} <bdi>{h.page}</bdi>{h.section ? ` · ${h.section}` : ""} <span className="muted ltr">({T("تطابق", "match")} {Math.round(h.coverage * 100)}%)</span></span><q dir="auto">{h.text}</q></button>)}
        {!hits.length && <p className="muted">{T("لا نتائج في الوثائق المصرح لك بها.", "No results in the documents you may read.")}</p>}</div>}
      <Async q={q}>{() => rows.length === 0 ? <Empty action={write && <button className="btn primary" onClick={() => setUp(true)}><Upload />{T("ارفع أول وثيقة", "Upload the first document")}</button>}>{T("لا وثائق في هذا المشروع بعد.", "No documents in this project yet.")}</Empty> :
        <div className="tbl-wrap"><table className="tbl"><thead><tr><th>{T("الوثيقة", "Document")}</th><th>{T("النوع", "Type")}</th><th>{T("تاريخ الوثيقة", "Document date")}</th><th>{T("الإصدار", "Version")}</th><th>{T("الاعتماد", "Approval")}</th><th>{T("السرية", "Confidentiality")}</th><th>{T("المعالجة", "Processing")}</th><th /></tr></thead>
          <tbody>{rows.map(d => <tr key={d.id}><td><button className="btn ghost sm" style={{ paddingInline: 0, whiteSpace: "normal", textAlign: "start" }} onClick={() => setView({ id: d.id })}><FileText />{d.name}</button>
            <div className="small muted">{d.folder} · {d.pages} {T("صفحة", "page(s)")} · <bdi>{d.language}</bdi>{d.source_tag === "ai" && <> · {T("مسودة مولدة", "generated draft")}</>}</div></td>
            <td>{T(...(DOC_TYPES[d.doc_type] || DOC_TYPES.other))}</td><td>{date(d.doc_date)}</td><td className="num">{d.current_version}</td><td><Status v={d.approval_status} /></td>
            <td><span className={`tag ${d.confidentiality >= 2 ? "serious" : ""}`}>{T(...CONF[d.confidentiality] || CONF[1])}</span>{d.access_roles?.length > 0 && <span className="tag" title={d.access_roles.join(", ")}>{T("أدوار محددة", "Role-limited")}</span>}</td>
            <td><Status v={d.processing_status} />{d.processing_error && <div className="small" style={{ color: "var(--critical)", maxWidth: 260 }}>{d.processing_error}</div>}</td>
            <td className="act"><button className="btn ghost sm icon" title={T("ملخص", "Summary")} aria-label={T("ملخص", "Summary")} onClick={() => api.get(`/documents/${d.id}/summary`).then(s => setInfo({ kind: "summary", doc: d, ...s })).catch(fail)}><Sparkles /></button>
              <button className="btn ghost sm icon" title={T("الجداول", "Tables")} aria-label={T("الجداول", "Tables")} onClick={() => api.get(`/documents/${d.id}/tables`).then(t => setInfo({ kind: "tables", doc: d, tables: t })).catch(fail)}><Table2 /></button>
              <button className="btn ghost sm icon" title={T("الإصدارات", "Versions")} aria-label={T("الإصدارات", "Versions")} onClick={() => setInfo({ kind: "versions", doc: d })}><History /></button>
              <button className="btn ghost sm icon" title={T("تنزيل", "Download")} aria-label={T("تنزيل", "Download")} onClick={() => api.blob(`/documents/${d.id}/download`).then(b => saveBlob(b, d.versions[d.versions.length - 1].filename)).catch(fail)}><Download /></button>
              {write && <><button className="btn ghost sm icon" title={T("أعد الفهرسة", "Re-index")} aria-label={T("أعد الفهرسة", "Re-index")} disabled={busy} onClick={() => act(() => api.post(`/documents/${d.id}/reindex`), T("أعيدت الفهرسة", "Re-indexed"))}><RefreshCw /></button>
                <button className="btn ghost sm icon" title={T("خصائص", "Properties")} aria-label={T("خصائص", "Properties")} onClick={() => setEdit(d)}><Eye /></button>
                <button className="btn ghost sm icon danger" aria-label={T("حذف", "Delete")} onClick={() => setDel(d)}><Trash2 /></button></>}</td></tr>)}</tbody></table></div>}</Async>
    </section>

    <section className="panel"><header><div><h2>{T("مقارنة الوثائق واكتشاف التعارضات", "Compare documents and find conflicts")}</h2><p>{T("تُعرض الاختلافات للمراجعة. لا تُستبدل أي قيمة تلقائياً.", "Differences are shown for review. No value is ever replaced automatically.")}</p></div>
      <div className="row">{["a", "b"].map(k => <select key={k} className="input" style={{ width: 210 }} value={cmp[k]} onChange={e => setCmp({ ...cmp, [k]: e.target.value })} aria-label={k === "a" ? T("الوثيقة الأولى", "First document") : T("الوثيقة الثانية", "Second document")}>
        <option value="">{k === "a" ? T("الوثيقة الأولى…", "First document…") : T("الوثيقة الثانية…", "Second document…")}</option>{(q.data || []).filter(d => d.processing_status === "indexed").map(d => <option key={d.id} value={d.id}>{d.name}</option>)}</select>)}
        <button className="btn" disabled={!cmp.a || !cmp.b || cmp.a === cmp.b || busy} onClick={() => act(() => api.post(`/projects/${pid}/documents/compare`, { a: +cmp.a, b: +cmp.b })).then(r => { conf.reload(); r && toast(r.length ? T(`وُجد ${r.length} اختلاف`, `${r.length} difference(s) found`) : T("لا اختلافات في البنود القابلة للمقارنة", "No differences in the comparable items")); })}><GitCompare />{T("قارن", "Compare")}</button></div></header>
      <Async q={conf}>{rows => rows.length === 0 ? <div className="empty">{T("لم تُسجل تعارضات. اختر وثيقتين وقارن بينهما.", "No conflicts recorded. Choose two documents and compare them.")}</div> :
        <div className="tbl-wrap"><table className="tbl"><thead><tr><th>{T("نوع التعارض", "Conflict")}</th><th>{T("الوثيقة الأولى", "First document")}</th><th>{T("قيمتها", "Its value")}</th><th>{T("الوثيقة الثانية", "Second document")}</th><th>{T("قيمتها", "Its value")}</th><th>{T("الأهمية", "Severity")}</th><th>{T("التوصية", "Recommendation")}</th><th>{T("حالة المراجعة", "Review")}</th></tr></thead>
          <tbody>{rows.map((c: any) => <tr key={c.id}><td>{T(c.source_a?.label_ar || c.conflict_type, c.source_a?.label_en || c.conflict_type)}</td><td>{c.doc_a}<div className="small muted">{date(c.source_a?.date)}</div></td><td dir="auto" className="strong">{c.value_a}</td>
            <td>{c.doc_b}<div className="small muted">{date(c.source_b?.date)}</div></td><td dir="auto" className="strong">{c.value_b}</td><td><Status v={c.severity} /></td><td className="small" style={{ minWidth: 220 }}>{(c.recommendation || "").split("\n")[lang === "ar" ? 0 : 1]}</td>
            <td>{write ? <select className="input inline" style={{ width: 170 }} value={c.review_status} onChange={e => api.patch(`/conflicts/${c.id}`, { review_status: e.target.value }).then(() => conf.reload()).catch(fail)} aria-label={T("حالة المراجعة", "Review status")}>
              <option value="open">{T("بانتظار المراجعة", "Awaiting review")}</option><option value="accepted_a">{T("اعتُمدت قيمة الأولى", "First value accepted")}</option><option value="accepted_b">{T("اعتُمدت قيمة الثانية", "Second value accepted")}</option><option value="dismissed">{T("ليس تعارضاً", "Not a conflict")}</option></select> : c.review_status}</td></tr>)}</tbody></table></div>}</Async>
    </section>

    <input ref={verRef} type="file" hidden onChange={e => { const f = e.target.files?.[0]; e.target.value = ""; if (!f) return; const fd = new FormData(); fd.append("file", f); fd.append("note", `${user?.name_en || ""} ${new Date().toISOString().slice(0, 10)}`);
      act(() => api.post(`/documents/${verDoc.current.id}/versions`, fd), T("رُفع إصدار جديد وأعيدت فهرسته", "New version uploaded and indexed")).then(d => d && setInfo({ kind: "versions", doc: d })); }} />
    {up && <UploadModal fields={metaFields} onSave={upload} onClose={() => setUp(false)} />}
    {edit && <FormModal title={T("خصائص الوثيقة", "Document properties")} fields={metaFields} initial={edit} onClose={() => setEdit(null)} onSave={async v => { await api.patch(`/documents/${edit.id}`, v); q.reload(); }} />}
    {view && <Viewer docId={view.id} chunkId={view.chunk} version={view.version} onClose={() => setView(null)} />}
    {del && <Confirm title={T("حذف الوثيقة", "Delete document")} text={T(`ستحذف «${del.name}» بكل إصداراتها وتُزال من الفهرس.`, `“${del.name}” and all its versions will be deleted and removed from the index.`)} onClose={() => setDel(null)} onYes={async () => { await api.del(`/documents/${del.id}`); q.reload(); conf.reload(); }} />}
    {info?.kind === "summary" && <Modal wide title={`${T("ملخص", "Summary")} — ${info.doc.name}`} onClose={() => setInfo(null)}><Answer msg={{ blocks: [{ kind: "documented", text: info.text || T("لا محتوى كافٍ للتلخيص.", "Not enough content to summarise.") }], citations: info.citations, content: info.text }} title={info.doc.name} /></Modal>}
    {info?.kind === "tables" && <Modal wide title={`${T("الجداول المستخرجة", "Extracted tables")} — ${info.doc.name}`} onClose={() => setInfo(null)}><div className="stack">
      {info.tables.length === 0 && <p className="muted">{T("لا جداول في هذه الوثيقة.", "No tables in this document.")}</p>}
      {info.tables.map((t: any, i: number) => <div key={i}><div className="small muted">{T("الصفحة", "Page")} <bdi>{t.page}</bdi> · {t.section}</div><div className="tbl-wrap"><table className="tbl"><tbody>{t.rows.map((r: string[], j: number) => <tr key={j}>{r.map((c, k) => j === 0 ? <th key={k}>{c}</th> : <td key={k}>{c}</td>)}</tr>)}</tbody></table></div></div>)}</div></Modal>}
    {info?.kind === "versions" && <Versions doc={info.doc} write={write} onClose={() => setInfo(null)} onView={v => setView({ id: info.doc.id, version: v })} onNew={() => { verDoc.current = info.doc; verRef.current?.click(); }} />}
  </div>;
}

function UploadModal({ fields, onSave, onClose }: { fields: any[]; onSave: (v: any) => Promise<any>; onClose: () => void }) {
  const { T } = useApp();
  return <Modal title={T("رفع وثيقة", "Upload a document")} onClose={onClose}><UploadForm fields={fields} onSave={onSave} onClose={onClose} /></Modal>;
}
function UploadForm({ fields, onSave, onClose }: { fields: any[]; onSave: (v: any) => Promise<any>; onClose: () => void }) {
  const { T, fail } = useApp();
  const [v, setV] = useState<any>({ doc_type: "other", approval_status: "draft", confidentiality: 1, folder: "/" });
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [over, setOver] = useState(false);
  const submit = async () => { if (!file) return setErr(T("اختر ملفاً أولاً.", "Choose a file first.")); setBusy(true); setErr(""); try { await onSave({ ...v, file }); onClose(); } catch (e: any) { e.message === "NETWORK" ? fail(e) : setErr(e.message); } finally { setBusy(false); } };
  return <div className="stack">
    {err && <div className="note critical" role="alert">{err}</div>}
    <label className={`drop ${over ? "over" : ""}`} onDragOver={e => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)} onDrop={e => { e.preventDefault(); setOver(false); setFile(e.dataTransfer.files[0] || null); }}>
      <Upload size={22} /><b>{file ? file.name : T("اسحب الملف هنا أو اضغط للاختيار", "Drop the file here or select to choose")}</b>
      <span className="small muted">PDF · DOCX · DOC · XLSX · XLS · PPTX · TXT</span><input type="file" hidden accept=".pdf,.docx,.doc,.xlsx,.xls,.pptx,.txt,.md,.csv" onChange={e => setFile(e.target.files?.[0] || null)} /></label>
    <Form fields={fields} value={v} onChange={setV} />
    <div className="row end"><button className="btn" onClick={onClose}>{T("إلغاء", "Cancel")}</button><button className="btn primary" disabled={busy} onClick={submit}>{busy && <i className="spin" />}{T("ارفع وفهرس", "Upload and index")}</button></div>
  </div>;
}

function Versions({ doc, write, onClose, onView, onNew }: { doc: any; write: boolean; onClose: () => void; onView: (v: number) => void; onNew: () => void }) {
  const { T, date, fail } = useApp();
  const [diff, setDiff] = useState<any>(null);
  const vs = doc.versions;
  return <Modal wide title={`${T("إصدارات", "Versions of")} ${doc.name}`} onClose={onClose} footer={write && <button className="btn primary" onClick={onNew}><Upload />{T("ارفع إصداراً جديداً", "Upload a new version")}</button>}>
    <div className="stack"><div className="tbl-wrap"><table className="tbl"><thead><tr><th>{T("الإصدار", "Version")}</th><th>{T("الملف", "File")}</th><th>{T("تاريخ الرفع", "Uploaded")}</th><th>{T("ملاحظة", "Note")}</th><th /></tr></thead>
      <tbody>{[...vs].reverse().map((v: any) => <tr key={v.version}><td className="num">{v.version}{v.version === doc.current_version && <span className="tag good" style={{ marginInlineStart: 6 }}>{T("الحالي", "Current")}</span>}</td><td><bdi>{v.filename}</bdi></td><td>{date(v.uploaded_at)}</td><td>{v.note || "—"}</td>
        <td className="act"><button className="btn ghost sm" onClick={() => onView(v.version)}><Eye />{T("اعرض", "View")}</button>
          {v.version > 1 && <button className="btn ghost sm" onClick={() => api.get(`/documents/${doc.id}/diff?v_from=${v.version - 1}&v_to=${v.version}`).then(setDiff).catch(fail)}><GitCompare />{T("ما الذي تغير؟", "What changed?")}</button>}</td></tr>)}</tbody></table></div>
      {diff && <div className="stack tight"><h3>{T(`التغييرات من الإصدار ${diff.from} إلى ${diff.to}`, `Changes from version ${diff.from} to ${diff.to}`)}</h3>
        {diff.added.map((l: string, i: number) => <div key={`a${i}`} className="note" style={{ background: "var(--good-bg)" }} dir="auto">+ {l}</div>)}
        {diff.removed.map((l: string, i: number) => <div key={`r${i}`} className="note critical" dir="auto">− {l}</div>)}
        <p className="small muted">{T(`${diff.unchanged} سطر بلا تغيير.`, `${diff.unchanged} lines unchanged.`)}</p></div>}
    </div></Modal>;
}
