"""Project knowledge base: secure upload, versioning, indexing, and the per-project
chat that combines grounded document answers with facts computed by the engines."""
from __future__ import annotations

import hashlib
import re
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config, models as m, security
from ..engines import scheduling
from ..rag import answer as rag_answer
from ..rag import compare as rag_compare
from ..rag import index as rag_index
from ..rag import retrieval
from ..rag.parsers import ParseError
from ..rag.text import detect_language, normalize, tokens
from . import core

DOC_TYPES = ["charter", "management_plan", "business_case", "scope_statement", "requirements", "technical", "contract",
             "meeting_minutes", "progress_report", "financial_report", "risk_register", "change_request",
             "quality_report", "lessons_learned", "presentation", "spreadsheet", "other"]


class UploadError(ValueError):
    pass


def _safe_name(name: str) -> str:
    name = Path(name or "file").name
    return re.sub(r"[^\w.\-؀-ۿ ]", "_", name)[:180] or "file"


def _store(project_id: int, doc_id: int, version: int, filename: str, data: bytes) -> Path:
    folder = config.STORAGE_DIR / str(project_id) / str(doc_id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"v{version}_{_safe_name(filename)}"
    path.write_bytes(data)
    return path


def _check(filename: str, data: bytes):
    ext = Path(filename or "").suffix.lower()
    if ext not in config.ALLOWED_EXTENSIONS:
        raise UploadError(f"File type {ext or '(none)'} is not allowed. Allowed: {', '.join(sorted(config.ALLOWED_EXTENSIONS))}")
    if not data:
        raise UploadError("The file is empty.")
    if len(data) > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise UploadError(f"The file is larger than {config.MAX_UPLOAD_MB} MB.")


def save_upload(db: Session, user: m.User | None, project: m.Project, filename: str, data: bytes, *, doc_type="other",
                name: str | None = None, folder="/", tags=None, confidentiality=1, access_roles=None, doc_date=None,
                approval_status="draft", source_tag="user", fire_event=True) -> m.Document:
    _check(filename, data)
    doc = m.Document(project_id=project.id, name=name or _safe_name(filename), doc_type=doc_type, folder=folder or "/",
                     tags=tags or [], confidentiality=int(confidentiality), access_roles=access_roles or [],
                     doc_date=doc_date, approval_status=approval_status, uploaded_by=user.id if user else None,
                     current_version=1, source_tag=source_tag)
    db.add(doc)
    db.flush()
    path = _store(project.id, doc.id, 1, filename, data)
    doc.versions.append(m.DocumentVersion(version=1, filename=_safe_name(filename), storage_path=str(path),
                                          sha256=hashlib.sha256(data).hexdigest(), size=len(data),
                                          uploaded_by=user.id if user else None))
    db.flush()
    _index(db, doc)
    security.audit(db, user, "document.upload", "document", doc.id, project.id, {"name": doc.name, "status": doc.processing_status})
    if fire_event:
        from . import automation
        automation.emit(db, "document.uploaded", {"project_id": project.id, "document_id": doc.id, "doc_type": doc.doc_type})
    return doc


def add_version(db: Session, user: m.User, doc: m.Document, filename: str, data: bytes, note: str = "") -> m.Document:
    _check(filename, data)
    v = doc.current_version + 1
    path = _store(doc.project_id, doc.id, v, filename, data)
    doc.versions.append(m.DocumentVersion(version=v, filename=_safe_name(filename), storage_path=str(path),
                                          sha256=hashlib.sha256(data).hexdigest(), size=len(data), uploaded_by=user.id, note=note))
    doc.current_version = v
    db.flush()
    _index(db, doc)
    security.audit(db, user, "document.new_version", "document", doc.id, doc.project_id, {"version": v, "note": note})
    return doc


def _index(db: Session, doc: m.Document):
    try:
        rag_index.index_document(db, doc, core.get_settings(db)["ai"].get("embedding_model", "local-hash-v1"))
    except ParseError:
        pass  # status and reason are stored on the document and shown to the user


def reindex_project(db: Session, project_id: int) -> int:
    n = 0
    for d in db.scalars(select(m.Document).where(m.Document.project_id == project_id)):
        _index(db, d)
        n += d.processing_status == "indexed"
    return n


def doc_dict(d: m.Document) -> dict:
    out = core.to_dict(d)
    out["versions"] = [core.to_dict(v, exclude=("storage_path",)) for v in d.versions]
    return out


# ---------- project chat ----------
_I = lambda *words: re.compile("|".join(words), re.I)
INTENTS = [
    ("conflicts", _I("تعارض", "تناقض", "اختلاف", "قارن", "مقارن", "conflict", "contradict", "discrepan", "compare", "differ")),
    ("exec_report", _I(r"تقرير\S{0,2} تنفيذي", "executive report")),
    ("status", _I("الوضع الحالي", "لخص الوضع", "current status", "status summary")),
    ("summary", _I("لخص", "ملخص", "تلخيص", "summari[sz]e", "summary")),
    ("decisions", _I("القرارات", "قرارات", "decisions")),
    ("actions", _I("المهام", "الإجراءات", "الاجراءات", "الالتزامات", "التزامات", "المسؤول عن", "action items", "open tasks", "commitments", "who is responsible")),
    ("recommendations", _I("التوصيات", "توصيات", "recommendations")),
    ("pending", _I("معلق", "ما زالت", "pending", "outstanding", "unresolved")),
    ("challenges", _I("التحديات", "أسباب التأخير", "اسباب التاخير", "challenges", "reasons for (the )?delay")),
]
LAST = _I("آخر", "اخر", "الأخير", "الاخير", "أحدث", "latest", "last", "most recent")


def _latest(docs: list[m.Document], types: tuple) -> list[m.Document]:
    pool = [d for d in docs if d.doc_type in types] or docs
    pool = sorted(pool, key=lambda d: (d.doc_date or date.min, d.id), reverse=True)
    return pool[:1]


def system_facts(db: Session, project: m.Project, question: str, lang: str) -> list[dict]:
    """Answers that must come from live data and the calculation engines, not from prose."""
    ar = lang == "ar"
    n = normalize(question)
    qt = set(tokens(question))
    blocks = []
    acts = core.leaf_activities(list(db.scalars(select(m.Activity).where(m.Activity.project_id == project.id))))
    today = date.today()
    if re.search("المسار الحرج|critical path", n):
        crit = sorted([a for a in acts if a.is_critical], key=lambda a: a.planned_start or date.min)
        blocks.append({"kind": "calculated", "text": (f"الأنشطة على المسار الحرج ({len(crit)}) — محسوبة بمحرك الجدولة:" if ar else f"Critical-path activities ({len(crit)}) — calculated by the scheduling engine:"),
                       "table": {"head": ["النشاط", "البداية", "النهاية", "الإنجاز %"] if ar else ["Activity", "Start", "End", "Progress %"],
                                 "rows": [[a.name, str(a.planned_start), str(a.planned_end), a.progress or 0] for a in crit]}})
    if "delay" in qt and re.search("انشطه|نشاط|activit", n) and not re.search("تاثير|اثر|impact|effect", n):
        late = [a for a in acts if a.planned_end and a.planned_end < today and (a.progress or 0) < 100]
        blocks.append({"kind": "system", "text": (f"الأنشطة المتأخرة حتى {today}: {len(late)}" if ar else f"Late activities as of {today}: {len(late)}"),
                       "table": {"head": ["النشاط", "النهاية المخططة", "أيام التأخير", "الإنجاز %", "حرج"] if ar else ["Activity", "Planned end", "Days late", "Progress %", "Critical"],
                                 "rows": [[a.name, str(a.planned_end), (today - a.planned_end).days, a.progress or 0, ("نعم" if ar else "Yes") if a.is_critical else ("لا" if ar else "No")] for a in late]}})
    if re.search("تاثير|اثر تاخر|impact|effect", n) and "delay" in qt:
        target = max(acts, key=lambda a: len(set(tokens(a.name)) & qt), default=None)
        if target and set(tokens(target.name)) & qt:
            days = int((re.search(r"(\d+)", n) or [0, 5])[1])
            deps = list(db.scalars(select(m.Dependency).where(m.Dependency.project_id == project.id)))
            all_acts = list(db.scalars(select(m.Activity).where(m.Activity.project_id == project.id)))
            parents = {a.parent_id for a in all_acts if a.parent_id}
            tasks = [scheduling.Task(a.id, a.duration_days or 0, a.constraint_start) for a in all_acts if a.id not in parents]
            ids = {t.id for t in tasks}
            links = [scheduling.Link(d.predecessor_id, d.successor_id, d.type, d.lag_days or 0) for d in deps
                     if d.predecessor_id in ids and d.successor_id in ids]
            r = scheduling.delay_impact(tasks, links, project.start_date or today, target.id, days, core.calendar(db))
            blocks.append({"kind": "calculated", "text": (
                f"أثر تأخر «{target.name}» {days} أيام عمل: ينتقل موعد انتهاء المشروع من {r['finish_before']} إلى {r['finish_after']} "
                f"(انزلاق {r['slip_working_days']} يوم عمل؛ الفائض الزمني للنشاط {r['float_before']} يوماً)." if ar else
                f"Impact of delaying “{target.name}” by {days} working days: project finish moves from {r['finish_before']} to {r['finish_after']} "
                f"({r['slip_working_days']} working days of slip; the activity has {r['float_before']} days of float).")})
    if "milestone" in qt:
        ms = sorted([x for x in db.scalars(select(m.Milestone).where(m.Milestone.project_id == project.id)) if x.status != "achieved"],
                    key=lambda x: x.target_date or date.max)[:6]
        blocks.append({"kind": "system", "text": "المعالم الرئيسية القادمة:" if ar else "Upcoming milestones:",
                       "table": {"head": ["المعلم", "التاريخ المستهدف", "الحالة"] if ar else ["Milestone", "Target date", "Status"],
                                 "rows": [[x.name, str(x.target_date), x.status] for x in ms]}})
    if "risk" in qt:
        rs = [r for r in db.scalars(select(m.Risk).where(m.Risk.project_id == project.id)) if r.status != "closed"]
        if re.search("لم تتم معالج|غير معالج|untreated|not (been )?(treated|mitigated|addressed)", n):
            rs = [r for r in rs if not (r.mitigation or "").strip() or (r.response_deadline and r.response_deadline < today and r.status == "open")]
            title = "مخاطر بلا خطة معالجة أو تجاوزت موعد الاستجابة:" if ar else "Risks with no mitigation or past their response deadline:"
        elif re.search("حرج|critical", n):
            rs = [r for r in rs if r.level == "critical"]
            title = "المخاطر الحرجة المفتوحة:" if ar else "Open critical risks:"
        else:
            rs = sorted(rs, key=lambda r: -(r.score or 0))[:5]
            title = "أعلى المخاطر درجةً في سجل المخاطر:" if ar else "Highest-scoring risks in the register:"
        rs = sorted(rs, key=lambda r: -(r.score or 0))
        blocks.append({"kind": "system", "text": title,
                       "table": {"head": ["الخطر", "الدرجة", "المستوى", "المالك", "المعالجة"] if ar else ["Risk", "Score", "Level", "Owner", "Mitigation"],
                                 "rows": [[r.title, r.score, r.level, r.owner_name or "—", r.mitigation or "—"] for r in rs]}})
    if qt & {"budget", "expense"} or re.search("التوقعات الماليه|forecast|التزامات ماليه|commitments", n):
        mt = core.project_metrics(db, project)
        e = mt["evm"]
        f = lambda v: "—" if v is None else f"{v:,.0f}"
        blocks.append({"kind": "calculated", "text": (f"الوضع المالي من سجلات النظام (تاريخ البيانات {mt['data_date']}):" if ar else f"Financial position from system records (data date {mt['data_date']}):"),
                       "table": {"head": ["البند", "القيمة"] if ar else ["Item", "Value"], "rows": [
                           ["الميزانية المعتمدة" if ar else "Approved budget", f(mt["budget"])],
                           ["المصروفات الفعلية" if ar else "Actual cost", f(mt["actual"])],
                           ["الالتزامات" if ar else "Commitments", f(mt["committed"])],
                           ["المتبقي" if ar else "Remaining", f(mt["remaining"])],
                           ["القيمة المخططة PV" if ar else "Planned value (PV)", f(e["PV"])],
                           ["القيمة المكتسبة EV" if ar else "Earned value (EV)", f(e["EV"])],
                           ["التكلفة المتوقعة عند الإنجاز EAC" if ar else "Estimate at completion (EAC)", f(e["EAC"])],
                           ["CPI", e["CPI"] if e["CPI"] is not None else "—"], ["SPI", e["SPI"] if e["SPI"] is not None else "—"]]}})
    return blocks


def chat(db: Session, user: m.User, project: m.Project, conv: m.ProjectConversation, question: str,
         doc_ids=None, date_from=None, date_to=None, versions="current") -> m.ConversationMessage:
    """One chat turn. Retrieval is scoped to this project and this user's readable documents."""
    lang = detect_language(question)
    ar = lang == "ar"
    settings = core.get_settings(db)
    history = [x.content for x in conv.messages if x.role == "user"]
    db.add(m.ConversationMessage(conversation_id=conv.id, role="user", content=question))
    if not conv.title:
        conv.title = question.strip()[:70]
    docs = retrieval.authorised_documents(db, user, project.id, doc_ids, date_from, date_to)
    intent = next((k for k, rx in INTENTS if rx.search(question)), None)
    blocks, citations, grounded = [], [], True
    not_found = rag_answer.NOT_FOUND[lang]

    def renumber(cs, text):
        off = len(citations)
        if off:
            text = re.sub(r"\[(\d+)\]", lambda mt: f"[{int(mt.group(1)) + off}]", text)
            cs = [{**c, "n": c["n"] + off} for c in cs]
        citations.extend(cs)
        return text

    if intent == "conflicts" and len(docs) >= 2:
        rows = []
        ordered = sorted(docs, key=lambda d: (d.doc_date or date.min, d.id))
        for i, a in enumerate(ordered):
            for b in ordered[i + 1:]:
                rows += rag_compare.compare(db, a, b)
        qt = set(tokens(question))
        focus = [r for r in rows if (r["conflict_type"] == "budget" and "budget" in qt) or (r["conflict_type"] == "scope" and "scope" in qt)
                 or (r["conflict_type"] == "date" and qt & {"schedule", "start", "end"})]
        rows = focus or rows
        rag_compare.store(db, project.id, rows)
        if rows:
            for r in rows:
                for side in ("a", "b"):
                    s = r[f"source_{side}"]
                    citations.append({"n": len(citations) + 1, "document_id": r[f"doc_{side}_id"], "document": r[f"doc_{side}"],
                                      "page": s.get("page"), "section": s.get("section", ""), "snippet": s.get("snippet", r[f"value_{side}"]),
                                      "doc_date": r[f"date_{side}"], "version": None, "approval_status": None})
                r["cite"] = (len(citations) - 1, len(citations))
            blocks.append({"kind": "inferred", "text": (f"وُجد {len(rows)} اختلاف بين الوثائق. لم تُعدَّل أي قيمة؛ القرار لك في تبويب «التعارضات»." if ar else f"{len(rows)} difference(s) found between documents. Nothing was changed; resolve them under “Conflicts”."),
                           "table": {"head": ["البند", "الوثيقة الأولى", "القيمة", "الوثيقة الثانية", "القيمة", "الأهمية", "المصادر"] if ar else ["Item", "Document A", "Value", "Document B", "Value", "Severity", "Sources"],
                                     "rows": [[r["label_ar"] if ar else r["label_en"], r["doc_a"], r["value_a"], r["doc_b"], r["value_b"], r["severity"], f"[{r['cite'][0]}] [{r['cite'][1]}]"] for r in rows]}})
            blocks.append({"kind": "analysis", "text": "\n".join(f"• {x}" for x in dict.fromkeys(r['recommendation_ar'] if ar else r['recommendation_en'] for r in rows))})
        else:
            blocks.append({"kind": "inferred", "text": "لم يُعثر على تعارضات في البنود القابلة للمقارنة (الميزانية، التواريخ، المسؤولون، النطاق، نسب الإنجاز)." if ar else "No conflicts were found in the comparable items (budget, dates, owners, scope, progress)."})
    elif intent in ("summary", "status", "exec_report") and docs:
        pool = docs
        if intent in ("status", "exec_report"):
            pool = sorted([d for d in docs if d.approval_status != "superseded"],
                          key=lambda d: (d.approval_status == "approved", d.doc_date or date.min), reverse=True)
            pool = sorted(pool[:6], key=lambda d: d.doc_date or date.min, reverse=True)[:3]
            mt = core.project_metrics(db, project)
            e = mt["evm"]
            blocks.append({"kind": "system", "text": (
                f"من بيانات النظام ({mt['data_date']}): الإنجاز {mt['progress']}% مقابل مخطط {mt['planned_progress']}%، SPI {e['SPI']}، CPI {e['CPI']}، "
                f"المصروف {mt['actual']:,.0f} من ميزانية {mt['budget']:,.0f}، أنشطة متأخرة {mt['late_activities']}، مخاطر حرجة {mt['risk_counts']['critical']}." if ar else
                f"From system data ({mt['data_date']}): progress {mt['progress']}% against {mt['planned_progress']}% planned, SPI {e['SPI']}, CPI {e['CPI']}, "
                f"spent {mt['actual']:,.0f} of {mt['budget']:,.0f}, {mt['late_activities']} late activities, {mt['risk_counts']['critical']} critical risks.")})
        s = rag_answer.summarize(db, pool, 6 if intent == "summary" else 5)
        if s["citations"]:
            used = sorted({(c["doc_date"] or "", c["document"]) for c in s["citations"]}, reverse=True)
            head = ("ملخص من: " if ar else "Summary of: ") + "، ".join(f"{n} ({d})" if d else n for d, n in used)
            blocks.append({"kind": "documented", "text": head + "\n" + renumber(s["citations"], s["text"])})
        if intent == "exec_report":
            from . import copilot
            blocks.append({"kind": "analysis", "text": copilot.recommendations_text(db, project, lang)})
    elif intent in ("decisions", "actions", "recommendations", "pending", "challenges") and docs:
        pool = docs
        if LAST.search(question):
            pool = _latest(docs, ("meeting_minutes",) if re.search("اجتماع|meeting", question, re.I) else ("progress_report", "meeting_minutes"))
        elif intent in ("decisions", "actions", "pending", "recommendations", "challenges"):
            pool = [d for d in docs if d.doc_type in ("meeting_minutes", "progress_report")] or docs
        s = rag_answer.extract_items(db, pool, intent)
        if s["citations"]:
            names = "، ".join(sorted({c["document"] for c in s["citations"]}))
            blocks.append({"kind": "documented", "text": (f"من {names}:" if ar else f"From {names}:") + "\n" + renumber(s["citations"], s["text"])})
    if not blocks or intent is None:
        blocks += system_facts(db, project, question, lang)
        res = rag_answer.answer(db, user, project.id, question, settings["ai"], history, doc_ids, date_from, date_to, versions)
        if res["grounded"]:
            for b in res["blocks"]:
                blocks.append({**b, "text": renumber(res["citations"], b["text"]) if b is res["blocks"][0] else b["text"]})
        elif not blocks:
            grounded = False
            blocks.append({"kind": "not_found", "text": not_found})
        if res.get("quarantined"):
            blocks.append({"kind": "security", "text": (f"تم تجاهل {res['quarantined']} مقطع في الوثائق لأنه يحتوي تعليمات موجهة للنظام وليست معلومات." if ar else f"{res['quarantined']} passage(s) in the documents were ignored because they contain instructions aimed at the system, not information.")})
    msg = m.ConversationMessage(conversation_id=conv.id, role="assistant", blocks=blocks, citations=citations,
                                content="\n\n".join(b["text"] for b in blocks))
    db.add(msg)
    security.audit(db, user, "chat.ask", "conversation", conv.id, project.id,
                   {"question": question[:300], "intent": intent, "grounded": grounded, "sources": sorted({c["document_id"] for c in citations})})
    db.flush()
    return msg
