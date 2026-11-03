import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Binary, ShieldCheck } from "lucide-react";
import { api, setToken } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { useStore } from "../lib/store";
import { ErrorBox } from "../components/ui";

export default function Auth() {
  const { t, tr, lang, setLang } = useI18n();
  const { setUser } = useStore();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const nav = useNavigate();
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      const r = await api(`/api/auth/${mode}`, { method: "POST", json: { email, password, name } });
      setToken(r.token); setUser(r.user); nav("/projects");
    } catch (err) { setError(err); } finally { setBusy(false); }
  };
  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <div className="hidden flex-col justify-between bg-brand-900 p-10 text-white lg:flex">
        <div className="flex items-center gap-2"><Binary /> <b dir="ltr">Research Analytics AI</b></div>
        <div>
          <h1 className="mb-4 text-3xl font-bold leading-snug">{t("tagline")}</h1>
          <ul className="space-y-2 text-brand-100">
            <li>• {tr("دورة حياة علم البيانات كاملة: من رفع ملف CSV إلى التقرير الأكاديمي", "Full data-science lifecycle: from CSV upload to an academic report")}</li>
            <li>• {tr("محرك إحصائي موثوق (SciPy، statsmodels، pingouin، semopy) — لا تُولَّد القيم بالذكاء الاصطناعي", "Trusted engine (SciPy, statsmodels, pingouin, semopy) — no AI-generated numbers")}</li>
            <li>• {tr("تنظيف قابل للمراجعة مع نسخة أصلية غير قابلة للتعديل", "Reviewable cleaning with an immutable original")}</li>
            <li>• {tr("تفسير أكاديمي وفق APA 7 بالعربية والإنجليزية", "APA 7 interpretation in Arabic and English")}</li>
          </ul>
        </div>
        <div className="flex items-center gap-2 text-sm text-brand-200"><ShieldCheck size={16} />{tr("البيانات مشفرة أثناء التخزين ولا تُرسل لأي خدمة خارجية", "Data encrypted at rest and never sent to external services")}</div>
      </div>
      <div className="flex items-center justify-center p-6">
        <form onSubmit={submit} className="card w-full max-w-sm space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-bold">{mode === "login" ? t("login") : t("register")}</h2>
            <button type="button" className="btn-ghost text-xs" onClick={() => setLang(lang === "ar" ? "en" : "ar")}>{t("language")}</button>
          </div>
          {mode === "register" && <div><label className="label">{t("name")}</label><input className="input" value={name} onChange={(e) => setName(e.target.value)} /></div>}
          <div><label className="label">{t("email")}</label><input className="input" dir="ltr" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></div>
          <div><label className="label">{t("password")}</label><input className="input" dir="ltr" type="password" minLength={8} required value={password} onChange={(e) => setPassword(e.target.value)} /></div>
          <ErrorBox error={error} />
          <button className="btn-primary w-full" disabled={busy}>{mode === "login" ? t("login") : t("register")}</button>
          <button type="button" className="btn-ghost w-full text-xs" onClick={() => setMode(mode === "login" ? "register" : "login")}>
            {mode === "login" ? tr("ليس لديك حساب؟ أنشئ حساباً", "No account? Create one") : tr("لديك حساب؟ سجّل الدخول", "Have an account? Sign in")}
          </button>
        </form>
      </div>
    </div>
  );
}
