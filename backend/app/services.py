"""Project-level services: rebuilding data frames, caching, KPIs, lifecycle status, audit."""
from __future__ import annotations

import copy
import threading
from collections import OrderedDict
from dataclasses import dataclass

import pandas as pd
from sqlalchemy.orm import Session

from .db import AuditLog, Dataset, Project
from .engine.dictionary import build_dictionary
from .engine.ingest import parse_csv
from .engine.pipeline import apply_filters, apply_operations, fingerprint, transform, typed_frame
from .engine.quality import quality_report
from .engine.utils import AnalysisError
from .storage import load_original


@dataclass
class Frames:
    raw: pd.DataFrame
    typed: pd.DataFrame
    clean: pd.DataFrame
    analysis: pd.DataFrame
    op_log: list
    notes: list
    fingerprint: str
    meta: dict


_cache: "OrderedDict[str, Frames]" = OrderedDict()
_raw_cache: "OrderedDict[str, tuple]" = OrderedDict()
_lock = threading.Lock()
_CACHE_SIZE = 12


def audit(db: Session, project_id: str | None, user_id: str | None, action: str, details: dict | None = None) -> None:
    db.add(AuditLog(project_id=project_id, user_id=user_id, action=action, details=details or {}))


def current_dataset(project: Project) -> Dataset | None:
    return project.datasets[-1] if project.datasets else None


def raw_frame(ds: Dataset):
    key = ds.sha256 + ds.delimiter + ds.encoding
    with _lock:
        if key in _raw_cache:
            _raw_cache.move_to_end(key)
            return _raw_cache[key]
    raw = load_original(ds.storage_path, ds.sha256)
    parsed = parse_csv(raw, delimiter=ds.delimiter)
    with _lock:
        _raw_cache[key] = (parsed.df, parsed)
        while len(_raw_cache) > _CACHE_SIZE:
            _raw_cache.popitem(last=False)
    return parsed.df, parsed


def data_fingerprint(project: Project) -> str:
    ds = current_dataset(project)
    accepted = [o for o in (project.cleaning_ops or []) if o.get("status") == "accepted"]
    return fingerprint(ds.sha256 if ds else None, project.dictionary, accepted)


def frames(project: Project) -> Frames:
    ds = current_dataset(project)
    if ds is None:
        raise AnalysisError("No data uploaded for this project yet.", "لم تُرفع بيانات لهذا المشروع بعد.")
    if not project.dictionary:
        raise AnalysisError("The data dictionary has not been created.", "لم يُنشأ قاموس البيانات بعد.")
    fp = data_fingerprint(project)
    with _lock:
        if fp in _cache:
            _cache.move_to_end(fp)
            return _cache[fp]
    raw, parsed = raw_frame(ds)
    d = project.dictionary
    typed = typed_frame(raw, d)
    clean, log = apply_operations(typed, project.cleaning_ops or [], d)
    analysis, notes = transform(clean, d)
    f = Frames(raw=raw, typed=typed, clean=clean, analysis=analysis, op_log=log, notes=notes, fingerprint=fp,
               meta={"encoding": parsed.encoding, "delimiter": parsed.delimiter, "warnings": parsed.warnings})
    with _lock:
        _cache[fp] = f
        while len(_cache) > _CACHE_SIZE:
            _cache.popitem(last=False)
    return f


def analysis_frame(project: Project, filters: dict | None = None) -> pd.DataFrame:
    f = frames(project)
    return apply_filters(f.analysis, filters)


def new_dictionary(project: Project) -> dict:
    ds = current_dataset(project)
    raw, _ = raw_frame(ds)
    return build_dictionary(raw)


def project_quality(project: Project) -> dict:
    f = frames(project)
    return quality_report(f.raw, f.typed, project.dictionary)


def lifecycle(project: Project) -> list[dict]:
    """Status of the 7 data-science lifecycle stages with completion %."""
    ds = current_dataset(project)
    d = project.dictionary or {}
    ops = project.cleaning_ops or []
    kinds = {a.kind for a in project.analyses}
    pending = sum(1 for o in ops if o.get("status") == "pending")
    decided = sum(1 for o in ops if o.get("status") in ("accepted", "rejected"))
    stages = [
        ("understanding", "Data understanding", "فهم البيانات", 100 if ds and d.get("confirmed") else 50 if ds else 0),
        ("cleaning", "Data cleaning", "تنظيف البيانات", 0 if not ds else (100 if ops and pending == 0 else int(100 * decided / len(ops)) if ops else (50 if d.get("confirmed") else 0))),
        ("transformation", "Transformation", "تحويل البيانات", 100 if d.get("confirmed") and d.get("dimensions") else 50 if d.get("confirmed") else 0),
        ("eda", "Exploration (EDA)", "الاستكشاف", 100 if kinds & {"eda", "descriptive", "likert", "normality"} else 0),
        ("modeling", "Modeling & analysis", "النمذجة والتحليل", min(100, 25 * len(kinds - {"eda", "descriptive", "likert", "normality"}))),
        ("evaluation", "Evaluation", "التقييم", 100 if kinds & {"reliability", "validity", "cfa"} and kinds & {"normality"} else 50 if kinds & {"reliability", "validity", "normality", "cfa"} else 0),
        ("reporting", "Reporting", "التقارير", 100 if (project.settings or {}).get("report_generated") else 0),
    ]
    return [{"key": k, "en": en, "ar": ar, "progress": p, "status": "done" if p >= 100 else "in_progress" if p > 0 else "pending"} for k, en, ar, p in stages]


def kpis(project: Project) -> dict:
    ds = current_dataset(project)
    if ds is None or not project.dictionary:
        return {"has_data": False}
    f = frames(project)
    q = project_quality(project)
    d = project.dictionary
    items = [v for v in d["variables"] if v.get("is_likert")]
    return {"has_data": True, "participants_raw": len(f.raw), "participants": len(f.analysis), "variables": len(d["variables"]),
            "questions": len(items), "dimensions": len(d.get("dimensions", [])), "completeness_pct": q["completeness_pct"],
            "missing_pct": q["missing_pct"], "duplicates": q["duplicates"]["count"], "quality_score": q["quality_score"],
            "issues": q["issues"], "dataset": {"filename": ds.filename, "version": ds.version, "sha256": ds.sha256, "encoding": ds.encoding,
                                                "delimiter": ds.delimiter, "uploaded_at": ds.uploaded_at.isoformat(), "size_bytes": ds.size_bytes},
            "composites": f.analysis.attrs.get("composites", {}), "is_synthetic": project.is_synthetic}


def set_json(obj, attr: str, value) -> None:
    """Assign a deep copy so SQLAlchemy detects JSON changes."""
    setattr(obj, attr, copy.deepcopy(value))
