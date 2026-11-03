"""Deterministic data pipeline: original (immutable) -> typed -> cleaned -> transformed.

Every derived frame is rebuilt from the original file + the confirmed dictionary +
the ordered list of *accepted* cleaning operations. That makes every analysis
reproducible and lets the researcher restore the original data at any time.
Row identity is the 0-based row number in the original file (`df.index`).
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from .dictionary import _coded, missing_mask
from .utils import AnalysisError, normalize_text

# ---------------------------------------------------------------------------------------
# Typing
# ---------------------------------------------------------------------------------------


def typed_frame(raw: pd.DataFrame, dictionary: dict) -> pd.DataFrame:
    tokens = dictionary.get("missing_tokens")
    out = {}
    for v in dictionary["variables"]:
        name = v["name"]
        if name not in raw.columns:
            continue
        s = raw[name]
        dt = v.get("dtype")
        if dt in ("numeric", "id") and (v.get("value_map") or dt == "numeric"):
            out[name] = _coded(s, v, tokens)
        elif dt == "datetime":
            out[name] = pd.to_datetime(s.where(~missing_mask(s, tokens)), errors="coerce", format="mixed")
        elif dt == "empty":
            out[name] = pd.Series(np.nan, index=raw.index)
        else:
            val = s.where(~missing_mask(s, tokens))
            out[name] = val.astype(object).where(val.notna(), None)
    df = pd.DataFrame(out, index=raw.index)
    # categorical/ordinal numeric codes stay numeric; labels used for grouping
    return df


# ---------------------------------------------------------------------------------------
# Cleaning operations (proposed -> accepted/rejected by the researcher)
# ---------------------------------------------------------------------------------------

OP_TYPES = {
    "drop_rows": ("Remove rows", "حذف صفوف"),
    "set_missing": ("Set values to missing", "تحويل قيم إلى مفقودة"),
    "recode": ("Recode / merge category values", "إعادة ترميز / دمج قيم فئوية"),
    "impute": ("Impute missing values", "تعويض القيم المفقودة"),
    "winsorize": ("Winsorize extreme values", "تهذيب القيم المتطرفة (Winsorize)"),
    "drop_columns": ("Remove variables", "حذف متغيرات"),
    "pseudonymize": ("Pseudonymize identifiers", "إخفاء هوية المعرّفات"),
}


def new_op(op_type: str, params: dict, reason_en: str, reason_ar: str, source: str = "auto",
           affected: int | None = None, check: str | None = None) -> dict:
    if op_type not in OP_TYPES:
        raise AnalysisError(f"Unknown operation type {op_type}", f"نوع عملية غير معروف {op_type}")
    return {"id": uuid.uuid4().hex[:10], "type": op_type, "label_en": OP_TYPES[op_type][0],
            "label_ar": OP_TYPES[op_type][1], "params": params, "reason_en": reason_en, "reason_ar": reason_ar,
            "source": source, "check": check, "status": "pending", "affected": affected,
            "created_at": datetime.now(timezone.utc).isoformat(), "decided_at": None}


def apply_operations(df: pd.DataFrame, ops: list[dict], dictionary: dict) -> tuple[pd.DataFrame, list[dict]]:
    df = df.copy()
    log = []
    for op in ops:
        if op.get("status") != "accepted":
            continue
        t, p = op["type"], op["params"]
        before_rows = len(df)
        changed = 0
        if t == "drop_rows":
            rows = [r for r in p["rows"] if r in df.index]
            df = df.drop(index=rows)
            changed = len(rows)
        elif t == "drop_columns":
            cols = [c for c in p["columns"] if c in df.columns]
            df = df.drop(columns=cols)
            changed = len(cols)
        elif t == "set_missing":
            c = p["column"]
            if c in df.columns:
                if "rows" in p:
                    rows = [r for r in p["rows"] if r in df.index]
                    changed = int(df.loc[rows, c].notna().sum())
                    df.loc[rows, c] = np.nan
                else:
                    lo, hi = p.get("min"), p.get("max")
                    x = pd.to_numeric(df[c], errors="coerce")
                    mask = pd.Series(False, index=df.index)
                    if lo is not None:
                        mask |= x < lo
                    if hi is not None:
                        mask |= x > hi
                    if "values" in p:
                        mask |= df[c].astype(str).isin([str(v) for v in p["values"]])
                    changed = int(mask.sum())
                    df.loc[mask, c] = np.nan
        elif t == "recode":
            c = p["column"]
            if c in df.columns:
                mapping = {str(k): v for k, v in p["mapping"].items()}
                orig = df[c]
                df[c] = orig.map(lambda v: mapping.get(str(v), v) if v is not None and not (isinstance(v, float) and np.isnan(v)) else v)
                changed = int((orig.astype(str) != df[c].astype(str)).sum())
        elif t == "impute":
            method = p.get("method", "median")
            for c in p["columns"]:
                if c not in df.columns:
                    continue
                miss = df[c].isna()
                if not miss.any():
                    continue
                if method == "person_mean":
                    # mean of the respondent's other answered items in the same dimension
                    items = p.get("dimension_items", [])
                    block = df[[i for i in items if i in df.columns]].apply(pd.to_numeric, errors="coerce")
                    min_ans = p.get("min_answered", 0.5)
                    answered = block.notna().mean(axis=1)
                    fill = block.mean(axis=1).where(answered >= min_ans)
                    if p.get("round", True):
                        fill = fill.round()
                    df.loc[miss, c] = fill[miss]
                elif method == "mean":
                    df.loc[miss, c] = pd.to_numeric(df[c], errors="coerce").mean()
                elif method == "median":
                    df.loc[miss, c] = pd.to_numeric(df[c], errors="coerce").median()
                elif method == "mode":
                    m = df[c].dropna().mode()
                    if len(m):
                        df.loc[miss, c] = m.iloc[0]
                changed += int(miss.sum() - df[c].isna().sum())
        elif t == "winsorize":
            c = p["column"]
            x = pd.to_numeric(df[c], errors="coerce")
            lo, hi = x.quantile(p.get("lower", 0.01)), x.quantile(p.get("upper", 0.99))
            changed = int(((x < lo) | (x > hi)).sum())
            df[c] = x.clip(lo, hi)
        elif t == "pseudonymize":
            salt = p.get("salt", "")
            for c in p["columns"]:
                if c in df.columns:
                    df[c] = df[c].map(lambda v: None if v is None or (isinstance(v, float) and np.isnan(v)) else
                                      "P-" + hashlib.sha256(f"{salt}{v}".encode()).hexdigest()[:10])
                    changed += int(df[c].notna().sum())
        log.append({"op_id": op["id"], "type": t, "rows_before": before_rows, "rows_after": len(df), "changed": changed})
    return df, log


# ---------------------------------------------------------------------------------------
# Transformations: reverse coding, composite scores, derived variables
# ---------------------------------------------------------------------------------------


def composite_name(dim_name: str, columns) -> str:
    return dim_name if dim_name not in columns else f"{dim_name}_score"


def transform(df: pd.DataFrame, dictionary: dict) -> tuple[pd.DataFrame, list[dict]]:
    df = df.copy()
    notes = []
    lk = dictionary.get("likert", {})
    lo, hi = lk.get("min", 1), lk.get("max", 5)
    for v in dictionary["variables"]:
        if v.get("reverse") and v["name"] in df.columns:
            df[v["name"]] = (lo + hi) - pd.to_numeric(df[v["name"]], errors="coerce")
            notes.append({"en": f"{v['name']} reverse-coded as ({lo}+{hi}) − x", "ar": f"أعيد ترميز {v['name']} عكسياً: ({lo}+{hi}) − x"})
    min_prop = dictionary.get("composite_min_answered", 0.5)
    composites = {}
    raw_cols = list(df.columns)
    for dim in dictionary.get("dimensions", []):
        items = [i for i in dim["items"] if i in df.columns]
        if not items:
            continue
        block = df[items].apply(pd.to_numeric, errors="coerce")
        score = block.mean(axis=1).where(block.notna().mean(axis=1) >= min_prop)
        name = composite_name(dim["name"], raw_cols)
        df[name] = score
        composites[dim["name"]] = name
    if len(composites) >= 2:
        all_items = [i for dim in dictionary["dimensions"] for i in dim["items"] if i in df.columns]
        block = df[all_items].apply(pd.to_numeric, errors="coerce")
        name = "OVERALL" if "OVERALL" not in df.columns else "OVERALL_score"
        df[name] = block.mean(axis=1).where(block.notna().mean(axis=1) >= min_prop)
        composites["__overall__"] = name
    if composites:
        notes.append({"en": f"Composite scores = mean of available items when ≥ {int(min_prop * 100)}% of the dimension's items were answered.",
                      "ar": f"الدرجة المركبة = متوسط البنود المجاب عنها عندما يُجاب عن {int(min_prop * 100)}% على الأقل من بنود البعد."})
    for d in dictionary.get("derived", []):
        try:
            if d["type"] == "bin":
                x = pd.to_numeric(df[d["source"]], errors="coerce")
                df[d["name"]] = pd.cut(x, bins=d["edges"], labels=d.get("labels"), include_lowest=True).astype(object)
            elif d["type"] in ("mean", "sum"):
                block = df[d["sources"]].apply(pd.to_numeric, errors="coerce")
                df[d["name"]] = block.mean(axis=1) if d["type"] == "mean" else block.sum(axis=1, min_count=1)
            elif d["type"] == "zscore":
                x = pd.to_numeric(df[d["source"]], errors="coerce")
                df[d["name"]] = (x - x.mean()) / x.std(ddof=1)
            elif d["type"] == "log":
                x = pd.to_numeric(df[d["source"]], errors="coerce")
                df[d["name"]] = np.log(x.where(x > 0))
            notes.append({"en": f"Derived variable {d['name']} ({d['type']})", "ar": f"متغير مشتق {d['name']} ({d['type']})"})
        except Exception as exc:  # noqa: BLE001
            notes.append({"en": f"Derived variable {d.get('name')} failed: {exc}", "ar": f"تعذر إنشاء المتغير المشتق {d.get('name')}: {exc}"})
    df.attrs["composites"] = composites
    return df, notes


def apply_filters(df: pd.DataFrame, filters: dict | None) -> pd.DataFrame:
    """filters: {column: [allowed values]} or {column: {"min": a, "max": b}}"""
    if not filters:
        return df
    mask = pd.Series(True, index=df.index)
    for c, f in filters.items():
        if c not in df.columns or f in (None, [], {}):
            continue
        if isinstance(f, dict):
            x = pd.to_numeric(df[c], errors="coerce")
            if f.get("min") is not None:
                mask &= x >= f["min"]
            if f.get("max") is not None:
                mask &= x <= f["max"]
        else:
            allowed = {str(v) for v in f}
            mask &= df[c].map(lambda v: _key(v) in allowed)
    out = df.loc[mask]
    out.attrs = df.attrs
    return out


def _key(v) -> str:
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def fingerprint(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:16]


def category_merge_suggestions(series: pd.Series) -> dict:
    """Group spelling variants (case, spacing, Arabic letter forms) and map them to the most frequent form."""
    counts = series.dropna().astype(str).value_counts()
    groups: dict[str, list[str]] = {}
    for val in counts.index:
        groups.setdefault(normalize_text(val), []).append(val)
    mapping = {}
    for variants in groups.values():
        if len(variants) > 1:
            canonical = max(variants, key=lambda v: counts[v])
            for v in variants:
                if v != canonical:
                    mapping[v] = canonical
    # close misspellings (e.g. 'Femal' vs 'Female') among frequent labels
    import difflib
    keys = [k for k in counts.index if k not in mapping]
    for a in keys:
        if a in mapping:
            continue
        for b in keys:
            if a == b or b in mapping or a in mapping:
                continue
            na, nb = normalize_text(a), normalize_text(b)
            if len(na) >= 4 and difflib.SequenceMatcher(None, na, nb).ratio() >= 0.85 and counts[b] < counts[a] and counts[b] <= max(2, 0.1 * counts[a]):
                mapping[b] = a
    return mapping
