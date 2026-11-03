"""Data understanding & quality checks, and proposal of (reviewable) cleaning operations."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from .pipeline import category_merge_suggestions, new_op
from .utils import to_jsonable


def _likert_items(dictionary: dict) -> list[str]:
    return [v["name"] for v in dictionary["variables"] if v.get("is_likert") and v.get("role") != "exclude"]


def quality_report(raw: pd.DataFrame, typed: pd.DataFrame, dictionary: dict) -> dict:
    n, p = typed.shape
    variables = {v["name"]: v for v in dictionary["variables"]}
    analysable = [c for c in typed.columns if variables.get(c, {}).get("role") not in ("exclude",)]
    miss = typed[analysable].isna()
    total_cells = max(1, miss.size)
    lk = dictionary.get("likert", {})
    lo, hi = lk.get("min", 1), lk.get("max", 5)
    items = [c for c in _likert_items(dictionary) if c in typed.columns]
    id_cols = [v["name"] for v in dictionary["variables"] if v.get("role") == "id" and v["name"] in typed.columns]
    content_cols = [c for c in analysable if c not in id_cols and variables.get(c, {}).get("role") not in ("date", "response_time")]

    # duplicates
    dup_mask = raw[content_cols].duplicated(keep="first") if content_cols else pd.Series(False, index=raw.index)
    dup_rows = [int(i) for i in raw.index[dup_mask]]
    dup_ids = []
    for c in id_cols:
        d = typed[c][typed[c].notna() & typed[c].duplicated(keep=False)]
        if len(d):
            dup_ids.append({"column": c, "values": sorted(map(str, d.unique()))[:50], "rows": [int(i) for i in d.index]})

    # out of range Likert & non-numeric values in numeric columns
    out_of_range = []
    for c in items:
        x = pd.to_numeric(typed[c], errors="coerce")
        bad = x[(x < lo) | (x > hi)]
        if len(bad):
            out_of_range.append({"column": c, "count": int(len(bad)), "values": sorted(set(map(float, bad)))[:10],
                                 "rows": [int(i) for i in bad.index]})
    nonnumeric = []
    tokens = {t.lower() for t in dictionary.get("missing_tokens", [])}
    for v in dictionary["variables"]:
        if v.get("dtype") == "numeric" and not v.get("value_map") and v["name"] in raw.columns:
            r = raw[v["name"]]
            was_value = ~r.str.strip().str.lower().isin(tokens)
            bad = r[was_value & typed[v["name"]].isna()]
            if len(bad):
                nonnumeric.append({"column": v["name"], "count": int(len(bad)), "examples": list(map(str, bad.unique()[:5])),
                                   "rows": [int(i) for i in bad.index]})

    # response patterns
    straight, low_var, incomplete = [], [], []
    if len(items) >= 5:
        block = typed[items].apply(pd.to_numeric, errors="coerce")
        answered = block.notna().sum(axis=1)
        sd = block.std(axis=1, ddof=0)
        straight = [int(i) for i in block.index[(answered >= 5) & (sd == 0)]]
        # longest run of identical consecutive answers ("long-string") >= 80% of items
        def longest_run(row):
            vals = row.dropna().to_numpy()
            best = cur = 1 if len(vals) else 0
            for a, b in zip(vals[:-1], vals[1:]):
                cur = cur + 1 if a == b else 1
                best = max(best, cur)
            return best
        runs = block.apply(longest_run, axis=1)
        low_var = [int(i) for i in block.index[(runs >= 0.8 * len(items)) & ~block.index.isin(straight)]]
        incomplete = [int(i) for i in block.index[answered < 0.5 * len(items)]]

    # speeders
    speeders, time_info = [], None
    tcols = [v["name"] for v in dictionary["variables"] if v.get("role") == "response_time" and v["name"] in typed.columns]
    if tcols:
        t = pd.to_numeric(typed[tcols[0]], errors="coerce")
        med = t.median()
        if med and med > 0:
            thr = med / 3
            speeders = [int(i) for i in t.index[t < thr]]
            time_info = {"column": tcols[0], "median": float(med), "threshold": float(thr),
                         "rule_en": "duration < one third of the median completion time",
                         "rule_ar": "زمن الاستجابة أقل من ثلث الوسيط"}

    # outliers: univariate (non-Likert numeric) and multivariate (Mahalanobis on Likert items)
    univariate = []
    for v in dictionary["variables"]:
        c = v["name"]
        if v.get("dtype") == "numeric" and not v.get("is_likert") and c in typed.columns and v.get("role") not in ("id",):
            x = pd.to_numeric(typed[c], errors="coerce").dropna()
            if len(x) < 10 or x.std() == 0:
                continue
            q1, q3 = x.quantile([0.25, 0.75])
            iqr = q3 - q1
            lo_f, hi_f = q1 - 3 * iqr, q3 + 3 * iqr
            z = (x - x.mean()) / x.std(ddof=1)
            ext = x[(x < lo_f) | (x > hi_f) | (z.abs() > 3.29)]
            if len(ext):
                univariate.append({"column": c, "count": int(len(ext)), "rows": [int(i) for i in ext.index],
                                   "values": [float(v) for v in ext.values[:20]], "lower_fence": float(lo_f),
                                   "upper_fence": float(hi_f)})
    multivariate = None
    if len(items) >= 3:
        block = typed[items].apply(pd.to_numeric, errors="coerce").dropna()
        if len(block) > len(items) + 10:
            cov = np.cov(block.to_numpy(), rowvar=False)
            inv = np.linalg.pinv(cov)
            diff = block.to_numpy() - block.mean().to_numpy()
            d2 = np.einsum("ij,jk,ik->i", diff, inv, diff)
            crit = stats.chi2.ppf(0.999, df=len(items))
            flagged = block.index[d2 > crit]
            multivariate = {"critical": float(crit), "df": len(items), "count": int(len(flagged)),
                            "rows": [int(i) for i in flagged], "rule_en": "Mahalanobis D² > χ²(.999, k)",
                            "rule_ar": "مسافة ماهالانوبيس D² > χ²(.999، k)"}

    # category inconsistencies
    inconsistent = []
    for v in dictionary["variables"]:
        if v.get("dtype") == "categorical" and v["name"] in typed.columns:
            mapping = category_merge_suggestions(typed[v["name"]])
            if mapping:
                inconsistent.append({"column": v["name"], "mapping": mapping})

    # implausible values (age)
    implausible = []
    for v in dictionary["variables"]:
        nm = v["name"].lower()
        if v.get("dtype") == "numeric" and (nm in ("age", "العمر", "السن") or nm.startswith("age")):
            x = pd.to_numeric(typed[v["name"]], errors="coerce")
            bad = x[(x < 10) | (x > 100)]
            if len(bad):
                implausible.append({"column": v["name"], "count": int(len(bad)), "rows": [int(i) for i in bad.index],
                                    "rule_en": "age outside 10–100", "rule_ar": "العمر خارج النطاق 10–100"})

    per_var = []
    for c in analysable:
        per_var.append({"variable": c, "missing": int(miss[c].sum()), "missing_pct": round(100 * miss[c].mean(), 2),
                        "dtype": variables.get(c, {}).get("dtype"), "role": variables.get(c, {}).get("role")})

    missing_pct = 100 * miss.values.sum() / total_cells
    complete_cases = int((~miss).all(axis=1).sum())
    oor_cells = sum(o["count"] for o in out_of_range)
    # Transparent quality index (0–100): starts at 100 and subtracts documented penalties.
    penalties = {
        "missing": min(30.0, missing_pct * 1.0),
        "duplicates": min(15.0, 100 * len(dup_rows) / max(n, 1)),
        "out_of_range": min(15.0, 100 * oor_cells / max(1, len(items) * n)),
        "straightlining": min(15.0, 100 * len(straight) / max(n, 1)),
        "speeders": min(10.0, 100 * len(speeders) / max(n, 1)),
        "incomplete": min(15.0, 100 * len(incomplete) / max(n, 1)),
    }
    score = max(0.0, 100 - sum(penalties.values()))
    issues = []

    def add(sev, en, ar, count):
        if count:
            issues.append({"severity": sev, "en": en, "ar": ar, "count": int(count)})

    add("high", "Exact duplicate responses", "استجابات مكررة تماماً", len(dup_rows))
    add("high", "Duplicate identifiers", "معرّفات مكررة", sum(len(d["rows"]) for d in dup_ids))
    add("high", "Values outside the Likert range", "قيم خارج نطاق مقياس ليكرت", oor_cells)
    add("medium", "Non-numeric entries in numeric variables", "قيم غير رقمية في متغيرات رقمية", sum(x["count"] for x in nonnumeric))
    add("medium", "Straight-lining (identical answers to all items)", "نمط الإجابة الثابتة على جميع البنود", len(straight))
    add("low", "Long-string responses (≥80% identical in a row)", "سلاسل إجابات متطابقة طويلة (≥80%)", len(low_var))
    add("medium", "Incomplete responses (<50% of items answered)", "استجابات غير مكتملة (أقل من 50% من البنود)", len(incomplete))
    add("medium", "Possible speeders", "استجابات سريعة محتملة", len(speeders))
    add("low", "Univariate extreme values", "قيم متطرفة أحادية", sum(u["count"] for u in univariate))
    add("low", "Multivariate outliers", "قيم متطرفة متعددة المتغيرات", multivariate["count"] if multivariate else 0)
    add("low", "Inconsistent category spellings", "تهجئات فئوية غير متسقة", sum(len(i["mapping"]) for i in inconsistent))
    add("medium", "Implausible values", "قيم غير منطقية", sum(i["count"] for i in implausible))

    return to_jsonable({
        "n_rows": n, "n_columns": p, "n_items": len(items), "total_cells": int(total_cells),
        "missing_cells": int(miss.values.sum()), "missing_pct": round(missing_pct, 2),
        "completeness_pct": round(100 - missing_pct, 2), "complete_cases": complete_cases,
        "rows_with_missing": int(miss.any(axis=1).sum()), "per_variable": per_var,
        "duplicates": {"rows": dup_rows, "count": len(dup_rows), "ids": dup_ids},
        "out_of_range": out_of_range, "nonnumeric": nonnumeric, "straightlining": straight, "longstring": low_var,
        "incomplete": incomplete, "speeders": speeders, "time": time_info, "univariate_outliers": univariate,
        "multivariate_outliers": multivariate, "inconsistent_categories": inconsistent, "implausible": implausible,
        "quality_score": round(score, 1), "penalties": penalties, "issues": issues,
        "likert_range": [lo, hi],
        "score_note_en": "Quality index = 100 − capped penalties for missing data, duplicates, out-of-range values, straight-lining, speeders and incomplete responses. It is a screening aid, not a validity measure.",
        "score_note_ar": "مؤشر الجودة = 100 − خصومات محددة السقف للقيم المفقودة والتكرار والقيم خارج النطاق ونمط الإجابة الثابتة والاستجابات السريعة وغير المكتملة. وهو أداة فرز أولي وليس مقياساً للصدق.",
    })


def propose_operations(report: dict, dictionary: dict) -> list[dict]:
    """Translate detected issues into *pending* operations; nothing is applied until accepted."""
    ops = []
    d = report["duplicates"]
    if d["count"]:
        ops.append(new_op("drop_rows", {"rows": d["rows"]},
                          f"{d['count']} exact duplicate response(s); the first occurrence is kept.",
                          f"{d['count']} استجابة مكررة تماماً؛ يُحتفظ بالظهور الأول.", affected=d["count"], check="duplicates"))
    for o in report["out_of_range"]:
        lk = report["likert_range"]
        ops.append(new_op("set_missing", {"column": o["column"], "min": lk[0], "max": lk[1]},
                          f"{o['count']} value(s) in {o['column']} outside the {lk[0]}–{lk[1]} scale set to missing.",
                          f"{o['count']} قيمة في {o['column']} خارج المقياس {lk[0]}–{lk[1]} تُحوَّل إلى مفقودة.",
                          affected=o["count"], check="out_of_range"))
    for i in report["implausible"]:
        ops.append(new_op("set_missing", {"column": i["column"], "rows": i["rows"]},
                          f"{i['count']} implausible value(s) in {i['column']} ({i['rule_en']}).",
                          f"{i['count']} قيمة غير منطقية في {i['column']} ({i['rule_ar']}).", affected=i["count"], check="implausible"))
    for c in report["inconsistent_categories"]:
        ops.append(new_op("recode", {"column": c["column"], "mapping": c["mapping"]},
                          f"Merge spelling variants in {c['column']}: " + ", ".join(f"'{k}'→'{v}'" for k, v in c["mapping"].items()),
                          f"دمج التهجئات المختلفة في {c['column']}: " + "، ".join(f"'{k}'←'{v}'" for k, v in c["mapping"].items()),
                          affected=len(c["mapping"]), check="categories"))
    if report["straightlining"]:
        k = len(report["straightlining"])
        ops.append(new_op("drop_rows", {"rows": report["straightlining"]},
                          f"{k} respondent(s) gave the identical answer to every Likert item (straight-lining). Review before removing: uniform answers can be genuine.",
                          f"{k} مستجيب أعطى الإجابة نفسها لجميع بنود ليكرت. راجع قبل الحذف؛ فقد تكون الإجابات المتماثلة حقيقية.",
                          affected=k, check="straightlining"))
    if report["incomplete"]:
        k = len(report["incomplete"])
        ops.append(new_op("drop_rows", {"rows": report["incomplete"]},
                          f"{k} respondent(s) answered fewer than 50% of the Likert items.",
                          f"{k} مستجيب أجاب عن أقل من 50% من بنود ليكرت.", affected=k, check="incomplete"))
    if report["speeders"]:
        k = len(report["speeders"])
        ops.append(new_op("drop_rows", {"rows": report["speeders"]},
                          f"{k} respondent(s) completed in less than one third of the median time ({report['time']['median']:.0f}).",
                          f"{k} مستجيب أكمل الاستبانة في أقل من ثلث الزمن الوسيط ({report['time']['median']:.0f}).",
                          affected=k, check="speeders"))
    # Missing Likert answers: person-mean imputation within the dimension (only proposed when sparse).
    for dim in dictionary.get("dimensions", []):
        cols = [c for c in dim["items"] if any(pv["variable"] == c and 0 < pv["missing_pct"] <= 10 for pv in report["per_variable"])]
        if cols:
            total = sum(pv["missing"] for pv in report["per_variable"] if pv["variable"] in cols)
            ops.append(new_op("impute", {"columns": cols, "method": "person_mean", "dimension_items": dim["items"],
                                         "min_answered": 0.5, "round": True},
                              f"{total} sparse missing answer(s) in dimension {dim['name']} replaced by the respondent's mean on the other items of the same dimension (only when ≥ 50% answered). Alternative: leave missing (pairwise/listwise).",
                              f"تعويض {total} إجابة مفقودة في البعد {dim['name']} بمتوسط المستجيب على بقية بنود البعد نفسه (عند الإجابة عن 50% فأكثر). البديل: تركها مفقودة.",
                              affected=total, check="missing"))
    # Outliers are flagged only: no automatic removal is proposed.
    return ops
