import { createContext, ReactNode, useContext, useEffect, useState } from "react";

export type Lang = "ar" | "en";

const S = {
  appName: ["Research Analytics AI", "Research Analytics AI"],
  tagline: ["منصة التحليل الإحصائي الذكي للاستبانات والبحوث العلمية", "AI-powered survey analytics & scientific research platform"],
  dashboard: ["لوحة المعلومات الرئيسية", "Dashboard"],
  projects: ["إدارة المشاريع البحثية", "Research projects"],
  upload: ["رفع وتحميل البيانات", "Data upload"],
  eda: ["استكشاف البيانات (EDA)", "Data exploration (EDA)"],
  cleaning: ["تنظيف ومعالجة البيانات", "Data cleaning"],
  survey: ["تحليل الاستبانة", "Questionnaire analysis"],
  descriptive: ["التحليل الإحصائي الوصفي", "Descriptive statistics"],
  inferential: ["التحليل الإحصائي الاستدلالي", "Inferential statistics"],
  reliability: ["الصدق والثبات", "Validity & reliability"],
  hypotheses: ["اختبار الفرضيات", "Hypothesis testing"],
  correlation: ["الارتباط والانحدار", "Correlation & regression"],
  factor: ["التحليل العاملي", "Factor analysis"],
  advanced: ["النماذج الإحصائية المتقدمة", "Advanced models"],
  interpretation: ["تفسير النتائج", "Interpretation"],
  reports: ["التقارير العلمية", "Scientific reports"],
  export: ["تصدير النتائج", "Export"],
  login: ["تسجيل الدخول", "Sign in"],
  register: ["إنشاء حساب", "Create account"],
  logout: ["تسجيل الخروج", "Sign out"],
  email: ["البريد الإلكتروني", "Email"],
  password: ["كلمة المرور", "Password"],
  name: ["الاسم", "Name"],
  run: ["تنفيذ التحليل", "Run analysis"],
  running: ["جارٍ التنفيذ…", "Running…"],
  noProject: ["اختر مشروعاً أو أنشئ مشروعاً جديداً للبدء.", "Select or create a project to start."],
  noData: ["لم تُرفع بيانات لهذا المشروع بعد.", "No data uploaded for this project yet."],
  goUpload: ["رفع البيانات", "Upload data"],
  filters: ["المرشحات", "Filters"],
  clear: ["مسح", "Clear"],
  save: ["حفظ", "Save"],
  cancel: ["إلغاء", "Cancel"],
  delete: ["حذف", "Delete"],
  open: ["فتح", "Open"],
  accept: ["قبول", "Accept"],
  reject: ["رفض", "Reject"],
  pending: ["قيد المراجعة", "Pending"],
  accepted: ["مقبولة", "Accepted"],
  rejected: ["مرفوضة", "Rejected"],
  newProject: ["مشروع جديد", "New project"],
  demoProject: ["مشروع تجريبي (بيانات اصطناعية)", "Demo project (synthetic data)"],
  create: ["إنشاء", "Create"],
  assumptions: ["فحص الافتراضات", "Assumption checks"],
  interpretationTitle: ["التفسير الأكاديمي (APA 7)", "Academic interpretation (APA 7)"],
  limitations: ["حدود الاستنتاج", "Limits of inference"],
  warnings: ["تنبيهات", "Warnings"],
  effect: ["حجم الأثر", "Effect size"],
  significant: ["دال إحصائياً", "Significant"],
  notSignificant: ["غير دال إحصائياً", "Not significant"],
  select: ["— اختر —", "— select —"],
  optional: ["(اختياري)", "(optional)"],
  theme: ["المظهر", "Theme"],
  language: ["English", "العربية"],
  stale: ["نتيجة قديمة: تغيرت البيانات بعد التنفيذ", "Stale: data changed since this run"],
};
export type Key = keyof typeof S;

type Ctx = { lang: Lang; setLang: (l: Lang) => void; t: (k: Key) => string; dir: "rtl" | "ltr"; tr: (ar: string, en: string) => string };
const I18n = createContext<Ctx>(null as any);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>(() => {
    try { return (localStorage.getItem("ra_lang") as Lang) || "ar"; } catch { return "ar"; }
  });
  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
    try { localStorage.setItem("ra_lang", lang); } catch { /* ignore */ }
  }, [lang]);
  const t = (k: Key) => S[k][lang === "ar" ? 0 : 1];
  const tr = (ar: string, en: string) => (lang === "ar" ? ar : en);
  return <I18n.Provider value={{ lang, setLang, t, dir: lang === "ar" ? "rtl" : "ltr", tr }}>{children}</I18n.Provider>;
}

export const useI18n = () => useContext(I18n);

/** Pick the bilingual field of a backend object: obj[`${key}_ar`] / obj[`${key}_en`]. */
export function pick(obj: any, key: string, lang: Lang): string {
  if (!obj) return "";
  return obj[`${key}_${lang}`] ?? obj[`${key}_en`] ?? obj[key] ?? "";
}

export const fmtNum = (v: any, d = 2) => (v === null || v === undefined || Number.isNaN(v) ? "—" : typeof v === "number" ? v.toFixed(d) : String(v));
export const fmtP = (p: any) => (p === null || p === undefined ? "—" : p < 0.001 ? "< .001" : p.toFixed(3).replace(/^0\./, "."));
