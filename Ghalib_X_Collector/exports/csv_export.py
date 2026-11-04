from __future__ import annotations

from pathlib import Path

import pandas as pd

from exports.common import posts_for_export


def export_csv(df: pd.DataFrame, folder: Path, stem: str) -> Path:
    """UTF-8 with BOM so Excel on Windows shows Arabic correctly."""
    path = Path(folder) / f"{stem}.csv"
    posts_for_export(df).to_csv(path, index=False, encoding="utf-8-sig")
    return path


def export_table_csv(df: pd.DataFrame, folder: Path, stem: str) -> Path:
    path = Path(folder) / f"{stem}.csv"
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path
