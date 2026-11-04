"""Shared export helpers: unified columns, export folders and the exports registry."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

import config
from database import db

# Unified post model (section 7 of the specification) + optional fields.
POST_EXPORT_COLUMNS = {
    "post_id": "Post ID",
    "raw_text": "Post Text",
    "clean_text": "Clean Text",
    "username": "Username",
    "display_name": "Display Name",
    "profile_url": "Profile URL",
    "post_url": "Post URL",
    "published_date": "Published Date",
    "published_time": "Published Time",
    "published_at": "Published At (UTC)",
    "lang": "Language",
    "post_type": "Post Type",
    "hashtags_json": "Hashtags",
    "mentions_json": "Mentions",
    "replies_count": "Replies Count",
    "reposts_count": "Reposts Count",
    "likes_count": "Likes Count",
    "quotes_count": "Quotes Count",
    "views_count": "Views Count",
    "search_keyword": "Search Keyword",
    "first_collected_at": "Collection Date",
    "source": "Source",
    "urls_json": "External Links",
    "media_json": "Attachments",
    "validation_notes": "Processing Notes",
}


def slugify(name: str, max_len: int = 60) -> str:
    s = re.sub(r"[\\/:*?\"<>|#@\s]+", "_", name.strip())
    s = re.sub(r"_+", "_", s).strip("._")
    return (s or "export")[:max_len]


def export_folder(name: str, base: Path | None = None) -> tuple[Path, str]:
    """A dedicated folder per export: exports_data/<name>_<YYYYmmdd_HHMMSS>/"""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = f"{slugify(name)}_{stamp}"
    folder = Path(base or config.EXPORT_DIR) / stem
    n = 1
    while folder.exists():
        folder = Path(base or config.EXPORT_DIR) / f"{stem}_{n}"
        n += 1
    folder.mkdir(parents=True, exist_ok=True)
    return folder, folder.name


def posts_for_export(df: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in POST_EXPORT_COLUMNS if c in df.columns]
    out = df[cols].copy()
    for c in ("hashtags_json", "mentions_json", "urls_json"):
        if c in out:
            out[c] = out[c].apply(lambda s: ", ".join(json.loads(s)) if s else "")
    if "media_json" in out:
        out["media_json"] = out["media_json"].apply(
            lambda s: ", ".join(m.get("video_url") or m.get("url") or m.get("type", "") for m in json.loads(s)) if s else "")
    return out.rename(columns=POST_EXPORT_COLUMNS)


def register_export(path: Path, fmt: str, count: int, job_id: int | None = None, filters: dict | None = None,
                    export_type: str = "data", actor: str | None = None) -> int:
    eid = db.execute(
        "INSERT INTO exports(job_id, export_type, format, path, record_count, filters_json, created_by, created_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (job_id, export_type, fmt, str(path), count, json.dumps(filters or {}, ensure_ascii=False, default=str),
         actor, db.utcnow()),
    )
    db.audit("export_created", str(path), {"format": fmt, "records": count, "type": export_type}, actor=actor)
    return eid
