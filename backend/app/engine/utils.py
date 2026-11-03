"""Shared helpers for the statistical engine.

All numeric results are produced by tested libraries (NumPy, SciPy, statsmodels,
pingouin, factor_analyzer, semopy, scikit-learn). Nothing here estimates values
heuristically or with a language model.
"""
from __future__ import annotations

import math
import re
from typing import Any, Iterable

import numpy as np
import pandas as pd


class AnalysisError(ValueError):
    """Raised when an analysis cannot be run on the given data (shown to the user)."""

    def __init__(self, en: str, ar: str | None = None):
        super().__init__(en)
        self.en = en
        self.ar = ar or en


def to_jsonable(obj: Any) -> Any:
    """Recursively convert numpy/pandas objects to JSON-safe Python values (NaN/inf -> None)."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        f = float(obj)
        return None if (math.isnan(f) or math.isinf(f)) else f
    if isinstance(obj, np.ndarray):
        return [to_jsonable(v) for v in obj.tolist()]
    if isinstance(obj, pd.Series):
        return [to_jsonable(v) for v in obj.tolist()]
    if isinstance(obj, pd.DataFrame):
        return [to_jsonable(r) for r in obj.to_dict(orient="records")]
    if isinstance(obj, (pd.Timestamp,)):
        return obj.isoformat()
    if obj is pd.NA or obj is pd.NaT:
        return None
    return obj


def fnum(x: Any, d: int = 2) -> str:
    if x is None:
        return "—"
    try:
        f = float(x)
    except (TypeError, ValueError):
        return str(x)
    if math.isnan(f):
        return "—"
    return f"{f:.{d}f}"


def fp(p: Any) -> str:
    """APA 7 p-value formatting: exact to 3 decimals, no leading zero, '< .001'."""
    if p is None:
        return "—"
    p = float(p)
    if math.isnan(p):
        return "—"
    if p < 0.001:
        return "< .001"
    s = f"{p:.3f}"
    return "= " + s.replace("0.", ".", 1) if s.startswith("0.") else "= " + s


def fr(r: Any, d: int = 2) -> str:
    """Format statistics bounded by 1 (r, beta, alpha) without leading zero (APA)."""
    if r is None:
        return "—"
    s = f"{float(r):.{d}f}"
    return s.replace("0.", ".", 1) if s.startswith(("0.", "-0.")) else s


def col(key: str, en: str, ar: str, fmt: str | None = None) -> dict:
    return {"key": key, "en": en, "ar": ar, "fmt": fmt}


def table(tid: str, title_en: str, title_ar: str, columns: list[dict], rows: list[dict],
          note_en: str = "", note_ar: str = "") -> dict:
    return {"id": tid, "title_en": title_en, "title_ar": title_ar, "columns": columns,
            "rows": to_jsonable(rows), "note_en": note_en, "note_ar": note_ar}


def assumption(name_en: str, name_ar: str, test: str, met: bool | None, detail_en: str, detail_ar: str,
               stat: float | None = None, p: float | None = None) -> dict:
    return to_jsonable({"name_en": name_en, "name_ar": name_ar, "test": test, "met": met,
                        "detail_en": detail_en, "detail_ar": detail_ar, "stat": stat, "p": p})


def numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def require_columns(df: pd.DataFrame, cols: Iterable[str]) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise AnalysisError(f"Unknown variable(s): {', '.join(missing)}",
                            f"متغيرات غير موجودة: {', '.join(missing)}")


def require_n(n: int, minimum: int, what: str = "") -> None:
    if n < minimum:
        raise AnalysisError(
            f"Not enough valid observations{(' for ' + what) if what else ''}: n = {n}, minimum {minimum}.",
            f"عدد الملاحظات الصالحة غير كافٍ{(' لـ ' + what) if what else ''}: n = {n}، والحد الأدنى {minimum}.")


_AR_DIACRITICS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")
_AR_INDIC = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫", "01234567890123456789.")


def normalize_text(s: Any) -> str:
    """Normalisation used to detect inconsistent category spellings (Arabic + Latin)."""
    if s is None:
        return ""
    t = str(s).strip().lower()
    t = _AR_DIACRITICS.sub("", t)
    t = re.sub("[إأآا]", "ا", t)
    t = t.replace("ى", "ي").replace("ة", "ه").replace("ؤ", "و").replace("ئ", "ي")
    t = re.sub(r"[\s_\-\.]+", " ", t).strip()
    return t


def arabic_digits_to_latin(s: str) -> str:
    return s.translate(_AR_INDIC)


def cohen_label(value: float, kind: str) -> tuple[str, str]:
    """Conventional (Cohen, 1988) magnitude labels. Context should override these benchmarks."""
    v = abs(value) if value is not None else float("nan")
    thresholds = {
        "d": (0.2, 0.5, 0.8),
        "r": (0.1, 0.3, 0.5),
        "eta2": (0.01, 0.06, 0.14),
        "w": (0.1, 0.3, 0.5),
        "f2": (0.02, 0.15, 0.35),
    }[kind]
    if math.isnan(v):
        return "undetermined", "غير محدد"
    if v < thresholds[0]:
        return "negligible", "ضئيل"
    if v < thresholds[1]:
        return "small", "صغير"
    if v < thresholds[2]:
        return "medium", "متوسط"
    return "large", "كبير"


def result(kind: str, title_en: str, title_ar: str, *, params: dict, n: int | None = None,
           tables: list | None = None, charts: list | None = None, assumptions: list | None = None,
           stats: dict | None = None, warnings: list | None = None, nature: str = "inferential") -> dict:
    """Uniform analysis result envelope consumed by the API, the assistant and the report builder."""
    return to_jsonable({
        "kind": kind, "title_en": title_en, "title_ar": title_ar, "params": params, "n": n,
        "tables": tables or [], "charts": charts or [], "assumptions": assumptions or [],
        "stats": stats or {}, "warnings": warnings or [], "nature": nature,
    })


def warn(en: str, ar: str) -> dict:
    return {"en": en, "ar": ar}
