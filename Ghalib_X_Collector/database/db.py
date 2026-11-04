"""SQLite access layer: connections, schema creation, settings, audit, backup."""
from __future__ import annotations

import json
import shutil
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

import pandas as pd

import config

_init_lock = threading.Lock()
_initialized: set[str] = set()


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def db_path() -> Path:
    # Read at call time so tests can point GHALIB_DB_PATH / config.DB_PATH elsewhere.
    return Path(config.DB_PATH)


def _connect(path: Path | None = None) -> sqlite3.Connection:
    path = Path(path or db_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


@contextmanager
def get_conn(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    """Open a short-lived connection; commit on success, roll back on error.

    One connection per unit of work keeps the Streamlit threads and the
    browser/collection thread independent (SQLite WAL handles concurrency).
    """
    init_db(path)
    conn = _connect(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(path: Path | None = None) -> None:
    path = Path(path or db_path())
    key = str(path.resolve())
    if key in _initialized and path.exists():
        return
    with _init_lock:
        if key in _initialized and path.exists():
            return
        conn = _connect(path)
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(config.SCHEMA_PATH.read_text(encoding="utf-8"))
            now = utcnow()
            for k, v in config.DEFAULTS.items():
                conn.execute(
                    "INSERT OR IGNORE INTO application_settings(key, value, updated_at) VALUES (?,?,?)",
                    (k, v, now),
                )
            conn.commit()
        finally:
            conn.close()
        _initialized.add(key)


def reset_init_cache() -> None:
    _initialized.clear()


# ---------------------------------------------------------------- queries
def execute(sql: str, params: Iterable[Any] = ()) -> int:
    with get_conn() as conn:
        cur = conn.execute(sql, tuple(params))
        return cur.lastrowid if cur.lastrowid else cur.rowcount


def fetch_all(sql: str, params: Iterable[Any] = ()) -> list[dict]:
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql, tuple(params)).fetchall()]


def fetch_one(sql: str, params: Iterable[Any] = ()) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(sql, tuple(params)).fetchone()
        return dict(row) if row else None


def fetch_value(sql: str, params: Iterable[Any] = (), default: Any = None) -> Any:
    with get_conn() as conn:
        row = conn.execute(sql, tuple(params)).fetchone()
        return row[0] if row and row[0] is not None else default


def read_df(sql: str, params: Iterable[Any] = ()) -> pd.DataFrame:
    with get_conn() as conn:
        return pd.read_sql_query(sql, conn, params=tuple(params))


def table_counts() -> dict[str, int]:
    tables = [r["name"] for r in fetch_all("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    return {t: int(fetch_value(f"SELECT COUNT(*) FROM {t}", default=0)) for t in sorted(tables)}


# --------------------------------------------------------------- settings
def get_setting(key: str, default: str | None = None) -> str | None:
    row = fetch_one("SELECT value FROM application_settings WHERE key = ?", (key,))
    if row is None or row["value"] is None:
        return config.DEFAULTS.get(key, default) if default is None else default
    return row["value"]


def get_setting_float(key: str, default: float) -> float:
    try:
        return float(get_setting(key, str(default)))
    except (TypeError, ValueError):
        return default


def get_setting_int(key: str, default: int) -> int:
    try:
        return int(float(get_setting(key, str(default))))
    except (TypeError, ValueError):
        return default


def get_setting_bool(key: str, default: bool = False) -> bool:
    return str(get_setting(key, "true" if default else "false")).lower() in ("1", "true", "yes", "on")


def set_setting(key: str, value: Any) -> None:
    if isinstance(value, bool):
        value = "true" if value else "false"
    elif isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    execute(
        "INSERT INTO application_settings(key, value, updated_at) VALUES (?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
        (key, None if value is None else str(value), utcnow()),
    )


# ------------------------------------------------------------------ audit
def audit(action: str, target: str | None = None, details: Any = None, actor: str | None = None) -> None:
    if details is not None and not isinstance(details, str):
        details = json.dumps(details, ensure_ascii=False, default=str)
    execute(
        "INSERT INTO audit_log(ts, actor, action, target, details) VALUES (?,?,?,?,?)",
        (utcnow(), actor or "local", action, target, details),
    )


# ------------------------------------------------------ backup / restore
def backup_database(dest_dir: Path | None = None, label: str = "") -> Path:
    """Consistent online backup using SQLite's backup API (safe while running)."""
    dest_dir = Path(dest_dir or config.BACKUP_DIR)
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = f"_{label}" if label else ""
    dest = dest_dir / f"ghalib_x_backup_{stamp}{suffix}.db"
    n = 1
    while dest.exists():
        dest = dest_dir / f"ghalib_x_backup_{stamp}{suffix}_{n}.db"
        n += 1
    init_db()
    src = _connect()
    dst = sqlite3.connect(str(dest))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return dest


def list_backups(dest_dir: Path | None = None) -> list[Path]:
    dest_dir = Path(dest_dir or config.BACKUP_DIR)
    if not dest_dir.exists():
        return []
    return sorted(dest_dir.glob("ghalib_x_backup_*.db"), reverse=True)


def verify_database_file(path: Path) -> bool:
    try:
        conn = sqlite3.connect(str(path))
        try:
            ok = conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            has_posts = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='posts'"
            ).fetchone()[0] == 1
            return ok and has_posts
        finally:
            conn.close()
    except sqlite3.DatabaseError:
        return False


def restore_database(backup_file: Path) -> Path:
    """Replace the live database with a backup. A safety backup is taken first."""
    backup_file = Path(backup_file)
    if not verify_database_file(backup_file):
        raise ValueError(f"Backup file is not a valid Ghalib database: {backup_file}")
    safety = backup_database(label="before_restore") if db_path().exists() else None
    src = sqlite3.connect(str(backup_file))
    dst = _connect()
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    reset_init_cache()
    init_db()  # applies any schema additions to older backups
    return safety or backup_file


# ------------------------------------------------------------ deletion
def delete_job_data(job_id: int) -> dict[str, int]:
    """Delete a job and the posts that were found ONLY by that job."""
    with get_conn() as conn:
        orphan_ids = [
            r[0]
            for r in conn.execute(
                "SELECT jp.post_id FROM job_posts jp WHERE jp.job_id = ? AND NOT EXISTS ("
                " SELECT 1 FROM job_posts o WHERE o.post_id = jp.post_id AND o.job_id <> ?)",
                (job_id, job_id),
            ).fetchall()
        ]
        for i in range(0, len(orphan_ids), 500):
            chunk = orphan_ids[i : i + 500]
            conn.execute(f"DELETE FROM posts WHERE post_id IN ({','.join('?' * len(chunk))})", chunk)
        conn.execute("DELETE FROM search_jobs WHERE id = ?", (job_id,))
    return {"posts_deleted": len(orphan_ids)}


def delete_all_data() -> None:
    with get_conn() as conn:
        for t in (
            "entity_results", "topic_results", "sentiment_results", "post_metrics", "post_hashtags",
            "post_sources", "job_posts", "posts", "hashtags", "accounts", "collection_logs",
            "processing_logs", "exports", "search_jobs",
        ):
            conn.execute(f"DELETE FROM {t}")
    with get_conn() as conn:
        conn.execute("VACUUM")


def copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
