import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from "react";
import { api, getToken, setToken } from "./api";

export type Variable = {
  name: string; label: string; dtype: string; level: string; role: string; dimension?: string | null;
  is_likert: boolean; numeric: boolean; composite: boolean; n_unique: number; values: string[] | null;
};
export type Filters = Record<string, string[] | { min?: number; max?: number }>;

type Store = {
  user: any; setUser: (u: any) => void; logout: () => void;
  projectId: string | null; setProjectId: (id: string | null) => void;
  project: any; reloadProject: () => Promise<void>;
  variables: Variable[]; dictionary: any; reloadVariables: () => Promise<void>;
  filters: Filters; setFilters: (f: Filters) => void;
  theme: "light" | "dark"; setTheme: (t: "light" | "dark") => void;
  version: number; bump: () => void;
};
const C = createContext<Store>(null as any);

export function StoreProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<any>(null);
  const [projectId, setPid] = useState<string | null>(() => { try { return localStorage.getItem("ra_project"); } catch { return null; } });
  const [project, setProject] = useState<any>(null);
  const [variables, setVariables] = useState<Variable[]>([]);
  const [dictionary, setDictionary] = useState<any>(null);
  const [filters, setFilters] = useState<Filters>({});
  const [version, setVersion] = useState(0);
  const [theme, setThemeS] = useState<"light" | "dark">(() => {
    try { return (localStorage.getItem("ra_theme") as any) || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"); } catch { return "light"; }
  });
  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    try { localStorage.setItem("ra_theme", theme); } catch { /* ignore */ }
  }, [theme]);

  useEffect(() => {
    if (getToken()) api("/api/auth/me").then(setUser).catch(() => setUser(null));
  }, []);

  const setProjectId = (id: string | null) => {
    setPid(id);
    setFilters({});
    try { id ? localStorage.setItem("ra_project", id) : localStorage.removeItem("ra_project"); } catch { /* ignore */ }
  };
  const reloadProject = useCallback(async () => {
    if (!projectId) { setProject(null); return; }
    try { setProject(await api(`/api/projects/${projectId}`)); } catch { setProjectId(null); setProject(null); }
  }, [projectId]);
  const reloadVariables = useCallback(async () => {
    if (!projectId) { setVariables([]); setDictionary(null); return; }
    try {
      const [v, d] = await Promise.all([api(`/api/projects/${projectId}/variables`), api(`/api/projects/${projectId}/dictionary`)]);
      setVariables(v.variables); setDictionary(d);
    } catch { setVariables([]); setDictionary(null); }
  }, [projectId]);

  useEffect(() => { if (user) { reloadProject(); reloadVariables(); } }, [user, projectId, version, reloadProject, reloadVariables]);

  const logout = () => { api("/api/auth/logout", { method: "POST" }).catch(() => {}); setToken(null); setUser(null); };
  return (
    <C.Provider value={{ user, setUser, logout, projectId, setProjectId, project, reloadProject, variables, dictionary, reloadVariables,
      filters, setFilters, theme, setTheme: setThemeS, version, bump: () => setVersion((v) => v + 1) }}>
      {children}
    </C.Provider>
  );
}
export const useStore = () => useContext(C);
