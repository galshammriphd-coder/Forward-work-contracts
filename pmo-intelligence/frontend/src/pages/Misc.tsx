import { useEffect, useRef, useState } from "react";
import { MessageSquarePlus, Send, ShieldCheck } from "lucide-react";
import { api, setToken, useApp, useLoad } from "../lib/core";
import { Async, Register, Tabs } from "../lib/ui";
import { Answer } from "./Knowledge";
import { BenefitsRegister, LessonsRegister } from "./ProjectCenter";

/* ---------------- AI PMO Copilot ---------------- */
export function Copilot() {
  const { T, fail } = useApp();
  const convs = useLoad<any[]>("/copilot/conversations");
  const [cid, setCid] = useState<number | null>(null);
  const [conv, setConv] = useState<any>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const log = useRef<HTMLDivElement>(null);
  useEffect(() => { if (cid) api.get(`/conversations/${cid}`).then(setConv).catch(fail); else setConv(null); }, [cid]);  // eslint-disable-line
  useEffect(() => { log.current?.scrollTo({ top: log.current.scrollHeight }); }, [conv?.messages?.length, busy]);
  const ask = async (q: string) => { if (!q.trim() || busy) return; setBusy(true); setText("");
    try { let id = cid; if (!id) { id = (await api.post("/copilot/conversations")).id; setCid(id); }
      setConv((c: any) => ({ ...(c || {}), messages: [...(c?.messages || []), { id: -1, role: "user", content: q }] }));
      await api.post(`/conversations/${id}/messages`, { question: q }); setConv(await api.get(`/conversations/${id}`)); convs.reload(); } catch (e) { fail(e); } finally { setBusy(false); } };
  const ideas: [string, string][] = [["لخص وضع المحفظة", "Summarise the portfolio"], ["ما أولويات التدخل؟", "Where should we intervene first?"], ["ما المشاريع المتأخرة؟", "Which projects are delayed?"], ["ما أعلى المخاطر عبر المشاريع؟", "What are the top risks across projects?"],
    ["كيف الأداء المالي للمشاريع؟", "How is financial performance?"], ["قارن بين DX-02 و DX-04", "Compare DX-02 and DX-04"], ["ما الأنماط المتكررة في التأخير؟", "What delay patterns recur?"]];
  return <div className="page">
    <div className="page-head"><div><h1>{T("المساعد الذكي لمكتب إدارة المشاريع", "AI PMO Copilot")}</h1><p>{T("يحلل المحافظ والبرامج والمشاريع التي تتيحها صلاحياتك فقط، ويبين لكل جزء من إجابته مصدره: بيانات النظام، حساب المحركات، وثائق مسترجعة، أو توصية مولدة.", "Analyses only the portfolios, programmes and projects in your scope, and labels each part of its answer by source: system data, engine calculation, retrieved documents, or a generated recommendation.")}</p></div></div>
    <div className="chat">
      <aside className="panel"><header><h3>{T("المحادثات", "Conversations")}</h3><button className="btn sm" onClick={() => setCid(null)}><MessageSquarePlus />{T("جديدة", "New")}</button></header>
        <div style={{ maxHeight: "60vh", overflowY: "auto" }}>{(convs.data || []).map(c => <button key={c.id} onClick={() => setCid(c.id)} style={{ all: "unset", display: "block", cursor: "pointer", padding: "7px 12px", fontSize: ".86rem", width: "100%", boxSizing: "border-box", background: c.id === cid ? "var(--raised)" : undefined, fontWeight: c.id === cid ? 600 : 400, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.title || "—"}</button>)}
          {convs.data?.length === 0 && <p className="muted small" style={{ padding: 12 }}>{T("لا محادثات بعد.", "No conversations yet.")}</p>}</div></aside>
      <section className="panel"><div className="chat-log" ref={log} aria-live="polite">
        {!conv?.messages?.length && <div className="stack"><p className="muted">{T("اسأل عن الأداء أو التأخير أو المخاطر أو الميزانيات، أو اطلب مقارنة بين مشروعين برمزيهما.", "Ask about performance, delays, risks or budgets, or compare two projects by their codes.")}</p>
          <div className="row">{ideas.map(([a, e]) => <button key={e} className="btn sm" onClick={() => ask(T(a, e))}>{T(a, e)}</button>)}</div></div>}
        {(conv?.messages || []).map((m: any) => m.role === "user" ? <div key={m.id} className="msg user" dir="auto">{m.content}</div> : <Answer key={m.id} msg={m} title={conv.title} />)}
        {busy && <div className="row muted"><i className="spin" />{T("يحلل بيانات المشاريع ضمن صلاحياتك…", "Analysing the projects in your scope…")}</div>}</div>
        <form className="row body" style={{ borderBlockStart: "1px solid var(--line-2)" }} onSubmit={e => { e.preventDefault(); ask(text); }}>
          <input className="input grow" style={{ width: "auto" }} dir="auto" value={text} onChange={e => setText(e.target.value)} placeholder={T("اسأل عن المحفظة أو مشروع بعينه…", "Ask about the portfolio or a specific project…")} aria-label={T("السؤال", "Question")} />
          <button className="btn primary" disabled={busy || !text.trim()}><Send className="flip" />{T("اسأل", "Ask")}</button></form></section>
    </div></div>;
}

export function Lessons() {
  const { T } = useApp();
  const [tab, setTab] = useState("lessons");
  return <div className="page">
    <div className="page-head"><div><h1>{T("الدروس المستفادة وتحقيق القيمة", "Lessons learned and value realisation")}</h1><p>{T("ما تعلمته المشاريع، وما تحقق فعلاً من منافعها بعد التسليم.", "What projects learned, and what benefit they actually delivered after handover.")}</p></div></div>
    <Tabs value={tab} onChange={setTab} tabs={[["lessons", T("الدروس المستفادة", "Lessons learned")], ["benefits", T("المنافع وتحقيق القيمة", "Benefits realisation")]]} />
    {tab === "lessons" ? <LessonsRegister /> : <BenefitsRegister />}</div>;
}

/* ---------------- administration ---------------- */
export function Admin() {
  const { T, N, can, meta, reloadMeta, fail, toast, user } = useApp();
  const [tab, setTab] = useState(can("admin.users") ? "users" : "settings");
  const users = useLoad<any[]>(tab === "users" && can("admin.users") ? "/admin/users" : null);
  const roles = useLoad<any>(tab === "roles" && can("admin.users") ? "/admin/roles" : null);
  const [edit, setEdit] = useState<any>(null);
  const [s, setS] = useState<any>(null);
  const [mfa, setMfa] = useState<any>(null);
  const [code, setCode] = useState("");
  useEffect(() => { if (meta?.settings) setS(JSON.parse(JSON.stringify(meta.settings))); }, [meta]);
  const put = (key: string) => api.put(`/settings/${key}`, s[key]).then(() => { toast(T("حُفظت الإعدادات", "Settings saved")); reloadMeta(); }).catch(fail);
  const saveUser = async () => { try { edit.id ? await api.patch(`/admin/users/${edit.id}`, edit) : await api.post("/admin/users", edit); toast(T("حُفظ المستخدم", "User saved")); setEdit(null); users.reload(); reloadMeta(); } catch (e) { fail(e); } };
  const days: [number, string, string][] = [[6, "الأحد", "Sun"], [0, "الاثنين", "Mon"], [1, "الثلاثاء", "Tue"], [2, "الأربعاء", "Wed"], [3, "الخميس", "Thu"], [4, "الجمعة", "Fri"], [5, "السبت", "Sat"]];
  const adminS = can("admin.settings");
  return <div className="page">
    <div className="page-head"><div><h1>{T("الإدارة والإعدادات", "Administration and settings")}</h1><p>{T("المستخدمون والأدوار والصلاحيات، وإعدادات المؤسسة والمخاطر والتقويم والذكاء الاصطناعي.", "Users, roles and permissions; organisation, risk, calendar and AI settings.")}</p></div></div>
    <Tabs value={tab} onChange={setTab} tabs={[...(can("admin.users") ? [["users", T("المستخدمون", "Users")], ["roles", T("الأدوار والصلاحيات", "Roles & permissions")]] as [string, string][] : []), ["settings", T("إعدادات المنصة", "Platform settings")], ["org", T("الإدارات", "Departments")], ["security", T("أمان حسابي", "My account security")]]} />
    {tab === "users" && <section className="panel"><header><h2>{T("المستخدمون", "Users")}</h2><button className="btn primary sm" onClick={() => setEdit({ role_key: "team_member", is_active: true })}>{T("أضف مستخدماً", "Add user")}</button></header>
      <Async q={users}>{rows => <div className="tbl-wrap"><table className="tbl"><thead><tr><th>{T("الاسم", "Name")}</th><th>{T("البريد الإلكتروني", "Email")}</th><th>{T("الدور", "Role")}</th><th>{T("نطاق المشاريع", "Project scope")}</th><th>{T("تحقق بخطوتين", "Two-step")}</th><th>{T("الحالة", "State")}</th><th /></tr></thead>
        <tbody>{rows.map((u: any) => <tr key={u.id}><td>{N(u)}</td><td><bdi>{u.email}</bdi></td><td>{N(u, "role_name")}</td><td>{u.all_projects ? T("كل المشاريع", "All projects") : T("المشاريع المسندة فقط", "Assigned projects only")}</td><td>{u.mfa_enabled ? T("مفعّل", "On") : "—"}</td>
          <td>{u.is_active ? <span className="tag good">{T("نشط", "Active")}</span> : <span className="tag">{T("موقوف", "Disabled")}</span>}</td><td className="act"><button className="btn ghost sm" onClick={() => setEdit({ ...u, password: "" })}>{T("عدّل", "Edit")}</button></td></tr>)}</tbody></table></div>}</Async></section>}
    {tab === "roles" && <Async q={roles}>{d => <section className="panel"><header><div><h2>{T("مصفوفة الأدوار والصلاحيات", "Role and permission matrix")}</h2><p>{T("التغيير يسري فوراً على كل من يحمل الدور. دور مدير النظام ثابت.", "Changes apply at once to everyone holding the role. The Super Administrator role is fixed.")}</p></div></header>
      <div className="tbl-wrap" style={{ maxHeight: "68vh" }}><table className="tbl"><thead><tr><th>{T("الصلاحية", "Permission")}</th>{d.roles.map((r: any) => <th key={r.id} style={{ writingMode: "vertical-rl", whiteSpace: "nowrap", verticalAlign: "bottom", height: 150 }}>{N(r)}</th>)}</tr></thead>
        <tbody>{d.permissions.map((p: any) => <tr key={p.key}><td><bdi className="strong">{p.key}</bdi><div className="small muted" dir="ltr" style={{ textAlign: "start" }}>{p.description}</div></td>
          {d.roles.map((r: any) => <td key={r.id}><input type="checkbox" checked={r.permissions.includes(p.key)} disabled={r.key === "super_admin"} aria-label={`${r.key} ${p.key}`}
            onChange={e => api.patch(`/admin/roles/${r.id}`, { permissions: e.target.checked ? [...r.permissions, p.key] : r.permissions.filter((x: string) => x !== p.key) }).then(() => roles.reload()).catch(fail)} /></td>)}</tr>)}
          <tr><td className="strong">{T("يرى كل المشاريع", "Sees all projects")}</td>{d.roles.map((r: any) => <td key={r.id}><input type="checkbox" checked={r.all_projects} disabled={r.key === "super_admin"} aria-label={`${r.key} all projects`} onChange={e => api.patch(`/admin/roles/${r.id}`, { all_projects: e.target.checked }).then(() => roles.reload()).catch(fail)} /></td>)}</tr>
          <tr><td className="strong">{T("مستوى الاطلاع على الوثائق (0–3)", "Document clearance (0–3)")}</td>{d.roles.map((r: any) => <td key={r.id}><select className="input inline" style={{ width: 52 }} value={r.clearance} disabled={r.key === "super_admin"} aria-label={`${r.key} clearance`} onChange={e => api.patch(`/admin/roles/${r.id}`, { clearance: +e.target.value }).then(() => roles.reload()).catch(fail)}>{[0, 1, 2, 3].map(n => <option key={n}>{n}</option>)}</select></td>)}</tr></tbody></table></div></section>}</Async>}
    {tab === "settings" && s && <div className="grid g2">
      <section className="panel"><header><h2>{T("المؤسسة والعرض", "Organisation and display")}</h2></header><div className="body stack"><div className="form-grid">
        <label className="field"><span>{T("اسم المؤسسة (عربي)", "Organisation name (Arabic)")}</span><input className="input" value={s.org.name_ar} onChange={e => setS({ ...s, org: { ...s.org, name_ar: e.target.value } })} /></label>
        <label className="field"><span>{T("اسم المؤسسة (إنجليزي)", "Organisation name (English)")}</span><input className="input" dir="ltr" value={s.org.name_en} onChange={e => setS({ ...s, org: { ...s.org, name_en: e.target.value } })} /></label>
        <label className="field"><span>{T("العملة", "Currency")}</span><select className="input" value={s.org.currency} onChange={e => setS({ ...s, org: { ...s.org, currency: e.target.value } })}>{["SAR", "AED", "KWD", "QAR", "BHD", "OMR", "EGP", "USD", "EUR"].map(c => <option key={c}>{c}</option>)}</select></label>
        <label className="field"><span>{T("الأرقام في الواجهة العربية", "Numerals in the Arabic interface")}</span><select className="input" value={s.org.numerals} onChange={e => setS({ ...s, org: { ...s.org, numerals: e.target.value } })}><option value="latn">123 — {T("غربية", "Western")}</option><option value="arab">١٢٣ — {T("مشرقية", "Eastern Arabic")}</option></select></label>
        <label className="field"><span>{T("التقويم في الواجهة العربية", "Calendar in the Arabic interface")}</span><select className="input" value={s.org.calendar} onChange={e => setS({ ...s, org: { ...s.org, calendar: e.target.value } })}><option value="gregory">{T("ميلادي", "Gregorian")}</option><option value="islamic-umalqura">{T("هجري (أم القرى)", "Hijri (Umm al-Qura)")}</option></select></label></div>
        {adminS && <div><button className="btn primary" onClick={() => put("org")}>{T("احفظ", "Save")}</button></div>}</div></section>
      <section className="panel"><header><div><h2>{T("حدود تصنيف المخاطر", "Risk rating limits")}</h2><p>{T("الدرجة = الاحتمالية × الأثر (من 1 إلى 25)", "Score = probability × impact (1 to 25)")}</p></div></header><div className="body stack"><div className="form-grid">
        {[["low", "منخفض حتى", "Low up to"], ["moderate", "متوسط حتى", "Moderate up to"], ["high", "عالٍ حتى", "High up to"]].map(([k, a, e]) => <label className="field" key={k}><span>{T(a, e)}</span><input className="input" type="number" min={1} max={24} value={s.risk_thresholds[k]} onChange={ev => setS({ ...s, risk_thresholds: { ...s.risk_thresholds, [k]: +ev.target.value } })} /></label>)}
        <div className="field"><span>{T("حرج", "Critical")}</span><div className="input" style={{ background: "var(--sunk)" }}>{T("ما فوق", "Above")} {s.risk_thresholds.high}</div></div></div>
        <p className="small muted">{T("عند الحفظ يُعاد تصنيف كل المخاطر وتُراجع التنبيهات.", "On save every risk is reclassified and alerts are re-evaluated.")}</p>{adminS && <div><button className="btn primary" onClick={() => put("risk_thresholds")}>{T("احفظ وأعد التصنيف", "Save and reclassify")}</button></div>}</div></section>
      <section className="panel"><header><div><h2>{T("تقويم العمل والإجازات", "Working calendar and holidays")}</h2></div></header><div className="body stack">
        <div className="field"><span>{T("أيام العطلة الأسبوعية", "Weekend days")}</span><div className="row">{days.map(([n, a, e]) => <label key={n} className="tag" style={{ cursor: "pointer" }}><input type="checkbox" checked={s.work_calendar.weekend.includes(n)} onChange={ev => setS({ ...s, work_calendar: { ...s.work_calendar, weekend: ev.target.checked ? [...s.work_calendar.weekend, n] : s.work_calendar.weekend.filter((x: number) => x !== n) } })} />{T(a, e)}</label>)}</div></div>
        <label className="field"><span>{T("الإجازات الرسمية (تاريخ في كل سطر: 2027-02-22)", "Public holidays (one date per line: 2027-02-22)")}</span><textarea className="input" dir="ltr" value={(s.work_calendar.holidays || []).join("\n")} onChange={e => setS({ ...s, work_calendar: { ...s.work_calendar, holidays: e.target.value.split(/\s+/).filter(Boolean) } })} /></label>
        <p className="small muted">{T("عند الحفظ يُعاد حساب جداول كل المشاريع النشطة والمخطط لها.", "On save the schedules of all active and planned projects are recalculated.")}</p>{adminS && <div><button className="btn primary" onClick={() => put("work_calendar")}>{T("احفظ وأعد حساب الجداول", "Save and recalculate schedules")}</button></div>}</div></section>
      <section className="panel"><header><div><h2>{T("سياسة الاحتفاظ بالبيانات", "Data retention")}</h2><p>{T("عدد الأيام قبل الحذف التلقائي. 0 = احتفاظ دائم. سجل التدقيق لا يُحذف آلياً.", "Days before automatic deletion. 0 = keep for ever. The audit trail is never purged automatically.")}</p></div></header><div className="body stack"><div className="form-grid">
        {[["notifications_days", "الإشعارات", "Notifications"], ["automation_runs_days", "سجل تنفيذ الأتمتة", "Automation run log"], ["resolved_alerts_days", "التنبيهات المعالجة", "Resolved alerts"]].map(([k, a, e]) => <label className="field" key={k}><span>{T(a, e)}</span><input className="input" type="number" min={0} value={s.retention?.[k] ?? 0} onChange={ev => setS({ ...s, retention: { ...s.retention, [k]: +ev.target.value } })} /></label>)}</div>
        {adminS && <div><button className="btn primary" onClick={() => put("retention")}>{T("احفظ", "Save")}</button></div>}</div></section>
      <section className="panel"><header><div><h2>{T("الذكاء الاصطناعي ومعالجة الوثائق", "AI and document processing")}</h2><p>{T("الوضع الافتراضي محلي بالكامل: لا يغادر أي محتوى هذا الخادم.", "The default is fully local: no content leaves this server.")}</p></div></header><div className="body stack">
        <label className="field"><span>{T("محرك توليد الإجابات", "Answer generation engine")}</span><select className="input" value={s.ai.mode} onChange={e => setS({ ...s, ai: { ...s.ai, mode: e.target.value } })}><option value="local">{T("محلي مدمج (استخلاصي، بلا نموذج خارجي)", "Built-in local (extractive, no external model)")}</option><option value="endpoint">{T("نموذج لغوي عبر واجهة متوافقة مع OpenAI", "Language model through an OpenAI-compatible endpoint")}</option></select></label>
        {s.ai.mode === "endpoint" && <><div className="form-grid">
          <label className="field"><span>{T("عنوان الواجهة", "Endpoint URL")}</span><input className="input" dir="ltr" placeholder="http://ollama.internal:11434/v1" value={s.ai.endpoint_url} onChange={e => setS({ ...s, ai: { ...s.ai, endpoint_url: e.target.value } })} /></label>
          <label className="field"><span>{T("اسم النموذج", "Model name")}</span><input className="input" dir="ltr" value={s.ai.endpoint_model} onChange={e => setS({ ...s, ai: { ...s.ai, endpoint_model: e.target.value } })} /></label></div>
          <label className="row"><input type="checkbox" checked={s.ai.endpoint_is_external} onChange={e => setS({ ...s, ai: { ...s.ai, endpoint_is_external: e.target.checked } })} />{T("هذه الواجهة خارج شبكة المؤسسة (مزود خارجي)", "This endpoint is outside the organisation's network (external provider)")}</label>
          {s.ai.endpoint_is_external && <><div className="note warning">{T("سترسل مقتطفات من الوثائق إلى مزود خارجي. لا يعمل هذا الخيار إلا بموافقة مؤسسية صريحة.", "Document excerpts will be sent to an external provider. This works only with explicit organisational consent.")}</div>
            <label className="row"><input type="checkbox" checked={s.ai.external_consent} onChange={e => setS({ ...s, ai: { ...s.ai, external_consent: e.target.checked } })} />{T("المؤسسة وافقت على إرسال محتوى الوثائق غير السرية إلى هذا المزود", "The organisation has consented to sending non-confidential document content to this provider")}</label>
            <label className="row"><input type="checkbox" checked={s.ai.allow_confidential_external} onChange={e => setS({ ...s, ai: { ...s.ai, allow_confidential_external: e.target.checked } })} />{T("واسمح أيضاً بالوثائق السرية والمقيدة (غير مستحسن)", "Also allow confidential and restricted documents (not recommended)")}</label></>}</>}
        <label className="field"><span>{T("نموذج التضمين (Embeddings)", "Embedding model")}</span><input className="input" dir="ltr" value={s.ai.embedding_model} onChange={e => setS({ ...s, ai: { ...s.ai, embedding_model: e.target.value } })} />
          <small className="muted">{T("local-hash-v1 مدمج. لنموذج عصبي محلي أدخل اسمه أو مساره بعد تثبيت sentence-transformers، ثم أعد فهرسة الوثائق.", "local-hash-v1 is built in. For a local neural model enter its name or path after installing sentence-transformers, then re-index documents.")}</small></label>
        {adminS && <div><button className="btn primary" onClick={() => put("ai")}>{T("احفظ", "Save")}</button></div>}</div></section></div>}
    {tab === "org" && <Register resource="departments" perm="admin.settings" noun={["إدارة", "Department"]} title={T("الإدارات", "Departments")} onChanged={reloadMeta}
      cols={[{ key: "name_ar", label: ["الاسم (عربي)", "Name (Arabic)"] }, { key: "name_en", label: ["الاسم (إنجليزي)", "Name (English)"] }]} fields={[{ key: "name_ar", label: ["الاسم (عربي)", "Name (Arabic)"], required: true }, { key: "name_en", label: ["الاسم (إنجليزي)", "Name (English)"] }]} />}
    {tab === "security" && <section className="panel" style={{ maxWidth: 640 }}><header><div><h2>{T("التحقق بخطوتين", "Two-step verification")}</h2><p><bdi>{user?.email}</bdi></p></div><ShieldCheck /></header><div className="body stack">
      {user?.mfa_enabled ? <><div className="note">{T("التحقق بخطوتين مفعّل على حسابك.", "Two-step verification is on for your account.")}</div><div><button className="btn danger" onClick={() => api.post("/auth/mfa/enable", { disable: true }).then(() => location.reload()).catch(fail)}>{T("أوقف التحقق بخطوتين", "Turn off two-step verification")}</button></div></> :
        !mfa ? <><p>{T("أضف رمزاً من تطبيق المصادقة (TOTP) عند كل دخول.", "Add a code from an authenticator app (TOTP) at every sign-in.")}</p><div><button className="btn primary" onClick={() => api.post("/auth/mfa/setup").then(setMfa).catch(fail)}>{T("ابدأ الإعداد", "Start setup")}</button></div></> :
          <><p>{T("أدخل هذا المفتاح في تطبيق المصادقة، ثم اكتب الرمز الظاهر للتأكيد:", "Enter this key in your authenticator app, then type the code it shows to confirm:")}</p><code className="ltr" style={{ fontSize: "1.05rem", wordBreak: "break-all" }}>{mfa.secret}</code>
            <div className="row"><input className="input" style={{ width: 150 }} dir="ltr" inputMode="numeric" placeholder="000000" value={code} onChange={e => setCode(e.target.value)} aria-label={T("رمز التحقق", "Verification code")} />
              <button className="btn primary" onClick={() => api.post("/auth/mfa/enable", { code }).then(() => { toast(T("فُعّل التحقق بخطوتين", "Two-step verification is on")); location.reload(); }).catch(fail)}>{T("فعّل", "Turn on")}</button></div></>}
      <hr style={{ border: 0, borderBlockStart: "1px solid var(--line-2)", width: "100%" }} />
      <div><button className="btn" onClick={() => api.post("/auth/logout").then(() => { setToken(""); location.href = "/"; }).catch(fail)}>{T("سجّل الخروج من كل الأجهزة", "Sign out of all devices")}</button></div></div></section>}
    {edit && <div className="modal-back" onMouseDown={e => e.target === e.currentTarget && setEdit(null)}><div className="modal" role="dialog" aria-modal="true"><header><h2>{edit.id ? T("تعديل مستخدم", "Edit user") : T("مستخدم جديد", "New user")}</h2></header>
      <div className="body"><div className="form-grid">
        <label className="field"><span>{T("الاسم (عربي)", "Name (Arabic)")}</span><input className="input" value={edit.name_ar || ""} onChange={e => setEdit({ ...edit, name_ar: e.target.value })} /></label>
        <label className="field"><span>{T("الاسم (إنجليزي)", "Name (English)")}</span><input className="input" dir="ltr" value={edit.name_en || ""} onChange={e => setEdit({ ...edit, name_en: e.target.value })} /></label>
        <label className="field"><span>{T("البريد الإلكتروني", "Email")}<em> *</em></span><input className="input" dir="ltr" type="email" disabled={!!edit.id} value={edit.email || ""} onChange={e => setEdit({ ...edit, email: e.target.value })} /></label>
        <label className="field"><span>{T("الدور", "Role")}<em> *</em></span><select className="input" value={edit.role_key} onChange={e => setEdit({ ...edit, role_key: e.target.value })}>{(meta?.roles || []).map((r: any) => <option key={r.key} value={r.key}>{N(r)}</option>)}</select></label>
        <label className="field"><span>{edit.id ? T("كلمة مرور جديدة (اختياري)", "New password (optional)") : T("كلمة المرور (8 أحرف على الأقل)", "Password (at least 8 characters)")}</span><input className="input" dir="ltr" type="password" autoComplete="new-password" value={edit.password || ""} onChange={e => setEdit({ ...edit, password: e.target.value })} /></label>
        <label className="field"><span>{T("الحساب نشط", "Account active")}</span><label className="row"><input type="checkbox" checked={!!edit.is_active} onChange={e => setEdit({ ...edit, is_active: e.target.checked })} />{T("نعم", "Yes")}</label></label></div></div>
      <footer><button className="btn" onClick={() => setEdit(null)}>{T("إلغاء", "Cancel")}</button><button className="btn primary" onClick={saveUser}>{T("حفظ", "Save")}</button></footer></div></div>}
  </div>;
}
