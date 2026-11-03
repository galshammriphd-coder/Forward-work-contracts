"""Questionnaire structure detection and the data dictionary.

Everything produced here is a *suggestion*. The researcher confirms or edits the
dictionary (types, measurement levels, dimensions, reverse items, Likert range)
before any analysis uses it. Dimensions are only proposed when the column names
show a clear item grouping; otherwise `structure_confident` is False and the UI
asks the researcher to define the dimensions.
"""
from __future__ import annotations

import re
from collections import OrderedDict

import numpy as np
import pandas as pd

from .ingest import DEFAULT_MISSING_TOKENS
from .utils import arabic_digits_to_latin, normalize_text

DEMOGRAPHIC_KEYWORDS = [
    "gender", "sex", "age", "education", "qualification", "degree", "experience", "years", "department", "faculty",
    "college", "nationality", "marital", "income", "salary", "region", "city", "country", "job", "position", "role",
    "occupation", "major", "specialization", "level", "grade", "rank", "sector", "employment", "group",
    "الجنس", "النوع", "العمر", "السن", "المؤهل", "الخبرة", "سنوات", "القسم", "الكلية", "الجنسية", "الحالة", "الدخل",
    "الراتب", "المنطقة", "المدينة", "الوظيفة", "المسمى", "التخصص", "المستوى", "الرتبة", "القطاع", "الدرجة", "الفئة",
]
ID_KEYWORDS = ["id", "respondent", "participant", "subject", "record", "serial", "رقم", "المعرف", "الرمز", "مسلسل"]
CONTINUOUS_DEMOGRAPHICS = ["age", "years", "experience", "income", "salary", "العمر", "السن", "الخبرة", "سنوات", "الدخل", "الراتب"]
TIME_KEYWORDS = ["duration", "time", "seconds", "secs", "elapsed", "response_time", "المدة", "الزمن", "الوقت", "ثواني"]
DATE_KEYWORDS = ["date", "timestamp", "submitted", "started", "التاريخ", "تاريخ"]
REVERSE_PATTERNS = [r"[_\-\s\.](r|rev|reverse|reversed|neg)$", r"\(r\)$", r"(?<=\d)r$", r"عكسي", r"_ع$"]

# Text Likert anchors (agreement scales) -> numeric code. Used only to *propose* a value map.
TEXT_LIKERT_SCALES = [
    {"strongly disagree": 1, "disagree": 2, "neutral": 3, "neither agree nor disagree": 3, "undecided": 3,
     "agree": 4, "strongly agree": 5},
    {"غير موافق بشدة": 1, "لا اوافق بشده": 1, "لا أوافق بشدة": 1, "معارض بشده": 1, "غير موافق": 2, "لا اوافق": 2,
     "لا أوافق": 2, "معارض": 2, "محايد": 3, "غير متاكد": 3, "موافق": 4, "اوافق": 4, "موافق بشده": 5, "اوافق بشده": 5,
     "موافق بشدة": 5, "أوافق بشدة": 5},
    {"never": 1, "rarely": 2, "sometimes": 3, "often": 4, "always": 5},
    {"ابدا": 1, "نادرا": 2, "احيانا": 3, "غالبا": 4, "دائما": 5},
    {"very low": 1, "low": 2, "moderate": 3, "medium": 3, "high": 4, "very high": 5},
    {"منخفضه جدا": 1, "منخفضه": 2, "متوسطه": 3, "مرتفعه": 4, "مرتفعه جدا": 5},
]

LEVEL_LABELS = {
    2: (["Low", "High"], ["منخفض", "مرتفع"]),
    3: (["Low", "Moderate", "High"], ["منخفض", "متوسط", "مرتفع"]),
    4: (["Very low", "Low", "High", "Very high"], ["منخفض جداً", "منخفض", "مرتفع", "مرتفع جداً"]),
    5: (["Very low", "Low", "Moderate", "High", "Very high"], ["منخفض جداً", "منخفض", "متوسط", "مرتفع", "مرتفع جداً"]),
    6: (["Very low", "Low", "Somewhat low", "Somewhat high", "High", "Very high"],
        ["منخفض جداً", "منخفض", "منخفض نسبياً", "مرتفع نسبياً", "مرتفع", "مرتفع جداً"]),
    7: (["Very low", "Low", "Somewhat low", "Moderate", "Somewhat high", "High", "Very high"],
        ["منخفض جداً", "منخفض", "منخفض نسبياً", "متوسط", "مرتفع نسبياً", "مرتفع", "مرتفع جداً"]),
}
ANCHOR_LABELS = {
    5: (["Strongly disagree", "Disagree", "Neutral", "Agree", "Strongly agree"],
        ["غير موافق بشدة", "غير موافق", "محايد", "موافق", "موافق بشدة"]),
    4: (["Strongly disagree", "Disagree", "Agree", "Strongly agree"], ["غير موافق بشدة", "غير موافق", "موافق", "موافق بشدة"]),
    3: (["Disagree", "Neutral", "Agree"], ["غير موافق", "محايد", "موافق"]),
    7: (["Strongly disagree", "Disagree", "Somewhat disagree", "Neutral", "Somewhat agree", "Agree", "Strongly agree"],
        ["غير موافق بشدة", "غير موافق", "غير موافق إلى حد ما", "محايد", "موافق إلى حد ما", "موافق", "موافق بشدة"]),
}


def _matches(name: str, keywords: list[str]) -> bool:
    n = normalize_text(name)
    tokens = set(re.split(r"[\s_\-\.\(\)/]+", n))
    for k in keywords:
        kn = normalize_text(k)
        if kn in tokens or (len(kn) > 3 and kn in n):
            return True
    return False


def to_numeric_series(s: pd.Series, missing_tokens: list[str] | None = None) -> pd.Series:
    tokens = {t.lower() for t in (missing_tokens or DEFAULT_MISSING_TOKENS)}
    cleaned = s.astype(str).map(lambda v: arabic_digits_to_latin(v).replace("،", ".").strip())
    cleaned = cleaned.where(~cleaned.str.lower().isin(tokens), np.nan)
    return pd.to_numeric(cleaned, errors="coerce")


def missing_mask(s: pd.Series, missing_tokens: list[str] | None = None) -> pd.Series:
    tokens = {t.lower() for t in (missing_tokens or DEFAULT_MISSING_TOKENS)}
    return s.isna() | s.astype(str).str.strip().str.lower().isin(tokens)


def _text_likert_map(values: list[str]) -> dict | None:
    norm = {v: normalize_text(v) for v in values}
    for scale in TEXT_LIKERT_SCALES:
        nscale = {normalize_text(k): v for k, v in scale.items()}
        if all(n in nscale for n in norm.values()) and len(values) >= 2:
            return {orig: nscale[n] for orig, n in norm.items()}
    return None


def item_prefix(name: str) -> tuple[str | None, bool]:
    """Return (prefix, reverse_flag_from_name) for item-like names such as 'SQ3', 'trust_2', 'EE4_r'."""
    n = name.strip()
    rev = any(re.search(p, n, flags=re.IGNORECASE) for p in REVERSE_PATTERNS)
    base = n
    for p in REVERSE_PATTERNS:
        base = re.sub(p, "", base, flags=re.IGNORECASE)
    m = re.match(r"^(.*?\D)[_\-\s\.]?(\d+)$", base)
    if not m:
        return None, rev
    prefix = m.group(1).rstrip("_-. ")
    return (prefix or None), rev


def build_dictionary(raw: pd.DataFrame, missing_tokens: list[str] | None = None) -> dict:
    n = len(raw)
    variables = []
    for name in raw.columns:
        s = raw[name]
        miss = missing_mask(s, missing_tokens)
        valid = s[~miss]
        nonmiss = int((~miss).sum())
        num = to_numeric_series(s, missing_tokens)
        numeric_share = (num.notna().sum() / nonmiss) if nonmiss else 0
        n_unique = int(valid.nunique())
        var = OrderedDict(name=name, label=name, description="", dtype="categorical", level="nominal", role="other",
                          dimension=None, is_likert=False, reverse=False, reverse_suggested=False, reverse_reason="",
                          value_map=None, values="", n_missing=int(miss.sum()), n_unique=n_unique, detection=[])
        if nonmiss == 0:
            var.update(dtype="empty", role="exclude", detection=["all values missing"])
            variables.append(var)
            continue
        is_numeric = numeric_share >= 0.95
        if is_numeric:
            vals = num.dropna()
            is_int = bool(np.allclose(vals, vals.round()))
            var["values"] = f"{vals.min():g} – {vals.max():g}"
            if _matches(name, ID_KEYWORDS) and n_unique >= 0.9 * nonmiss:
                var.update(dtype="id", level="nominal", role="id", detection=["name looks like identifier; unique values"])
            elif _matches(name, TIME_KEYWORDS):
                var.update(dtype="numeric", level="ratio", role="response_time", detection=["name suggests response duration"])
            elif is_int and n_unique == nonmiss == n and (vals.sort_values().diff().dropna() == 1).all():
                var.update(dtype="id", level="nominal", role="id", detection=["consecutive unique integers"])
            elif _matches(name, DEMOGRAPHIC_KEYWORDS):
                continuous = n_unique > 10 or (_matches(name, CONTINUOUS_DEMOGRAPHICS) and not is_int or _matches(name, CONTINUOUS_DEMOGRAPHICS) and vals.max() > 12)
                level = "ratio" if continuous else "ordinal"
                var.update(dtype="numeric" if continuous else "categorical", level=level, role="demographic",
                           detection=["name matches demographic keyword"])
                if not continuous:
                    var["values"] = ", ".join(map(lambda v: f"{v:g}", sorted(vals.unique())))
            elif is_int and 3 <= n_unique <= 11 and vals.min() >= 0 and vals.max() <= 11:
                var.update(dtype="numeric", level="ordinal", role="item", is_likert=True,
                           detection=[f"integer values {vals.min():g}–{vals.max():g} with {n_unique} levels (Likert-type)"])
                var["values"] = ", ".join(map(lambda v: f"{v:g}", sorted(vals.unique())))
            else:
                var.update(dtype="numeric", level="ratio" if vals.min() >= 0 else "interval", role="other",
                           detection=["continuous numeric"])
        else:
            uniq = list(valid.unique())
            tmap = _text_likert_map(uniq) if n_unique <= 7 else None
            avg_len = valid.astype(str).str.len().mean()
            parsed_dates = pd.to_datetime(valid, errors="coerce", format="mixed") if _matches(name, DATE_KEYWORDS) else None
            if parsed_dates is not None and parsed_dates.notna().mean() > 0.9:
                var.update(dtype="datetime", level="interval", role="date", detection=["date/time values"])
            elif tmap:
                var.update(dtype="numeric", level="ordinal", role="item", is_likert=True, value_map=tmap,
                           detection=["text agreement anchors mapped to numeric codes (please verify)"])
                var["values"] = "; ".join(f"{k}={v}" for k, v in sorted(tmap.items(), key=lambda kv: kv[1]))
            elif _matches(name, ID_KEYWORDS) and n_unique >= 0.9 * nonmiss:
                var.update(dtype="id", role="id", detection=["identifier"])
            elif avg_len > 30 or (n_unique > max(15, 0.5 * nonmiss) and avg_len > 12):
                var.update(dtype="text", level="nominal", role="open_text",
                           detection=[f"free text (mean length {avg_len:.0f} chars)"])
            else:
                multi = valid.astype(str).str.contains(r"[;|]").mean() > 0.2
                if multi:
                    var.update(dtype="multiselect", role="item", detection=["multiple-response values separated by ';' or '|'"])
                else:
                    var.update(dtype="categorical", level="nominal",
                               role="demographic" if _matches(name, DEMOGRAPHIC_KEYWORDS) or n_unique <= 12 else "other",
                               detection=["categorical text"])
                counts = valid.value_counts()
                var["values"] = ", ".join(map(str, counts.index[:15])) + (" …" if len(counts) > 15 else "")
        variables.append(var)

    # ---- group Likert items into dimensions by name prefix ------------------------------
    groups: dict[str, list[dict]] = OrderedDict()
    for v in variables:
        if v["is_likert"]:
            prefix, rev = item_prefix(v["name"])
            if rev:
                v["reverse_suggested"], v["reverse_reason"] = True, "name suffix indicates reverse-keyed item"
            if prefix:
                groups.setdefault(prefix, []).append(v)
    dimensions = []
    for prefix, items in groups.items():
        if len(items) >= 2:
            for v in items:
                v["dimension"] = prefix
            dimensions.append({"name": prefix, "label": prefix, "items": [v["name"] for v in items], "axis": None})
    likert_vars = [v for v in variables if v["is_likert"]]
    ungrouped = [v["name"] for v in likert_vars if not v["dimension"]]
    structure_confident = bool(dimensions) and not ungrouped

    # ---- statistical reverse-item suggestion: negative corrected item-total correlation ---
    for d in dimensions:
        if len(d["items"]) < 3:
            continue
        block = pd.DataFrame({c: _coded(raw[c], next(v for v in variables if v["name"] == c), missing_tokens)
                              for c in d["items"]}).dropna()
        if len(block) < 10:
            continue
        total = block.sum(axis=1)
        for c in d["items"]:
            r = np.corrcoef(block[c], total - block[c])[0, 1] if block[c].std() > 0 else np.nan
            v = next(v for v in variables if v["name"] == c)
            if not np.isnan(r) and r < 0:
                v["reverse_suggested"] = True
                v["reverse_reason"] = (v["reverse_reason"] + "; " if v["reverse_reason"] else "") + \
                    f"negative corrected item-total correlation (r = {r:.2f})"

    # ---- Likert range -----------------------------------------------------------------------
    likert = default_likert_config(raw, variables, missing_tokens)
    return {"variables": variables, "dimensions": dimensions, "likert": likert,
            "structure_confident": structure_confident, "ungrouped_items": ungrouped,
            "missing_tokens": missing_tokens or DEFAULT_MISSING_TOKENS, "derived": [], "confirmed": False}


def _coded(s: pd.Series, var: dict, missing_tokens=None) -> pd.Series:
    if var.get("value_map"):
        m = {normalize_text(k): v for k, v in var["value_map"].items()}
        return s.map(lambda x: m.get(normalize_text(x), np.nan)).astype(float)
    return to_numeric_series(s, missing_tokens)


def default_likert_config(raw: pd.DataFrame, variables: list[dict], missing_tokens=None) -> dict:
    lik = [v for v in variables if v["is_likert"]]
    if not lik:
        return {"min": 1, "max": 5, "points": 5, "anchors_en": ANCHOR_LABELS[5][0], "anchors_ar": ANCHOR_LABELS[5][1],
                "interpretation": interpretation_bands(1, 5, 5), "detected": False}
    mins, maxs = [], []
    for v in lik:
        x = _coded(raw[v["name"]], v, missing_tokens).dropna()
        if len(x):
            mins.append(x.min())
            maxs.append(x.max())
    # mode of observed max is robust to the odd out-of-range value
    lo = int(pd.Series(mins).mode().iloc[0]) if mins else 1
    hi = int(pd.Series(maxs).mode().iloc[0]) if maxs else 5
    lo = 0 if lo == 0 else 1
    points = hi - lo + 1
    anchors = ANCHOR_LABELS.get(points, ([f"{i}" for i in range(lo, hi + 1)], [f"{i}" for i in range(lo, hi + 1)]))
    return {"min": lo, "max": hi, "points": points, "anchors_en": anchors[0], "anchors_ar": anchors[1],
            "interpretation": interpretation_bands(lo, hi, min(points, 5) if points not in LEVEL_LABELS else points),
            "detected": True}


def interpretation_bands(lo: float, hi: float, k: int) -> list[dict]:
    """Equal-width interpretation bands: width = (max - min) / k (e.g. 0.80 for a 1–5 scale with 5 bands)."""
    k = max(2, min(7, int(k)))
    width = (hi - lo) / k
    en, ar = LEVEL_LABELS[k]
    bands = []
    for i in range(k):
        a = lo + i * width
        b = hi if i == k - 1 else lo + (i + 1) * width
        bands.append({"from": round(a, 4), "to": round(b, 4), "en": en[i], "ar": ar[i]})
    return bands


def band_for(mean: float | None, bands: list[dict]) -> dict | None:
    if mean is None or pd.isna(mean):
        return None
    for i, b in enumerate(bands):
        if (mean >= b["from"] and mean < b["to"]) or (i == len(bands) - 1 and mean <= b["to"] + 1e-9 and mean >= b["from"]):
            return b
    return bands[0] if mean < bands[0]["from"] else bands[-1]


def validate_dictionary(d: dict, columns: list[str]) -> list[str]:
    errors = []
    names = {v["name"] for v in d.get("variables", [])}
    for c in columns:
        if c not in names:
            errors.append(f"Column '{c}' missing from dictionary")
    for dim in d.get("dimensions", []):
        for it in dim.get("items", []):
            if it not in names:
                errors.append(f"Dimension '{dim['name']}' references unknown item '{it}'")
    lk = d.get("likert", {})
    if lk and lk.get("min", 1) >= lk.get("max", 5):
        errors.append("Likert minimum must be smaller than maximum")
    return errors
