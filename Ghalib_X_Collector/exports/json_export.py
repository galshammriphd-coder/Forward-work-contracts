from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import config
from database import db


def _records(df: pd.DataFrame) -> list[dict]:
    out = []
    for r in df.to_dict(orient="records"):
        rec = {}
        for k, v in r.items():
            if k in ("published_dt", "_t", "_a", "author_followers"):
                continue
            if k.endswith("_json"):
                try:
                    rec[k[:-5]] = json.loads(v) if v else []
                except (TypeError, json.JSONDecodeError):
                    rec[k[:-5]] = []
                continue
            if k in ("hashtags", "mentions"):
                continue
            if isinstance(v, float) and pd.isna(v):
                v = None
            elif hasattr(v, "isoformat"):
                v = v.isoformat()
            rec[k] = v
        out.append(rec)
    return out


def export_json(df: pd.DataFrame, folder: Path, stem: str, meta: dict | None = None,
                include_raw: bool = False) -> Path:
    data = df if include_raw else df.drop(columns=[c for c in ("raw_json",) if c in df.columns])
    payload = {
        "application": config.APP_NAME,
        "version": config.APP_VERSION,
        "exported_at": db.utcnow(),
        "meta": meta or {},
        "count": len(data),
        "posts": _records(data),
    }
    path = Path(folder) / f"{stem}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path
