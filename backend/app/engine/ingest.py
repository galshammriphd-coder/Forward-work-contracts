"""CSV ingestion: encoding/delimiter detection and raw parsing.

The raw frame keeps every cell as text so that the original file is never altered;
typing happens later, driven by the (researcher-confirmed) data dictionary.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

import pandas as pd

from .utils import AnalysisError

ENCODINGS = ["utf-8-sig", "utf-8", "cp1256", "utf-16", "iso-8859-6", "cp1252", "latin-1"]
DELIMITERS = [",", ";", "\t", "|"]
DEFAULT_MISSING_TOKENS = ["", "na", "n/a", "nan", "null", "none", "-", "?", "#n/a", "missing", "لا يوجد", "غير متوفر"]


@dataclass
class ParsedCSV:
    df: pd.DataFrame
    encoding: str
    had_bom: bool
    delimiter: str
    n_rows: int
    n_cols: int
    warnings: list = field(default_factory=list)


def decode_bytes(raw: bytes) -> tuple[str, str, bool]:
    had_bom = raw.startswith(b"\xef\xbb\xbf")
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16"), "utf-16", True
    for enc in ENCODINGS:
        try:
            text = raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
        # cp1252/latin-1 decode anything; prefer cp1256 when Arabic-range bytes dominate.
        return text, ("utf-8 (BOM)" if enc == "utf-8-sig" and had_bom else enc), had_bom
    raise AnalysisError("Could not decode the file with any supported encoding.",
                        "تعذر فك ترميز الملف بأي من الترميزات المدعومة.")


def detect_delimiter(text: str) -> str:
    sample = "\n".join(text.splitlines()[:50])
    try:
        return csv.Sniffer().sniff(sample, delimiters="".join(DELIMITERS)).delimiter
    except csv.Error:
        pass
    lines = [l for l in sample.splitlines() if l.strip()][:20]
    best, best_score = ",", -1.0
    for d in DELIMITERS:
        counts = [l.count(d) for l in lines]
        if not counts or max(counts) == 0:
            continue
        # consistent count across lines is the strongest signal
        score = min(counts) + (1.0 if len(set(counts)) == 1 else 0.0)
        if score > best_score:
            best, best_score = d, score
    return best


def parse_csv(raw: bytes, delimiter: str | None = None, encoding: str | None = None) -> ParsedCSV:
    if not raw or not raw.strip():
        raise AnalysisError("The file is empty.", "الملف فارغ.")
    if encoding:
        text, enc, had_bom = raw.decode(encoding), encoding, raw.startswith(b"\xef\xbb\xbf")
        text = text.lstrip("﻿")
    else:
        text, enc, had_bom = decode_bytes(raw)
    delim = delimiter or detect_delimiter(text)
    warnings = []
    try:
        df = pd.read_csv(io.StringIO(text), sep=delim, dtype=str, keep_default_na=False,
                         na_filter=False, skip_blank_lines=True, engine="python", on_bad_lines="warn")
    except Exception as exc:  # pragma: no cover - surfaced to the user
        raise AnalysisError(f"Could not parse CSV: {exc}", f"تعذر قراءة ملف CSV: {exc}") from exc
    if df.shape[1] < 1 or df.shape[0] < 1:
        raise AnalysisError("The file has no data rows.", "لا يحتوي الملف على صفوف بيانات.")
    # Clean header names, make them unique.
    names, seen = [], {}
    for i, c in enumerate(df.columns):
        name = str(c).strip().lstrip("﻿") or f"col_{i + 1}"
        if name.startswith("Unnamed:"):
            name = f"col_{i + 1}"
        if name in seen:
            seen[name] += 1
            warnings.append({"en": f"Duplicate column name '{name}' renamed.", "ar": f"تمت إعادة تسمية العمود المكرر '{name}'."})
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 0
        names.append(name)
    df.columns = names
    df = df.apply(lambda s: s.str.strip())
    # Drop rows that are entirely empty.
    empty = (df == "").all(axis=1)
    if empty.any():
        warnings.append({"en": f"{int(empty.sum())} fully empty row(s) ignored.", "ar": f"تم تجاهل {int(empty.sum())} صف فارغ بالكامل."})
        df = df.loc[~empty]
    df = df.reset_index(drop=True)
    return ParsedCSV(df=df, encoding=enc, had_bom=had_bom, delimiter=delim, n_rows=len(df),
                     n_cols=df.shape[1], warnings=warnings)
