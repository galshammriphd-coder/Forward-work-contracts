"""Export orchestration: one folder per export, file name = operation name + timestamp."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from exports.common import export_folder, register_export
from exports.csv_export import export_csv
from exports.excel_export import export_excel, export_report_excel
from exports.json_export import export_json
from exports.pdf_export import export_report_pdf

DATA_FORMATS = ("xlsx", "csv", "json")
REPORT_FORMATS = ("xlsx", "pdf")


def export_posts(df: pd.DataFrame, fmt: str, name: str, job_id: int | None = None, filters: dict | None = None,
                 actor: str | None = None, base: Path | None = None, include_raw: bool = False) -> Path:
    fmt = fmt.lower()
    if fmt not in DATA_FORMATS:
        raise ValueError(f"صيغة غير مدعومة: {fmt}")
    folder, stem = export_folder(name, base)
    meta = {"name": name, "job_id": job_id, "filters": filters or {}, "records": len(df)}
    if fmt == "xlsx":
        path = export_excel(df, folder, stem, meta={"العملية": name, "المرشحات": str(filters or {})})
    elif fmt == "csv":
        path = export_csv(df, folder, stem)
    else:
        path = export_json(df, folder, stem, meta=meta, include_raw=include_raw)
    register_export(path, fmt, len(df), job_id=job_id, filters=filters, actor=actor)
    return path


def export_posts_all_formats(df: pd.DataFrame, name: str, job_id: int | None = None, filters: dict | None = None,
                             actor: str | None = None, base: Path | None = None) -> list[Path]:
    """Writes XLSX, CSV and JSON into the same export folder."""
    folder, stem = export_folder(name, base)
    paths = [
        export_excel(df, folder, stem, meta={"العملية": name}),
        export_csv(df, folder, stem),
        export_json(df, folder, stem, meta={"name": name, "job_id": job_id, "filters": filters or {}}),
    ]
    for p in paths:
        register_export(p, p.suffix.lstrip("."), len(df), job_id=job_id, filters=filters, actor=actor)
    return paths


def export_report(rep: dict, fmt: str, name: str, job_id: int | None = None, actor: str | None = None,
                  base: Path | None = None) -> Path:
    fmt = fmt.lower()
    if fmt not in REPORT_FORMATS:
        raise ValueError(f"صيغة تقرير غير مدعومة: {fmt}")
    folder, stem = export_folder(f"report_{name}", base)
    path = export_report_excel(rep, folder, stem) if fmt == "xlsx" else export_report_pdf(rep, folder, stem)
    register_export(path, fmt, rep.get("n_posts", 0), job_id=job_id, filters=rep.get("scope"),
                    export_type="report", actor=actor)
    return path
