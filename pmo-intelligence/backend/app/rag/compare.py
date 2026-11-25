"""Document comparison and conflict detection. Reports differences; never overwrites
anything — a person reviews each conflict and decides."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import facts
from .parsers import Segment
from .text import normalize, tokens

# field: (conflict type, kind, severity, changes over time are normal?)
FIELDS = {
    "budget": ("budget", "amount", "high", False),
    "start_date": ("date", "date", "high", False),
    "end_date": ("date", "date", "high", False),
    "duration": ("date", "months", "medium", False),
    "manager": ("owner", "name", "medium", False),
    "sponsor": ("owner", "name", "medium", False),
    "progress": ("progress", "percent", "low", True),
    "actual_cost": ("budget", "amount", "low", True),
}
LABEL = {"budget": ("الميزانية", "Budget"), "start_date": ("تاريخ البداية", "Start date"),
         "end_date": ("تاريخ النهاية", "End date"), "duration": ("المدة", "Duration"),
         "manager": ("مدير المشروع", "Project manager"), "sponsor": ("راعي المشروع", "Sponsor"),
         "progress": ("نسبة الإنجاز", "Progress"), "actual_cost": ("المصروفات الفعلية", "Actual cost"),
         "objectives": ("الأهداف", "Objectives"), "scope": ("النطاق", "Scope"), "duplicate": ("محتوى مكرر", "Duplicate content")}


def _norm(kind: str, value: str):
    if kind == "amount":
        return facts.parse_amount(value)
    if kind == "date":
        return facts.parse_date(value)
    if kind == "months":
        v = facts.parse_duration_months(value)
        return round(v, 1) if v else None
    if kind == "percent":
        v = facts.parse_percent(value)
        return v if v is not None else facts.parse_amount(value)
    return " ".join(t for t in normalize(value).split() if t not in ("م", "د", "ا", "السيد", "المهندس", "الدكتور", "mr", "dr", "eng"))[:60] or None


def doc_facts(db: Session, doc: m.Document, version: int | None = None) -> dict:
    chunks = db.scalars(select(m.DocumentChunk).where(
        m.DocumentChunk.document_id == doc.id, m.DocumentChunk.version == (version or doc.current_version)
    ).order_by(m.DocumentChunk.ordinal))
    segs = [Segment(c.page, c.section or "", c.text, c.kind) for c in chunks if not c.flagged]
    return facts.extract(segs, doc.name)


def _date(d: m.Document):
    return d.doc_date or (d.upload_date.date() if d.upload_date else None)


def _recommend(a: m.Document, b: m.Document, drift: bool) -> tuple[str, str]:
    da, db_ = _date(a), _date(b)
    newer = b if (db_ and da and db_ >= da) else a
    if drift:
        return (f"القيمة تتغير طبيعياً بمرور الوقت؛ اعتمد قيمة «{newer.name}» الأحدث بعد التحقق.",
                f"This value normally changes over time; use the newer “{newer.name}” after checking.")
    approved = [d for d in (a, b) if d.approval_status == "approved"]
    if len(approved) == 1:
        return (f"الوثيقة المعتمدة هي «{approved[0].name}»؛ تحقق من وجود طلب تغيير يبرر القيمة الأخرى.",
                f"“{approved[0].name}” is the approved document; check for a change request that explains the other value.")
    return (f"راجع الوثيقتين مع مالك المشروع؛ «{newer.name}» هي الأحدث تاريخاً لكن الأحدث ليس بالضرورة المعتمد.",
            f"Review both with the project owner; “{newer.name}” is newer, but newer is not necessarily the approved one.")


def compare(db: Session, a: m.Document, b: m.Document) -> list[dict]:
    fa, fb = doc_facts(db, a), doc_facts(db, b)
    rows = []
    for field, (ctype, kind, severity, drift) in FIELDS.items():
        va, vb = fa["scalars"].get(field), fb["scalars"].get(field)
        if not va or not vb:
            continue
        na, nb = _norm(kind, va[0]["value"]), _norm(kind, vb[0]["value"])
        if na is None or nb is None or na == nb:
            continue
        if kind == "amount" and abs(na - nb) / max(na, nb) < 0.001:
            continue
        rec = _recommend(a, b, drift)
        rows.append({"conflict_type": ctype, "field": field, "label_ar": LABEL[field][0], "label_en": LABEL[field][1],
                     "value_a": va[0]["value"][:300], "value_b": vb[0]["value"][:300],
                     "source_a": va[0]["source"], "source_b": vb[0]["source"],
                     "severity": severity, "recommendation_ar": rec[0], "recommendation_en": rec[1]})
    for field in ("objectives", "scope"):
        ta = fa["lists"].get(field) or fa["scalars"].get(field)
        tb = fb["lists"].get(field) or fb["scalars"].get(field)
        if not ta or not tb:
            continue
        text_a = " ".join(x.get("text") or x.get("value") for x in ta)
        text_b = " ".join(x.get("text") or x.get("value") for x in tb)
        sa, sb = set(tokens(text_a)), set(tokens(text_b))
        if sa and sb and len(sa & sb) / len(sa | sb) < 0.6:
            rec = _recommend(a, b, False)
            rows.append({"conflict_type": "scope" if field == "scope" else "objectives", "field": field,
                         "label_ar": LABEL[field][0], "label_en": LABEL[field][1],
                         "value_a": text_a[:300], "value_b": text_b[:300], "source_a": ta[0]["source"],
                         "source_b": tb[0]["source"], "severity": "high" if field == "scope" else "medium",
                         "recommendation_ar": rec[0], "recommendation_en": rec[1]})
    # near-identical documents
    def toks(d):
        return set(t for c in db.scalars(select(m.DocumentChunk.text).where(
            m.DocumentChunk.document_id == d.id, m.DocumentChunk.version == d.current_version)) for t in tokens(c))
    sa, sb = toks(a), toks(b)
    if sa and sb and len(sa & sb) / len(sa | sb) > 0.9:
        rows.append({"conflict_type": "duplicate", "field": "duplicate", "label_ar": LABEL["duplicate"][0],
                     "label_en": LABEL["duplicate"][1], "value_a": a.name, "value_b": b.name,
                     "source_a": {"document": a.name}, "source_b": {"document": b.name}, "severity": "low",
                     "recommendation_ar": "الوثيقتان شبه متطابقتين؛ احتفظ بواحدة كإصدار معتمد.",
                     "recommendation_en": "The two documents are nearly identical; keep one as the approved version."})
    for r in rows:
        r.update(doc_a_id=a.id, doc_b_id=b.id, doc_a=a.name, doc_b=b.name,
                 date_a=_date(a).isoformat() if _date(a) else None, date_b=_date(b).isoformat() if _date(b) else None)
    return rows


def store(db: Session, project_id: int, rows: list[dict]) -> list[m.DocumentConflict]:
    out = []
    for r in rows:
        existing = db.scalar(select(m.DocumentConflict).where(
            m.DocumentConflict.project_id == project_id, m.DocumentConflict.doc_a_id == r["doc_a_id"],
            m.DocumentConflict.doc_b_id == r["doc_b_id"], m.DocumentConflict.conflict_type == r["conflict_type"],
            m.DocumentConflict.value_a == r["value_a"], m.DocumentConflict.value_b == r["value_b"]))
        if existing:
            out.append(existing)
            continue
        c = m.DocumentConflict(project_id=project_id, conflict_type=r["conflict_type"], doc_a_id=r["doc_a_id"],
                               doc_b_id=r["doc_b_id"], value_a=r["value_a"], value_b=r["value_b"],
                               source_a={**r["source_a"], "label_ar": r["label_ar"], "label_en": r["label_en"], "date": r["date_a"]},
                               source_b={**r["source_b"], "date": r["date_b"]}, severity=r["severity"],
                               recommendation=r["recommendation_ar"] + "\n" + r["recommendation_en"])
        db.add(c)
        out.append(c)
    db.flush()
    return out
