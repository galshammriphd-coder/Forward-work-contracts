import { ReactNode, useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import {
  BarChart3, Binary, BookOpenCheck, Brush, ClipboardList, Download, FileText, FlaskConical, FolderKanban, GitBranch, LayoutDashboard,
  LineChart, LogOut, Menu, MessageSquareText, Moon, Network, ScanSearch, Sigma, Sun, Upload, X,
} from "lucide-react";
import { Key, useI18n } from "../lib/i18n";
import { useStore } from "../lib/store";

export const NAV: { to: string; key: Key; icon: any }[] = [
  { to: "/", key: "dashboard", icon: LayoutDashboard },
  { to: "/projects", key: "projects", icon: FolderKanban },
  { to: "/upload", key: "upload", icon: Upload },
  { to: "/eda", key: "eda", icon: ScanSearch },
  { to: "/cleaning", key: "cleaning", icon: Brush },
  { to: "/survey", key: "survey", icon: ClipboardList },
  { to: "/descriptive", key: "descriptive", icon: BarChart3 },
  { to: "/inferential", key: "inferential", icon: Sigma },
  { to: "/reliability", key: "reliability", icon: BookOpenCheck },
  { to: "/hypotheses", key: "hypotheses", icon: FlaskConical },
  { to: "/correlation", key: "correlation", icon: LineChart },
  { to: "/factor", key: "factor", icon: Network },
  { to: "/advanced", key: "advanced", icon: GitBranch },
  { to: "/interpretation", key: "interpretation", icon: MessageSquareText },
  { to: "/reports", key: "reports", icon: FileText },
  { to: "/export", key: "export", icon: Download },
];

export default function Layout({ children }: { children: ReactNode }) {
  const { t, lang, setLang, tr } = useI18n();
  const { user, logout, project, theme, setTheme } = useStore();
  const [open, setOpen] = useState(false);
  const nav = useNavigate();
  const side = (
    <nav className="flex h-full flex-col">
      <div className="flex items-center gap-2 px-4 py-4">
        <div className="grid h-9 w-9 place-items-center rounded-lg bg-brand-700 text-white"><Binary size={20} /></div>
        <div className="leading-tight">
          <div className="font-bold text-ink-900 dark:text-white" dir="ltr">Research Analytics AI</div>
          <div className="text-[11px] text-ink-500">{tr("بيئة بحثية ذكية", "Intelligent research environment")}</div>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto px-2 pb-4">
        {NAV.map(({ to, key, icon: Icon }, i) => (
          <NavLink key={to} to={to} end={to === "/"} onClick={() => setOpen(false)}
            className={({ isActive }) => `mb-0.5 flex items-center gap-2 rounded-lg px-3 py-2 text-sm ${isActive ? "bg-brand-700 text-white" : "text-ink-600 hover:bg-ink-100 dark:text-ink-300 dark:hover:bg-ink-800"}`}>
            <span className="w-5 text-center text-[10px] tabular-nums opacity-60">{i + 1}</span>
            <Icon size={16} className="shrink-0" />
            <span className="truncate">{t(key)}</span>
          </NavLink>
        ))}
      </div>
    </nav>
  );
  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 border-e border-ink-200 bg-white lg:block dark:border-ink-800 dark:bg-ink-900">{side}</aside>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/40" onClick={() => setOpen(false)} />
          <aside className="absolute inset-y-0 start-0 w-72 bg-white dark:bg-ink-900">{side}</aside>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex items-center gap-2 border-b border-ink-200 bg-white/90 px-4 py-2 backdrop-blur dark:border-ink-800 dark:bg-ink-900/90">
          <button className="btn-ghost lg:hidden" onClick={() => setOpen(!open)}>{open ? <X size={18} /> : <Menu size={18} />}</button>
          <button className="min-w-0 truncate text-start text-sm" onClick={() => nav("/projects")}>
            <span className="text-ink-500">{tr("المشروع", "Project")}: </span>
            <b>{project ? project.name : tr("لم يُحدد", "none selected")}</b>
            {project?.is_synthetic && <span className="badge ms-2 bg-amber-100 text-amber-800">{tr("بيانات اصطناعية", "Synthetic data")}</span>}
          </button>
          <div className="ms-auto flex items-center gap-1">
            <button className="btn-ghost" onClick={() => setLang(lang === "ar" ? "en" : "ar")}>{t("language")}</button>
            <button className="btn-ghost" title={t("theme")} onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>{theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}</button>
            <span className="hidden text-xs text-ink-500 sm:inline" dir="ltr">{user?.email}</span>
            <button className="btn-ghost" title={t("logout")} onClick={logout}><LogOut size={16} className="icon-dir" /></button>
          </div>
        </header>
        <main className="mx-auto w-full max-w-7xl flex-1 p-4 md:p-6">{children}</main>
      </div>
    </div>
  );
}
