const BASE = (import.meta as any).env?.VITE_API_BASE ?? "";

export class ApiError extends Error {
  ar: string;
  status: number;
  constructor(status: number, en: string, ar?: string) {
    super(en);
    this.ar = ar || en;
    this.status = status;
  }
}

export function getToken() {
  try { return localStorage.getItem("ra_token"); } catch { return null; }
}
export function setToken(t: string | null) {
  try { t ? localStorage.setItem("ra_token", t) : localStorage.removeItem("ra_token"); } catch { /* storage unavailable */ }
}

export async function api<T = any>(path: string, opts: RequestInit & { json?: any } = {}): Promise<T> {
  const headers: Record<string, string> = { ...(opts.headers as any) };
  const tok = getToken();
  if (tok) headers.Authorization = `Bearer ${tok}`;
  let body = opts.body;
  if (opts.json !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(opts.json); }
  const res = await fetch(BASE + path, { ...opts, headers, body });
  if (!res.ok) {
    let en = res.statusText, ar: string | undefined;
    try { const j = await res.json(); en = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); ar = j.detail_ar; } catch { /* not json */ }
    if (res.status === 401 && !path.startsWith("/api/auth")) { setToken(null); window.location.hash = "#/login"; }
    throw new ApiError(res.status, en, ar);
  }
  const ct = res.headers.get("content-type") || "";
  return (ct.includes("application/json") ? res.json() : (res.blob() as any)) as T;
}

export async function download(path: string, filename: string) {
  const blob = await api<Blob>(path);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
