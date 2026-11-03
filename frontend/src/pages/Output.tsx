import { useEffect, useRef, useState } from "react";
import { Bot, Download, Eye, FileText, Send, ShieldCheck, Trash2 } from "lucide-react";
import { api, download } from "../lib/api";
import { pick, useI18n } from "../lib/i18n";
import { useStore } from "../lib/store";
import ResultView from "../components/ResultView";
import { ErrorBox, NeedsData, Note, PageHeader } from "../components/ui";

export function Interpretation() {
  const { t, tr, lang } = useI18n();
  const { projectId, version, bump } = useStore();
  const [list, setList] = useState<any[]>([]);
  const [msgs, setMsgs] = useState<{ who: "me" | "bot"; text: string }[]>([]);
  const [q, setQ] = useState("");
  const [shown, setShown] = useState<any>(null);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { if (projectId) api(`/api/projects/${projectId}/analyses`).then(setList).catch(() => setList([])); }, [projectId, version]);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs]);
  const ask = async (question: string, analysis_id?: string) => {
    if (!question && !analysis_id) return;
    setMsgs((m) => [...m, { who: "me", text: question }]);
    setQ("");
    try {
      const r = await api(`/api/projects/${projectId}/assistant`, { method: "POST", json: { question, lang, analysis_id } });
      setMsgs((m) => [...m, { who: "bot", text: r.answer }]);
    } catch (e: any) { setMsgs((m) => [...m, { who: "bot", text: lang === "ar" ? e.ar : e.message }]); }
  };
  const quick = [tr("لخص أهم النتائج", "Summarise the key findings"), tr("ما الفرضيات المدعومة إحصائياً؟", "Which hypotheses are supported?"),
    tr("فسّر نتائج الثبات والصدق", "Interpret reliability and validity"), tr("فسّر نتائج الانحدار", "Interpret the regression results"),
    tr("ما التوصيات البحثية؟", "What are the research recommendations?"), tr("ما حدود الاستنتاج؟", "What are the limitations?")];
  return (
    <div>
      <PageHeader title={t("interpretation")} subtitle={tr("الخطوة 11: المساعد يقرأ النتائج المحسوبة فعلياً فقط ولا يخترع أي قيمة", "Step 11: the assistant reads only computed results and never invents values")} />
      <NeedsData>
        <Note><ShieldCheck size={14} className="me-1 inline" />{tr("يعمل المساعد محلياً على الخادم دون إرسال بياناتك إلى أي خدمة ذكاء اصطناعي خارجية؛ ويصوغ التفسيرات وفق APA 7 من القيم المحسوبة.",
          "The assistant runs locally on the server without sending your data to any external AI service; it phrases APA 7 interpretations from computed values.")}</Note>
        <div className="grid gap-4 lg:grid-cols-5">
          <div className="card flex h-[600px] flex-col lg:col-span-3">
            <div className="flex-1 space-y-3 overflow-y-auto">
              {msgs.length === 0 && <p className="text-sm text-ink-500">{tr("اطرح سؤالاً عن نتائجك أو اختر سؤالاً سريعاً.", "Ask about your results or pick a quick question.")}</p>}
              {msgs.map((m, i) => (
                <div key={i} className={`flex ${m.who === "me" ? "justify-start" : "justify-end"}`}>
                  <div dir="auto" className={`max-w-[90%] whitespace-pre-wrap rounded-xl px-3 py-2 text-sm leading-7 ${m.who === "me" ? "bg-brand-700 text-white" : "bg-ink-100 dark:bg-ink-800"}`}>
                    {m.who === "bot" && <Bot size={14} className="mb-1" />}{m.text}
                  </div>
                </div>
              ))}
              <div ref={end} />
            </div>
            <div className="mt-2 flex flex-wrap gap-1">{quick.map((x) => <button key={x} className="badge border border-ink-300 dark:border-ink-600" onClick={() => ask(x)}>{x}</button>)}</div>
            <form className="mt-2 flex gap-2" onSubmit={(e) => { e.preventDefault(); ask(q); }}>
              <input className="input" dir="auto" value={q} onChange={(e) => setQ(e.target.value)} placeholder={tr("اكتب سؤالك…", "Type your question…")} />
              <button className="btn-primary"><Send size={14} className="icon-dir" /></button>
            </form>
          </div>
          <div className="card max-h-[600px] overflow-y-auto lg:col-span-2">
            <h3 className="mb-2 text-sm font-semibold">{tr("التحليلات المحفوظة", "Saved analyses")}</h3>
            {list.length === 0 && <p className="text-sm text-ink-500">{tr("لا توجد تحليلات.", "No analyses.")}</p>}
            <ul className="space-y-2">
              {list.map((a) => (
                <li key={a.id} className="rounded-lg border border-ink-200 p-2 text-sm dark:border-ink-700">
                  <div className="flex items-start justify-between gap-2">
                    <span>{pick(a, "title", lang)}{a.stale && <span className="badge ms-1 bg-amber-100 text-amber-800">{tr("قديم", "stale")}</span>}</span>
                    <label className="flex shrink-0 items-center gap-1 text-xs"><input type="checkbox" checked={a.in_report} onChange={async (e) => { await api(`/api/projects/${projectId}/analyses/${a.id}`, { method: "PATCH", json: { in_report: e.target.checked } }); bump(); }} />{tr("في التقرير", "in report")}</label>
                  </div>
                  <div className="text-xs text-ink-500">{new Date(a.created_at).toLocaleString(lang === "ar" ? "ar-SA-u-nu-latn-ca-gregory" : "en-GB")}</div>
                  <div className="mt-1 flex gap-1">
                    <button className="btn-ghost px-2 py-0.5 text-xs" onClick={() => ask(tr("فسّر هذه النتيجة", "Explain this result") + `: ${pick(a, "title", lang)}`, a.id)}><Bot size={12} />{tr("فسّر", "Explain")}</button>
                    <button className="btn-ghost px-2 py-0.5 text-xs" onClick={async () => setShown(await api(`/api/projects/${projectId}/analyses/${a.id}`))}><Eye size={12} />{tr("عرض", "View")}</button>
                    <button className="btn-ghost px-2 py-0.5 text-xs text-red-600" onClick={async () => { await api(`/api/projects/${projectId}/analyses/${a.id}`, { method: "DELETE" }); bump(); }}><Trash2 size={12} /></button>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </div>
        {shown && <div className="mt-4"><ResultView result={shown} /></div>}
      </NeedsData>
    </div>
  );
}

const RTYPES = [
  { v: "comprehensive", ar: "تقرير إحصائي شامل", en: "Comprehensive statistical report" },
  { v: "apa", ar: "تقرير أكاديمي وفق APA 7", en: "Academic report (APA 7)" },
  { v: "executive", ar: "تقرير تنفيذي مختصر", en: "Executive summary" },
  { v: "quality", ar: "تقرير جودة البيانات", en: "Data quality report" },
  { v: "hypotheses", ar: "تقرير الفرضيات", en: "Hypotheses report" },
];

export function Reports() {
  const { t, tr, lang } = useI18n();
  const { projectId, project, bump } = useStore();
  const [type, setType] = useState("comprehensive");
  const [rlang, setRlang] = useState(lang);
  const [hid, setHid] = useState("");
  const [html, setHtml] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<any>(null);
  const qs = (format: string) => `/api/projects/${projectId}/report?type=${type}&lang=${rlang}&format=${format}${hid ? `&hypothesis_id=${hid}` : ""}`;
  const previewIt = async () => {
    setBusy(true); setError(null);
    try { const b: Blob = await api(qs("html")); setHtml(URL.createObjectURL(b)); bump(); } catch (e) { setError(e); } finally { setBusy(false); }
  };
  const dl = async (format: string, ext: string) => { setBusy(true); setError(null); try { await download(qs(format), `report_${type}_${rlang}.${ext}`); bump(); } catch (e) { setError(e); } finally { setBusy(false); } };
  return (
    <div>
      <PageHeader title={t("reports")} subtitle={tr("الخطوة 12: تقرير مبني على البيانات الفعلية والتحليلات المحفوظة", "Step 12: a report built from the actual data and saved analyses")} />
      <NeedsData>
        <div className="card mb-4 space-y-3">
          <div className="grid gap-3 sm:grid-cols-3">
            <div><label className="label">{tr("نوع التقرير", "Report type")}</label><select className="input" value={type} onChange={(e) => setType(e.target.value)}>{RTYPES.map((r) => <option key={r.v} value={r.v}>{lang === "ar" ? r.ar : r.en}</option>)}</select></div>
            <div><label className="label">{tr("لغة التقرير", "Report language")}</label><select className="input" value={rlang} onChange={(e) => setRlang(e.target.value as any)}><option value="ar">العربية</option><option value="en">English</option></select></div>
            {type === "hypotheses" && <div><label className="label">{tr("فرضية محددة", "Specific hypothesis")}</label><select className="input" value={hid} onChange={(e) => setHid(e.target.value)}><option value="">{tr("جميع الفرضيات", "All hypotheses")}</option>{(project?.hypotheses || []).map((h: any) => <option key={h.id} value={h.id}>{h.code}</option>)}</select></div>}
          </div>
          <div className="flex flex-wrap gap-2">
            <button className="btn-primary" disabled={busy} onClick={previewIt}><Eye size={14} />{tr("معاينة", "Preview")}</button>
            <button className="btn-secondary" disabled={busy} onClick={() => dl("pdf", "pdf")}><Download size={14} />PDF</button>
            <button className="btn-secondary" disabled={busy} onClick={() => dl("docx", "docx")}><Download size={14} />Word</button>
            <button className="btn-secondary" disabled={busy} onClick={() => dl("xlsx", "xlsx")}><Download size={14} />Excel</button>
            <button className="btn-secondary" disabled={busy} onClick={() => dl("csv", "zip")}><Download size={14} />CSV (zip)</button>
            <button className="btn-secondary" disabled={busy} onClick={() => dl("html", "html")}><Download size={14} />HTML</button>
          </div>
          {busy && <p className="text-sm text-ink-500">{t("running")}</p>}
          <ErrorBox error={error} />
          <p className="text-xs text-ink-500">{tr("يتضمن التقرير: وصف البيانات، منهجية المعالجة، وصف العينة، الإحصاء الوصفي، الصدق والثبات، الاعتدالية، الفرضيات، الارتباط والانحدار، التحليل العاملي، التحليلات المتقدمة، المناقشة، الاستنتاجات والتوصيات، والقيود. تُضاف التحليلات المحددة «في التقرير» من صفحة تفسير النتائج.",
            "Includes: dataset, processing methodology, sample, descriptives, reliability & validity, normality, hypotheses, correlation & regression, factor analysis, advanced analyses, discussion, conclusions & recommendations, limitations. Choose analyses to include from the Interpretation page.")}</p>
        </div>
        {html && <iframe title="report" src={html} className="h-[80vh] w-full rounded-xl border border-ink-200 bg-white dark:border-ink-700" />}
      </NeedsData>
    </div>
  );
}

export function Export() {
  const { t, tr, lang } = useI18n();
  const { projectId, project, bump, version, variables } = useStore();
  const [audit, setAudit] = useState<any[]>([]);
  const [verify, setVerify] = useState<any[] | null>(null);
  const [settings, setSettings] = useState<any>({});
  const [lit, setLit] = useState({ citation: "", finding: "", keywords: "" });
  const [error, setError] = useState<any>(null);
  useEffect(() => { if (projectId) api(`/api/projects/${projectId}/audit`).then(setAudit).catch(() => {}); }, [projectId, version]);
  useEffect(() => { setSettings(project?.settings || {}); }, [project]);
  const saveSettings = async (s = settings) => { try { await api(`/api/projects/${projectId}`, { method: "PATCH", json: { settings: s } }); bump(); } catch (e) { setError(e); } };
  const dl = (path: string, name: string) => download(path, name).catch(setError);
  return (
    <div>
      <PageHeader title={t("export")} subtitle={tr("تصدير البيانات والنتائج، إعدادات الدراسة، إعادة الإنتاج وسجل العمليات", "Data & results export, study settings, reproducibility and audit log")} />
      <NeedsData>
        <ErrorBox error={error} />
        <div className="mb-4 grid gap-4 lg:grid-cols-2">
          <div className="card space-y-2">
            <h3 className="font-semibold">{tr("تصدير البيانات", "Export data")}</h3>
            {[["raw", tr("الأصلية", "Original")], ["clean", tr("بعد التنظيف", "Cleaned")], ["analysis", tr("جاهزة للتحليل", "Analysis-ready")]].map(([s, l]) => (
              <div key={s} className="flex items-center justify-between gap-2 text-sm"><span>{l}</span>
                <div className="flex gap-1"><button className="btn-secondary" onClick={() => dl(`/api/projects/${projectId}/export/data?stage=${s}&format=csv`, `data_${s}.csv`)}>CSV</button>
                  <button className="btn-secondary" onClick={() => dl(`/api/projects/${projectId}/export/data?stage=${s}&format=xlsx`, `data_${s}.xlsx`)}>Excel</button></div></div>
            ))}
            <h3 className="pt-2 font-semibold">{tr("إعادة الإنتاج (Reproducibility)", "Reproducibility")}</h3>
            <div className="flex flex-wrap gap-2">
              <button className="btn-secondary" onClick={async () => { const m = await api(`/api/projects/${projectId}/reproduce`); const b = new Blob([JSON.stringify(m, null, 2)], { type: "application/json" }); const a = document.createElement("a"); a.href = URL.createObjectURL(b); a.download = "reproducibility_manifest.json"; a.click(); }}><FileText size={14} />{tr("ملف إعادة الإنتاج (JSON)", "Manifest (JSON)")}</button>
              <button className="btn-secondary" onClick={async () => setVerify(await api(`/api/projects/${projectId}/reproduce/verify`, { method: "POST" }))}><ShieldCheck size={14} />{tr("إعادة تنفيذ جميع التحليلات والتحقق", "Re-run & verify all analyses")}</button>
            </div>
            {verify && <ul className="text-sm">{verify.map((v) => <li key={v.id}>{v.kind}: <b className={v.status === "identical" ? "text-emerald-600" : "text-amber-600"}>{v.status}</b></li>)}</ul>}
          </div>
          <div className="card space-y-2">
            <h3 className="font-semibold">{tr("إعدادات الدراسة", "Study settings")}</h3>
            <div className="grid gap-2 sm:grid-cols-2">
              <div className="sm:col-span-2"><label className="label">{tr("عنوان الدراسة", "Study title")}</label><input className="input" dir="auto" value={settings.study_title || ""} onChange={(e) => setSettings({ ...settings, study_title: e.target.value })} /></div>
              <div><label className="label">{tr("مستوى الدلالة α", "Significance level α")}</label><input className="input" dir="ltr" type="number" step="0.01" value={settings.alpha ?? 0.05} onChange={(e) => setSettings({ ...settings, alpha: Number(e.target.value) })} /></div>
              <div><label className="label">{tr("طبيعة التحليل", "Analysis mode")}</label><select className="input" value={settings.analysis_mode || "confirmatory"} onChange={(e) => setSettings({ ...settings, analysis_mode: e.target.value })}>
                <option value="confirmatory">{tr("تأكيدي (فرضيات محددة مسبقاً)", "Confirmatory (pre-specified)")}</option><option value="exploratory">{tr("استكشافي", "Exploratory")}</option></select></div>
              <div><label className="label">{tr("طريقة اختيار العينة", "Sampling method")}</label><input className="input" dir="auto" value={settings.sampling_method || ""} onChange={(e) => setSettings({ ...settings, sampling_method: e.target.value })} placeholder={tr("مثال: عينة متاحة", "e.g. convenience sample")} /></div>
              <div><label className="label">{tr("متغير الأوزان (إن وجد)", "Weights variable (if any)")}</label><select className="input" value={settings.weights_variable || ""} onChange={(e) => setSettings({ ...settings, weights_variable: e.target.value || null })}>
                <option value="">—</option>{variables.filter((v) => v.numeric).map((v) => <option key={v.name} value={v.name}>{v.name}</option>)}</select></div>
            </div>
            <button className="btn-primary" onClick={() => saveSettings()}>{t("save")}</button>
            <h4 className="pt-2 text-sm font-semibold">{tr("الأدبيات المرجعية لمناقشة النتائج", "Literature for the discussion")}</h4>
            <div className="grid gap-2 sm:grid-cols-3">
              <input className="input" dir="auto" placeholder={tr("المرجع (APA)", "Citation (APA)")} value={lit.citation} onChange={(e) => setLit({ ...lit, citation: e.target.value })} />
              <input className="input" dir="auto" placeholder={tr("النتيجة الرئيسة", "Key finding")} value={lit.finding} onChange={(e) => setLit({ ...lit, finding: e.target.value })} />
              <input className="input" dir="ltr" placeholder={tr("كلمات مفتاحية/متغيرات (SAT, SQ)", "Keywords/variables (SAT, SQ)")} value={lit.keywords} onChange={(e) => setLit({ ...lit, keywords: e.target.value })} />
            </div>
            <button className="btn-secondary" disabled={!lit.citation} onClick={() => { const s = { ...settings, literature: [...(settings.literature || []), lit] }; setSettings(s); saveSettings(s); setLit({ citation: "", finding: "", keywords: "" }); }}>{tr("إضافة مرجع", "Add reference")}</button>
            <ul className="text-xs">{(settings.literature || []).map((l: any, i: number) => <li key={i}>• {l.citation} — {l.finding} <span className="text-ink-400">[{l.keywords}]</span></li>)}</ul>
          </div>
        </div>
        <div className="card">
          <h3 className="mb-2 font-semibold">{tr("سجل العمليات (Audit log)", "Audit log")}</h3>
          <div className="max-h-96 overflow-auto">
            <table className="tbl"><thead><tr><th>{tr("الوقت", "Time")}</th><th>{tr("العملية", "Action")}</th><th>{tr("التفاصيل", "Details")}</th></tr></thead>
              <tbody>{audit.map((a) => <tr key={a.id}><td className="whitespace-nowrap text-xs" dir="ltr">{new Date(a.ts).toLocaleString(lang === "ar" ? "ar-SA-u-nu-latn-ca-gregory" : "en-GB")}</td><td className="text-xs font-medium" dir="ltr">{a.action}</td>
                <td className="max-w-xl truncate text-xs text-ink-500" dir="ltr" title={JSON.stringify(a.details)}>{JSON.stringify(a.details)}</td></tr>)}</tbody></table>
          </div>
        </div>
      </NeedsData>
    </div>
  );
}
