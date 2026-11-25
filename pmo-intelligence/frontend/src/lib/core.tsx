import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, ReactNode } from "react";

/* ---------------- API ---------------- */
let token = localStorage.getItem("pmo_token") || "";
export const setToken = (t: string) => { token = t; t ? localStorage.setItem("pmo_token", t) : localStorage.removeItem("pmo_token"); };
export const hasToken = () => !!token;

export class ApiError extends Error { status: number; constructor(msg: string, status: number) { super(msg); this.status = status; } }

async function req(method: string, path: string, body?: any, raw = false): Promise<any> {
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  let payload: any = undefined;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }
  let res: Response;
  try { res = await fetch(`/api${path}`, { method, headers, body: payload }); }
  catch { throw new ApiError("NETWORK", 0); }
  if (res.status === 401 && path !== "/auth/login") { setToken(""); window.dispatchEvent(new Event("pmo-logout")); }
  if (!res.ok) {
    let detail = res.statusText;
    try { const j = await res.json(); detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch { /* not json */ }
    throw new ApiError(detail, res.status);
  }
  return raw ? res.blob() : res.json();
}
export const api = {
  get: (p: string) => req("GET", p), post: (p: string, b?: any) => req("POST", p, b ?? {}), patch: (p: string, b: any) => req("PATCH", p, b),
  put: (p: string, b: any) => req("PUT", p, b), del: (p: string) => req("DELETE", p), blob: (p: string, b?: any) => req(b ? "POST" : "GET", p, b, true),
};
export function saveBlob(blob: Blob, name: string) {
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

/* ---------------- app context: language, theme, user, settings ---------------- */
type Lang = "ar" | "en";
interface Ctx {
  lang: Lang; setLang: (l: Lang) => void; theme: string; setTheme: (t: string) => void;
  T: (ar: string, en: string) => string; N: (o: any, base?: string) => string;
  user: any; setUser: (u: any) => void; can: (p: string) => boolean; meta: any; reloadMeta: () => void;
  num: (v: any, d?: number) => string; money: (v: any) => string; pct: (v: any, d?: number) => string; date: (v: any) => string;
  toast: (msg: string, kind?: "ok" | "error") => void; fail: (e: any) => void;
}
const C = createContext<Ctx>(null as any);
export const useApp = () => useContext(C);

export function AppProvider({ children }: { children: ReactNode }) {
  const [lang, setLangS] = useState<Lang>((localStorage.getItem("pmo_lang") as Lang) || "ar");
  const [theme, setThemeS] = useState(localStorage.getItem("pmo_theme") || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"));
  const [user, setUser] = useState<any>(null);
  const [meta, setMeta] = useState<any>(null);
  const [toasts, setToasts] = useState<{ id: number; msg: string; kind: string }[]>([]);
  useEffect(() => { document.documentElement.lang = lang; document.documentElement.dir = lang === "ar" ? "rtl" : "ltr"; localStorage.setItem("pmo_lang", lang); }, [lang]);
  useEffect(() => { document.documentElement.dataset.theme = theme; localStorage.setItem("pmo_theme", theme); }, [theme]);
  const reloadMeta = useCallback(() => { api.get("/meta").then(setMeta).catch(() => {}); }, []);
  useEffect(() => { if (user) reloadMeta(); else setMeta(null); }, [user, reloadMeta]);
  const toast = useCallback((msg: string, kind: "ok" | "error" = "ok") => {
    const id = Date.now() + Math.random();
    setToasts(t => [...t, { id, msg, kind }]);
    setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), kind === "error" ? 7000 : 3200);
  }, []);
  const value = useMemo<Ctx>(() => {
    const T = (ar: string, en: string) => (lang === "ar" ? ar : en);
    const org = meta?.settings?.org || {};
    const loc = lang === "ar" ? `ar-SA-u-nu-${org.numerals || "latn"}-ca-${org.calendar || "gregory"}` : "en-GB";
    const num = (v: any, d = 0) => (v === null || v === undefined || v === "" || isNaN(+v) ? "—" : new Intl.NumberFormat(loc, { maximumFractionDigits: d, minimumFractionDigits: d }).format(+v));
    const cur = org.currency || "SAR";
    const money = (v: any) => {
      if (v === null || v === undefined || isNaN(+v)) return "—";
      const a = Math.abs(+v);
      const s = a >= 1e6 ? `${num(+v / 1e6, 2)} ${T("مليون", "M")}` : a >= 1e4 ? `${num(+v / 1e3, 0)} ${T("ألف", "K")}` : num(v);
      return `${s} ${cur === "SAR" ? T("ر.س", "SAR") : cur}`;
    };
    return {
      lang, setLang: setLangS, theme, setTheme: setThemeS, T, user, setUser, meta, reloadMeta, num, money, toast,
      N: (o: any, base = "name") => (o ? (lang === "ar" ? o[`${base}_ar`] || o[`${base}_en`] : o[`${base}_en`] || o[`${base}_ar`]) || o[base] || "" : ""),
      can: (p: string) => !!user?.permissions?.includes(p),
      pct: (v: any, d = 0) => (v === null || v === undefined || isNaN(+v) ? "—" : `${num(v, d)}%`),
      date: (v: any) => { if (!v) return "—"; const dt = new Date(String(v).length <= 10 ? `${v}T00:00:00` : v); return isNaN(+dt) ? String(v) : new Intl.DateTimeFormat(loc, { day: "numeric", month: "short", year: "numeric" }).format(dt); },
      fail: (e: any) => {
        const m = e?.message === "NETWORK" ? T("تعذر الاتصال بالخادم. تحقق من الشبكة ثم أعد المحاولة.", "Cannot reach the server. Check the connection and try again.") : e?.message || String(e);
        toast(m, "error");
      },
    };
  }, [lang, theme, user, meta, toast, reloadMeta]);
  return (
    <C.Provider value={value}>
      {children}
      <div className="toasts" role="status" aria-live="polite">{toasts.map(t => <div key={t.id} className={`toast ${t.kind}`}>{t.msg}</div>)}</div>
    </C.Provider>
  );
}

/* ---------------- data hook ---------------- */
export function useLoad<T = any>(path: string | null, deps: any[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(!!path);
  const n = useRef(0);
  const reload = useCallback(() => {
    if (!path) { setData(null); setLoading(false); return Promise.resolve(); }
    const mine = ++n.current;
    setLoading(true);
    return api.get(path).then(d => { if (mine === n.current) { setData(d); setError(null); } })
      .catch(e => { if (mine === n.current) setError(e.message === "NETWORK" ? "NETWORK" : e.message); })
      .finally(() => { if (mine === n.current) setLoading(false); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, ...deps]);
  useEffect(() => { reload(); }, [reload]);
  return { data, error, loading, reload, setData };
}

export const STATUS: Record<string, [string, string, string]> = {
  planned: ["مخطط", "Planned", "info"], active: ["نشط", "Active", "good"], on_hold: ["متوقف", "On hold", "warning"], completed: ["مكتمل", "Completed", ""], cancelled: ["ملغى", "Cancelled", ""],
  not_started: ["لم يبدأ", "Not started", ""], in_progress: ["جارٍ", "In progress", "info"], pending: ["معلق", "Pending", "warning"], achieved: ["تحقق", "Achieved", "good"], missed: ["فائت", "Missed", "critical"],
  open: ["مفتوح", "Open", "warning"], mitigating: ["قيد المعالجة", "Mitigating", "info"], closed: ["مغلق", "Closed", ""], occurred: ["تحقق", "Occurred", "critical"],
  approved: ["معتمد", "Approved", "good"], rejected: ["مرفوض", "Rejected", "critical"], draft: ["مسودة", "Draft", ""], superseded: ["مستبدل", "Superseded", ""], submitted: ["مقدّم", "Submitted", "info"], implemented: ["منفّذ", "Implemented", "good"],
  decided: ["صدر", "Decided", "good"], requested: ["مطلوب", "Requested", "warning"], running: ["جارٍ", "Running", "info"], success: ["نجح", "Succeeded", "good"], failed: ["فشل", "Failed", "critical"], skipped: ["تُجوِّز", "Skipped", ""],
  tracking: ["قيد القياس", "Tracking", "info"], realized: ["تحققت", "Realised", "good"], at_risk: ["مهددة", "At risk", "serious"], acknowledged: ["تم الاطلاع", "Acknowledged", "info"], resolved: ["عولج", "Resolved", "good"],
  low: ["منخفض", "Low", "good"], moderate: ["متوسط", "Moderate", "warning"], medium: ["متوسط", "Medium", "warning"], high: ["عالٍ", "High", "serious"], critical: ["حرج", "Critical", "critical"],
  informational: ["معلومة", "Informational", "info"], advisory: ["إرشادي", "Advisory", "info"], warning: ["تحذير", "Warning", "warning"],
  indexed: ["مفهرس", "Indexed", "good"], processing: ["قيد المعالجة", "Processing", "info"], active_: ["سارٍ", "Active", "good"], expired: ["منتهٍ", "Expired", ""],
  green: ["على المسار", "On track", "good"], amber: ["يحتاج متابعة", "Needs watching", "warning"], red: ["متعثر", "In trouble", "critical"],
  analyzed: ["تم التحليل", "Analysed", "info"], generated: ["قيد المراجعة", "In review", "warning"], activated: ["مفعّل", "Activated", "good"],
  supportive: ["داعم", "Supportive", "good"], neutral: ["محايد", "Neutral", ""], resistant: ["معارض", "Resistant", "critical"],
};
export const ROLE_OPTS = (meta: any, N: any) => (meta?.roles || []).map((r: any) => [r.key, N(r)]);
