import { ComponentType, lazy, ReactNode, Suspense, useEffect, useRef, useState } from "react";
import { Link, NavLink, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { Bell, BookOpenCheck, Bot, Briefcase, CalendarRange, CircleDollarSign, FileStack, FileUp, FolderKanban, Gauge, Languages, Layers, ListTree, LogOut, Menu, MessagesSquare, Moon, Scale, Search, Settings, ShieldAlert, Sun, Target, Users, Workflow, FileBarChart } from "lucide-react";
import { api, hasToken, setToken, store, useApp, useLoad } from "./lib/core";
import { Loading } from "./lib/ui";

// Route-level code splitting: each module is fetched when first opened (bundle-dynamic-imports),
// and warmed up when the pointer or keyboard focus reaches its menu entry (bundle-preload).
const load = {
  dashboard: () => import("./pages/Dashboard"), portfolio: () => import("./pages/Portfolio"), center: () => import("./pages/ProjectCenter"),
  initiation: () => import("./pages/Initiation"), schedule: () => import("./pages/Schedule"), risks: () => import("./pages/Risks"),
  finance: () => import("./pages/Finance"), people: () => import("./pages/People"), knowledge: () => import("./pages/Knowledge"),
  govern: () => import("./pages/Govern"), reports: () => import("./pages/Reports"), misc: () => import("./pages/Misc"),
};
const pick = <K extends keyof typeof load>(k: K, name: string) => lazy<ComponentType<any>>(() => (load[k]() as Promise<any>).then(m => ({ default: m[name] })));
const Dashboard = pick("dashboard", "default"), Strategy = pick("portfolio", "Strategy"), Portfolios = pick("portfolio", "Portfolios"), Projects = pick("portfolio", "Projects");
const ProjectCenter = pick("center", "default"), Initiation = pick("initiation", "default"), Schedule = pick("schedule", "default"), Planning = pick("schedule", "Planning");
const Risks = pick("risks", "default"), Finance = pick("finance", "default"), Resources = pick("people", "Resources"), Chat = pick("knowledge", "Chat"), Documents = pick("knowledge", "Documents");
const Governance = pick("govern", "Governance"), Automation = pick("govern", "Automation"), Reports = pick("reports", "default");
const Admin = pick("misc", "Admin"), Copilot = pick("misc", "Copilot"), Lessons = pick("misc", "Lessons");
const WARM: Record<string, keyof typeof load> = { "/": "dashboard", "/strategy": "portfolio", "/portfolios": "portfolio", "/programs": "portfolio", "/projects": "portfolio", "/initiation": "initiation",
  "/planning": "schedule", "/scheduling": "schedule", "/risks": "risks", "/financial": "finance", "/resources": "people", "/documents": "knowledge", "/knowledge": "knowledge",
  "/governance": "govern", "/automation": "govern", "/reports": "reports", "/copilot": "misc", "/lessons": "misc", "/admin": "misc" };
const warm = (to: string) => { const k = WARM[to]; if (k) load[k]().catch(() => {}); };
export const APP_NAME = "AI-Powered PMO Platform";

export const Mark = ({ size = 30 }: { size?: number }) => <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
  <rect width="32" height="32" rx="7" fill="#17383f" /><path d="M5 16h8m6 0h8" stroke="#79C7DD" strokeWidth="2.5" strokeLinecap="round" /><path d="M16 9.5 22.5 16 16 22.5 9.5 16Z" fill="#F4B740" /></svg>;

function Login() {
  const { T, setUser, lang, setLang } = useApp();
  const [v, setV] = useState({ email: "", password: "", code: "" });
  const [mfa, setMfa] = useState(false);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (creds = v) => { setBusy(true); setErr("");
    try { const r = await api.post("/auth/login", creds); if (r.mfa_required) setMfa(true); else { setToken(r.token); setUser(r.user); } }
    catch (e: any) { setErr(e.message === "NETWORK" ? T("تعذر الاتصال بالخادم.", "Cannot reach the server.") : e.status === 401 ? T("البريد الإلكتروني أو كلمة المرور غير صحيحة.", "Email or password is incorrect.") : e.message); } finally { setBusy(false); } };
  const demo: [string, string, string][] = [["director", "مدير مكتب إدارة المشاريع", "PMO Director"], ["pm1", "مدير مشروع", "Project Manager"], ["finance", "المراقب المالي", "Financial Controller"], ["member", "عضو فريق", "Team Member"], ["viewer", "مطّلع تنفيذي", "Executive Viewer"], ["admin", "مدير النظام", "Super Administrator"]];
  const life: [string, string][] = [["الفكرة", "Idea"], ["الميثاق", "Charter"], ["التخطيط", "Planning"], ["التنفيذ", "Delivery"], ["الإغلاق", "Closure"], ["القيمة", "Value"]];
  return <div className="login">
    <aside><div className="row"><Mark size={38} /><div><b style={{ fontFamily: "var(--display)", fontSize: "1.1rem" }} className="ltr">{APP_NAME}</b></div></div>
      <div><h1 style={{ fontSize: "clamp(1.7rem, 3.2vw, 2.6rem)", color: "#fff", lineHeight: 1.4, maxWidth: "16ch" }}>{T("من ميثاق المشروع إلى قيمة تُقاس", "From project charter to measured value")}</h1>
        <p style={{ color: "var(--rail-mute)", marginBlockStart: 14, maxWidth: "46ch" }}>{T("ارفع الميثاق فيصبح مشروعاً قابلاً للإدارة، ووثائقه معرفةً تُسأل، وبياناته مؤشرات وإنذارات.", "Upload a charter and it becomes a manageable project; its documents become knowledge you can question; its data become indicators and warnings.")}</p>
        <ul className="rail-life" style={{ marginBlockStart: 34, maxWidth: 520 }}>{life.map(([a, e], i) => <li key={e} className={i < 3 ? "done" : i === 3 ? "now done" : ""} style={{ color: i === 3 ? "#fff" : "var(--rail-mute)" }}>{T(a, e)}</li>)}</ul></div>
      <small style={{ color: "var(--rail-mute)" }} className="ltr">From Project Initiation to Strategic Value Realization</small></aside>
    <main><form className="stack" style={{ width: "min(380px, 100%)" }} onSubmit={e => { e.preventDefault(); submit(); }}>
      <div className="row" style={{ justifyContent: "space-between" }}><h2 style={{ fontSize: "1.4rem" }}>{T("تسجيل الدخول", "Sign in")}</h2><button type="button" className="btn ghost sm" onClick={() => setLang(lang === "ar" ? "en" : "ar")}><Languages />{lang === "ar" ? "English" : "العربية"}</button></div>
      {err && <div className="note critical" role="alert">{err}</div>}
      <label className="field"><span>{T("البريد الإلكتروني", "Email")}</span><input className="input" dir="ltr" type="email" autoComplete="username" required value={v.email} onChange={e => setV({ ...v, email: e.target.value })} /></label>
      <label className="field"><span>{T("كلمة المرور", "Password")}</span><input className="input" dir="ltr" type="password" autoComplete="current-password" required value={v.password} onChange={e => setV({ ...v, password: e.target.value })} /></label>
      {mfa && <label className="field"><span>{T("رمز التحقق من تطبيق المصادقة", "Code from your authenticator app")}</span><input className="input" dir="ltr" inputMode="numeric" autoFocus value={v.code} onChange={e => setV({ ...v, code: e.target.value })} /></label>}
      <button className="btn primary" disabled={busy}>{busy && <i className="spin" />}{T("ادخل", "Sign in")}</button>
      <div className="panel"><div className="body stack tight"><b className="small">{T("حسابات البيئة التجريبية (بيانات وهمية)", "Demo environment accounts (fictional data)")}</b>
        <div className="row">{demo.map(([k, a, e]) => <button type="button" key={k} className="btn sm" onClick={() => submit({ email: `${k}@pmo.local`, password: "Pmo@2026!", code: "" })}>{T(a, e)}</button>)}</div>
        <span className="small muted">{T("كل دور يرى ما تتيحه صلاحياته فقط. كلمة المرور لجميعها:", "Each role sees only what its permissions allow. Password for all:")} <bdi>Pmo@2026!</bdi></span></div></div>
    </form></main></div>;
}

function Picker({ children, title, sub, allowAll }: { children: (pid: number | undefined) => ReactNode; title: [string, string]; sub: [string, string]; allowAll?: boolean }) {
  const { T, N } = useApp();
  const q = useLoad<any[]>("/projects");
  const [pid, setPid] = useState<string>(store.get("pmo_project") || "");
  useEffect(() => { if (q.data && !allowAll && !q.data.some(p => String(p.id) === pid) && q.data[0]) setPid(String(q.data[0].id)); }, [q.data]);  // eslint-disable-line
  useEffect(() => { pid && store.set("pmo_project", pid); }, [pid]);
  const cur = (q.data || []).find(p => String(p.id) === pid);
  return <div className="page">
    <div className="page-head"><div><h1>{T(...title)}</h1><p>{T(...sub)}</p></div>
      <div className="row"><label className="field" style={{ minWidth: 280 }}><span>{T("المشروع", "Project")}</span><select className="input" value={cur || allowAll ? pid : ""} onChange={e => setPid(e.target.value)}>
        {allowAll && <option value="">{T("كل المشاريع", "All projects")}</option>}{(q.data || []).map(p => <option key={p.id} value={p.id}>{p.code} — {N(p)}</option>)}</select></label>
        {cur && <Link className="btn" style={{ alignSelf: "flex-end" }} to={`/projects/${cur.id}`}>{T("افتح مركز القيادة", "Open command centre")}</Link>}</div></div>
    {!q.data ? <Loading /> : cur ? <div key={cur.id}>{children(cur.id)}</div> : allowAll ? children(undefined) : <div className="panel"><div className="empty">{T("لا مشاريع ضمن صلاحياتك.", "No projects in your scope.")}</div></div>}
  </div>;
}

function GlobalSearch() {
  const { T, N } = useApp();
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const [res, setRes] = useState<any[] | null>(null);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => { if (q.trim().length < 2) { setRes(null); return; } const t = setTimeout(() => api.get(`/search?q=${encodeURIComponent(q)}`).then(setRes).catch(() => setRes([])), 220); return () => clearTimeout(t); }, [q]);
  useEffect(() => { const h = (e: MouseEvent) => !box.current?.contains(e.target as Node) && setRes(null); document.addEventListener("mousedown", h); return () => document.removeEventListener("mousedown", h); }, []);
  const tab: Record<string, string> = { project: "", activity: "/gantt", risk: "/risks", document: "/documents" };
  const kind: Record<string, [string, string]> = { project: ["مشروع", "Project"], activity: ["نشاط", "Activity"], risk: ["خطر", "Risk"], document: ["وثيقة", "Document"] };
  return <div ref={box} className="grow" style={{ position: "relative", maxWidth: 440 }}>
    <Search size={15} style={{ position: "absolute", insetInlineStart: 10, top: 10, color: "var(--ink-3)" }} />
    <input className="input" style={{ paddingInlineStart: 32 }} value={q} onChange={e => setQ(e.target.value)} placeholder={T("ابحث عن مشروع أو نشاط أو خطر أو وثيقة…", "Search projects, activities, risks, documents…")} aria-label={T("بحث شامل", "Global search")} />
    {res && <div className="pop" style={{ insetInline: 0, top: 40, maxHeight: 380, overflowY: "auto" }}>{res.length === 0 ? <div className="empty small">{T("لا نتائج ضمن صلاحياتك.", "No results in your scope.")}</div> :
      res.map((r, i) => <button key={i} className="cite" style={{ border: 0, borderRadius: 0, borderBlockEnd: "1px solid var(--line-2)" }} onClick={() => { nav(`/projects/${r.project_id}${tab[r.type]}`); setRes(null); setQ(""); }}>
        <span><span className="tag">{T(...kind[r.type])}</span> {r.type === "project" ? N({ name_ar: r.label, name_en: r.label_en }) : r.label}</span><span className="small muted"><bdi>{r.sub}</bdi></span></button>)}</div>}</div>;
}

function Bell_() {
  const { T, date } = useApp();
  const nav = useNavigate();
  const q = useLoad<any[]>("/notifications");
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => { const t = setInterval(q.reload, 60000); return () => clearInterval(t); }, [q.reload]);
  useEffect(() => { const h = (e: MouseEvent) => !box.current?.contains(e.target as Node) && setOpen(false); document.addEventListener("mousedown", h); return () => document.removeEventListener("mousedown", h); }, []);
  const unread = (q.data || []).filter(n => !n.is_read).length;
  return <div ref={box} style={{ position: "relative" }}>
    <button className="btn ghost icon" onClick={() => setOpen(!open)} aria-label={T(`الإشعارات، ${unread} غير مقروءة`, `Notifications, ${unread} unread`)} aria-expanded={open}><Bell />
      {unread > 0 && <span className="num" style={{ position: "absolute", top: 1, insetInlineEnd: 0, background: "var(--critical)", color: "#fff", borderRadius: 9, fontSize: 10, minWidth: 16, height: 16, lineHeight: "16px", textAlign: "center", padding: "0 3px" }}>{unread > 99 ? "99+" : unread}</span>}</button>
    {open && <div className="pop" style={{ insetInlineEnd: 0, top: 40, width: "min(380px, 92vw)", maxHeight: 460, overflowY: "auto" }}>
      <div className="row" style={{ padding: "8px 12px", justifyContent: "space-between", borderBlockEnd: "1px solid var(--line-2)" }}><b>{T("الإشعارات", "Notifications")}</b>
        {unread > 0 && <button className="btn ghost sm" onClick={() => api.post("/notifications/read").then(q.reload)}>{T("علّم الكل كمقروء", "Mark all as read")}</button>}</div>
      {(q.data || []).length === 0 && <div className="empty small">{T("لا إشعارات.", "No notifications.")}</div>}
      {(q.data || []).map(n => <button key={n.id} className="cite" style={{ border: 0, borderRadius: 0, borderBlockEnd: "1px solid var(--line-2)", background: n.is_read ? "transparent" : "var(--accent-soft)" }}
        onClick={() => { api.post("/notifications/read", { id: n.id }).then(q.reload); n.link && nav(n.link); setOpen(false); }}><span className="strong" dir="auto">{n.title}</span>{n.body && <span className="small muted" dir="auto">{String(n.body).slice(0, 140)}</span>}<span className="small muted">{date(n.created_at)}</span></button>)}</div>}</div>;
}

export default function App() {
  const { T, N, user, setUser, lang, setLang, theme, setTheme, can } = useApp();
  const [boot, setBoot] = useState(hasToken());
  const [open, setOpen] = useState(false);
  const loc = useLocation();
  useEffect(() => { if (hasToken()) api.get("/auth/me").then(setUser).catch(() => {}).finally(() => setBoot(false)); const out = () => setUser(null); window.addEventListener("pmo-logout", out); return () => window.removeEventListener("pmo-logout", out); }, []);  // eslint-disable-line
  useEffect(() => { setOpen(false); window.scrollTo(0, 0); }, [loc.pathname]);
  if (boot) return <Loading />;
  if (!user) return <Login />;
  const P = (title: [string, string], sub: [string, string], render: (pid: number) => ReactNode) => <Picker title={title} sub={sub}>{pid => render(pid!)}</Picker>;
  const nav: [string, [string, string], [string, string, string, any, boolean?][]][] = [
    ["overview", ["الصورة العامة", "Overview"], [["/", "لوحة القيادة التنفيذية", "Executive Dashboard", Gauge], ["/strategy", "المواءمة الاستراتيجية", "Strategic Alignment", Target, can("portfolio.read")], ["/portfolios", "إدارة المحافظ", "Portfolio Management", Briefcase, can("portfolio.read")],
      ["/programs", "إدارة البرامج", "Program Management", Layers, can("portfolio.read")], ["/projects", "إدارة المشاريع", "Project Management", FolderKanban]]],
    ["project", ["دورة المشروع", "Project lifecycle"], [["/initiation", "إنشاء المشروع", "Project Initiation", FileUp, can("initiation.use")], ["/planning", "تخطيط المشروع", "Project Planning", ListTree], ["/scheduling", "الجدولة الزمنية", "Project Scheduling", CalendarRange],
      ["/risks", "إدارة المخاطر", "Risk Management", ShieldAlert], ["/financial", "الإدارة المالية", "Financial Management", CircleDollarSign, can("finance.read")], ["/resources", "إدارة الموارد", "Resource Management", Users],
      ["/documents", "وثائق المشروع", "Project Documents", FileStack, can("docs.read")], ["/knowledge", "معرفة المشروع والمحادثة", "Project Knowledge & AI Chat", MessagesSquare, can("chat.use")]]],
    ["pmo", ["مكتب إدارة المشاريع", "The PMO"], [["/governance", "حوكمة المكتب", "PMO Governance", Scale], ["/automation", "سير العمل والأتمتة", "Workflow & Automation", Workflow], ["/reports", "التقارير والتحليلات", "Reports & Analytics", FileBarChart, can("report.read")],
      ["/copilot", "المساعد الذكي", "AI PMO Copilot", Bot, can("copilot.use")], ["/lessons", "الدروس المستفادة", "Lessons Learned", BookOpenCheck], ["/admin", "الإدارة والإعدادات", "Administration & Settings", Settings]]]];
  return <div className="shell">
    {open && <div className="scrim" onClick={() => setOpen(false)} />}
    <nav className={`rail ${open ? "open" : ""}`} aria-label={T("القائمة الرئيسية", "Main menu")}>
      <Link to="/" className="brand" style={{ color: "inherit", textDecoration: "none" }}><Mark /><div><b>{APP_NAME}</b><small>From Project Initiation to Strategic Value Realization</small></div></Link>
      <div className="nav">{nav.map(([k, title, items]) => <div key={k}><h5>{T(...title)}</h5>{items.filter(i => i[4] !== false).map(([to, a, e, I]) => <NavLink key={to} to={to} end={to === "/"} onPointerEnter={() => warm(to)} onFocus={() => warm(to)} title={T(a, e)}><I /><span>{T(a, e)}</span></NavLink>)}</div>)}</div>
    </nav>
    <div className="main">
      <header className="top no-print"><a href="#content" className="btn ghost sm" style={{ position: "absolute", insetInlineStart: -9999 }} onFocus={e => (e.currentTarget.style.insetInlineStart = "8px")} onBlur={e => (e.currentTarget.style.insetInlineStart = "-9999px")}>{T("انتقل إلى المحتوى", "Skip to content")}</a>
        <button className="btn ghost icon menu-btn" onClick={() => setOpen(true)} aria-label={T("افتح القائمة", "Open menu")}><Menu /></button>
        <GlobalSearch /><span className="grow" />
        <button className="btn ghost sm" onClick={() => setLang(lang === "ar" ? "en" : "ar")}><Languages /><span lang={lang === "ar" ? "en" : "ar"}>{lang === "ar" ? "English" : "العربية"}</span></button>
        <button className="btn ghost icon" onClick={() => setTheme(theme === "dark" ? "light" : "dark")} aria-label={theme === "dark" ? T("الوضع الفاتح", "Light mode") : T("الوضع الداكن", "Dark mode")}>{theme === "dark" ? <Sun /> : <Moon />}</button>
        <Bell_ />
        <div className="row" style={{ gap: 6, flexWrap: "nowrap" }}><div style={{ textAlign: "end", lineHeight: 1.3 }} className="small who"><div className="strong">{N(user)}</div><div className="muted">{N(user, "role_name")}</div></div>
          <button className="btn ghost icon" onClick={() => { setToken(""); setUser(null); }} aria-label={T("تسجيل الخروج", "Sign out")}><LogOut className="flip" /></button></div></header>
      <main id="content"><Suspense fallback={<Loading />}><Routes>
        <Route path="/" element={<Dashboard />} /><Route path="/strategy" element={<Strategy />} /><Route path="/portfolios" element={<Portfolios kind="portfolios" key="pf" />} /><Route path="/programs" element={<Portfolios kind="programs" key="pg" />} />
        <Route path="/projects" element={<Projects />} /><Route path="/projects/:id" element={<ProjectCenter />} /><Route path="/projects/:id/:tab" element={<ProjectCenter />} />
        <Route path="/initiation" element={<Initiation />} /><Route path="/initiation/:sid" element={<Initiation />} />
        <Route path="/planning" element={P(["تخطيط المشروع", "Project planning"], ["هيكل تقسيم العمل والأنشطة والمخرجات لمشروع واحد.", "The work breakdown, activities and deliverables of one project."], pid => <Planning pid={pid} />)} />
        <Route path="/scheduling" element={P(["الجدولة الزمنية ومخطط Gantt", "Scheduling and Gantt"], ["اسحب الأنشطة، غيّر المدد والاعتماديات، وسيُعاد حساب المسار الحرج.", "Drag activities, change durations and links, and the critical path is recalculated."], pid => <Schedule pid={pid} />)} />
        <Route path="/risks" element={<Picker allowAll title={["إدارة المخاطر", "Risk management"]} sub={["سجل المخاطر ومصفوفتها على مستوى المشروع أو عبر كل المشاريع والمحافظ والبرامج.", "The risk register and matrix for one project, or across all projects, portfolios and programmes."]}>{pid => <Risks pid={pid} key={pid || 0} />}</Picker>} />
        <Route path="/financial" element={P(["الإدارة المالية وضبط المشروع", "Financial management and project controls"], ["الميزانية والمصروفات والالتزامات والقيمة المكتسبة.", "Budget, spend, commitments and earned value."], pid => <Finance pid={pid} />)} />
        <Route path="/resources" element={<Picker allowAll title={["إدارة الموارد", "Resource management"]} sub={["الفرق والتخصيص والاستغلال والتعارضات والطاقة المتاحة.", "Teams, allocation, utilisation, conflicts and available capacity."]}>{pid => <Resources pid={pid} key={pid || 0} />}</Picker>} />
        <Route path="/documents" element={P(["وثائق المشروع", "Project documents"], ["مستودع وثائق مستقل لكل مشروع: رفع، إصدارات، فهرسة، مقارنة.", "A separate repository per project: upload, versions, indexing, comparison."], pid => <Documents pid={pid} />)} />
        <Route path="/knowledge" element={P(["معرفة المشروع والمحادثة الذكية", "Project knowledge and AI chat"], ["حاور وثائق مشروع واحد. الإجابات موثقة بالملف والصفحة والمقتطف.", "Talk to one project's documents. Answers cite the file, page and excerpt."], pid => <Chat pid={pid} />)} />
        <Route path="/governance" element={<Governance />} /><Route path="/automation" element={<Automation />} /><Route path="/reports" element={<Reports />} /><Route path="/copilot" element={<Copilot />} /><Route path="/lessons" element={<Lessons />} /><Route path="/admin" element={<Admin />} />
        <Route path="*" element={<Navigate to="/" replace />} /></Routes></Suspense></main>
    </div></div>;
}
