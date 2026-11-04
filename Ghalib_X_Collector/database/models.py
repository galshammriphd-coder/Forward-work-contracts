"""Data models and repository functions (jobs, posts, accounts, logs)."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from database import db

JOB_STATUSES = ("new", "running", "completed", "stopped", "failed")
STATUS_LABELS_AR = {
    "new": "جديدة",
    "running": "قيد التنفيذ",
    "completed": "مكتملة",
    "stopped": "متوقفة",
    "failed": "فاشلة",
}
SEARCH_TYPE_LABELS_AR = {
    "hashtag": "هاشتاق",
    "user": "اسم مستخدم",
    "keyword": "كلمات مفتاحية",
    "advanced": "بحث متقدم",
    "import": "استيراد ملف",
}


@dataclass
class Post:
    """Unified post record. Count fields are None when X did not expose them."""

    post_id: str
    raw_text: str = ""
    username: str | None = None
    display_name: str | None = None
    profile_url: str | None = None
    post_url: str | None = None
    published_at: str | None = None      # ISO UTC
    language: str | None = None
    post_type: str = "original"
    hashtags: list[str] = field(default_factory=list)
    mentions: list[str] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)
    media: list[dict] = field(default_factory=list)
    replies_count: int | None = None
    reposts_count: int | None = None
    likes_count: int | None = None
    quotes_count: int | None = None
    bookmarks_count: int | None = None
    views_count: int | None = None
    conversation_id: str | None = None
    in_reply_to_post_id: str | None = None
    in_reply_to_user: str | None = None
    quoted_post_id: str | None = None
    source: str = "graphql"
    raw: dict | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Account:
    username: str                         # screen name (any casing)
    user_id: str | None = None
    display_name: str | None = None
    description: str | None = None
    location: str | None = None
    followers_count: int | None = None
    following_count: int | None = None
    statuses_count: int | None = None
    account_created_at: str | None = None
    verified: bool | None = None
    profile_image_url: str | None = None
    raw: dict | None = None
    is_profile: bool = False              # True when data came from the profile endpoint


def _j(value: Any) -> str:
    return json.dumps(value if value is not None else [], ensure_ascii=False, default=str)


# ------------------------------------------------------------------ jobs
def create_job(
    name: str,
    search_type: str,
    query_text: str,
    queries: list[str],
    params: dict,
    start_date: str | None = None,
    end_date: str | None = None,
    sort_mode: str = "live",
    max_posts: int = 300,
    parent_job_id: int | None = None,
    created_by: str | None = None,
    status: str = "new",
) -> int:
    if not name.strip():
        raise ValueError("اسم العملية مطلوب")
    if not queries:
        raise ValueError("لا توجد عبارة بحث صالحة")
    return db.execute(
        "INSERT INTO search_jobs(name, search_type, query_text, queries_json, params_json, start_date, end_date,"
        " sort_mode, max_posts, status, parent_job_id, created_by, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            name.strip(), search_type, query_text, _j(queries), json.dumps(params, ensure_ascii=False, default=str),
            start_date, end_date, sort_mode, int(max_posts), status, parent_job_id, created_by, db.utcnow(),
        ),
    )


def get_job(job_id: int) -> dict | None:
    job = db.fetch_one("SELECT * FROM search_jobs WHERE id = ?", (job_id,))
    if job:
        job["queries"] = json.loads(job.get("queries_json") or "[]")
        job["params"] = json.loads(job.get("params_json") or "{}")
        job["progress"] = json.loads(job.get("progress_json") or "{}")
    return job


def list_jobs(limit: int = 500) -> list[dict]:
    return db.fetch_all("SELECT * FROM search_jobs ORDER BY id DESC LIMIT ?", (limit,))


def update_job(job_id: int, **fields: Any) -> None:
    if not fields:
        return
    for k in ("progress", "params", "queries"):
        if k in fields:
            fields[f"{k}_json"] = json.dumps(fields.pop(k), ensure_ascii=False, default=str)
    if "status" in fields and fields["status"] not in JOB_STATUSES:
        raise ValueError(f"invalid status {fields['status']}")
    cols = ", ".join(f"{k} = ?" for k in fields)
    db.execute(f"UPDATE search_jobs SET {cols} WHERE id = ?", (*fields.values(), job_id))


def increment_job(job_id: int, received: int = 0, new: int = 0, duplicate: int = 0, errors: int = 0) -> None:
    db.execute(
        "UPDATE search_jobs SET received_count = received_count + ?, new_count = new_count + ?,"
        " duplicate_count = duplicate_count + ?, error_count = error_count + ? WHERE id = ?",
        (received, new, duplicate, errors, job_id),
    )


def refresh_processed_count(job_id: int) -> int:
    n = int(db.fetch_value(
        "SELECT COUNT(*) FROM job_posts jp JOIN posts p ON p.post_id = jp.post_id"
        " WHERE jp.job_id = ? AND p.is_processed = 1", (job_id,), default=0))
    update_job(job_id, processed_count=n)
    return n


def log_collection(job_id: int | None, level: str, event: str, message: str = "", details: Any = None) -> None:
    if details is not None and not isinstance(details, str):
        details = json.dumps(details, ensure_ascii=False, default=str)
    db.execute(
        "INSERT INTO collection_logs(job_id, ts, level, event, message, details) VALUES (?,?,?,?,?,?)",
        (job_id, db.utcnow(), level, event, message, details),
    )


# ---------------------------------------------------------------- accounts
def upsert_account(acc: Account, conn=None) -> None:
    if not acc.username:
        return
    key = acc.username.lower().lstrip("@")
    now = db.utcnow()
    values = {
        "user_id": acc.user_id,
        "screen_name": acc.username.lstrip("@"),
        "display_name": acc.display_name,
        "profile_url": f"https://x.com/{acc.username.lstrip('@')}",
        "description": acc.description,
        "location": acc.location,
        "followers_count": acc.followers_count,
        "following_count": acc.following_count,
        "statuses_count": acc.statuses_count,
        "account_created_at": acc.account_created_at,
        "verified": None if acc.verified is None else int(bool(acc.verified)),
        "profile_image_url": acc.profile_image_url,
        "raw_json": json.dumps(acc.raw, ensure_ascii=False, default=str) if acc.raw is not None else None,
    }

    def _run(c):
        exists = c.execute("SELECT 1 FROM accounts WHERE username = ?", (key,)).fetchone()
        if not exists:
            cols = ["username", *values.keys(), "first_seen_at", "last_updated_at"]
            c.execute(
                f"INSERT INTO accounts({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                (key, *values.values(), now, now),
            )
        else:
            # Never erase known values with missing ones (DOM captures carry less data).
            sets = ", ".join(f"{k} = COALESCE(?, {k})" for k in values)
            c.execute(
                f"UPDATE accounts SET {sets}, last_updated_at = ? WHERE username = ?",
                (*values.values(), now, key),
            )

    if conn is not None:
        _run(conn)
    else:
        with db.get_conn() as c:
            _run(c)


# ------------------------------------------------------------------ posts
_POST_COLUMNS = (
    "raw_text", "username", "display_name", "profile_url", "post_url", "published_at", "published_date",
    "published_time", "language", "post_type", "hashtags_json", "mentions_json", "urls_json", "media_json",
    "replies_count", "reposts_count", "likes_count", "quotes_count", "bookmarks_count", "views_count",
    "conversation_id", "in_reply_to_post_id", "in_reply_to_user", "quoted_post_id", "raw_json",
)
_METRICS = ("replies_count", "reposts_count", "likes_count", "quotes_count", "bookmarks_count", "views_count")


def save_post(
    post: Post,
    job_id: int | None,
    query: str | None,
    tz_name: str = "UTC",
    source_url: str | None = None,
    conn=None,
) -> bool:
    """Insert or refresh a post. Returns True when the post is new to the database.

    Duplicates are detected by the X post id. A duplicate still records the job
    link, a provenance row and a metrics snapshot, and fills in values that were
    missing in the earlier capture, but it never overwrites the stored raw text.
    """
    from processing.cleaning import local_date_time  # local import avoids a cycle

    if not post.post_id or not str(post.post_id).isdigit():
        raise ValueError(f"invalid post id: {post.post_id!r}")
    now = db.utcnow()
    username = post.username.lower().lstrip("@") if post.username else None
    pdate, ptime = local_date_time(post.published_at, tz_name)
    row = {
        "raw_text": post.raw_text,
        "username": username,
        "display_name": post.display_name,
        "profile_url": post.profile_url or (f"https://x.com/{post.username.lstrip('@')}" if post.username else None),
        "post_url": post.post_url or (f"https://x.com/{post.username.lstrip('@')}/status/{post.post_id}" if post.username else f"https://x.com/i/status/{post.post_id}"),
        "published_at": post.published_at,
        "published_date": pdate,
        "published_time": ptime,
        "language": post.language,
        "post_type": post.post_type,
        "hashtags_json": _j(post.hashtags),
        "mentions_json": _j(post.mentions),
        "urls_json": _j(post.urls),
        "media_json": _j(post.media),
        "replies_count": post.replies_count,
        "reposts_count": post.reposts_count,
        "likes_count": post.likes_count,
        "quotes_count": post.quotes_count,
        "bookmarks_count": post.bookmarks_count,
        "views_count": post.views_count,
        "conversation_id": post.conversation_id,
        "in_reply_to_post_id": post.in_reply_to_post_id,
        "in_reply_to_user": post.in_reply_to_user,
        "quoted_post_id": post.quoted_post_id,
        "raw_json": json.dumps(post.raw, ensure_ascii=False, default=str) if post.raw is not None else None,
    }
    raw_json = row["raw_json"]

    def _run(c) -> bool:
        if username:
            if not c.execute("SELECT 1 FROM accounts WHERE username = ?", (username,)).fetchone():
                c.execute(
                    "INSERT INTO accounts(username, screen_name, display_name, profile_url, first_seen_at, last_updated_at)"
                    " VALUES (?,?,?,?,?,?)",
                    (username, post.username.lstrip("@"), post.display_name, row["profile_url"], now, now),
                )
        existing = c.execute("SELECT post_id FROM posts WHERE post_id = ?", (post.post_id,)).fetchone()
        is_new = existing is None
        if is_new:
            cols = ["post_id", *_POST_COLUMNS, "search_keyword", "first_job_id", "source",
                    "first_collected_at", "last_collected_at"]
            c.execute(
                f"INSERT INTO posts({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                (post.post_id, *[row[k] for k in _POST_COLUMNS], query, job_id, post.source, now, now),
            )
        else:
            # Metrics are refreshed with the newest capture; descriptive fields only fill gaps.
            fill = [k for k in _POST_COLUMNS if k not in _METRICS and k not in ("raw_text", "hashtags_json",
                    "mentions_json", "urls_json", "media_json", "raw_json")]
            sets = [f"{k} = COALESCE({k}, ?)" for k in fill]
            sets += [f"{k} = COALESCE(?, {k})" for k in _METRICS]
            vals = [row[k] for k in fill] + [row[k] for k in _METRICS]
            # A GraphQL capture is richer than a DOM capture: upgrade the stored raw record.
            if post.source == "graphql":
                sets += ["raw_json = COALESCE(?, raw_json)", "source = 'graphql'",
                         "raw_text = CASE WHEN source = 'dom' THEN ? ELSE raw_text END",
                         "hashtags_json = CASE WHEN source = 'dom' THEN ? ELSE hashtags_json END",
                         "mentions_json = CASE WHEN source = 'dom' THEN ? ELSE mentions_json END",
                         "urls_json = CASE WHEN source = 'dom' THEN ? ELSE urls_json END",
                         "media_json = CASE WHEN source = 'dom' THEN ? ELSE media_json END",
                         "is_processed = CASE WHEN source = 'dom' THEN 0 ELSE is_processed END"]
                vals += [raw_json, row["raw_text"], row["hashtags_json"], row["mentions_json"],
                         row["urls_json"], row["media_json"]]
            sets.append("last_collected_at = ?")
            vals.append(now)
            c.execute(f"UPDATE posts SET {', '.join(sets)} WHERE post_id = ?", (*vals, post.post_id))
        if job_id is not None:
            c.execute(
                "INSERT OR IGNORE INTO job_posts(job_id, post_id, query, is_new, collected_at) VALUES (?,?,?,?,?)",
                (job_id, post.post_id, query, int(is_new), now),
            )
        c.execute(
            "INSERT INTO post_sources(post_id, job_id, source, source_url, captured_at, raw_json) VALUES (?,?,?,?,?,?)",
            (post.post_id, job_id, post.source, source_url, now, raw_json),
        )
        if any(row[m] is not None for m in _METRICS):
            c.execute(
                "INSERT INTO post_metrics(post_id, job_id, captured_at, replies_count, reposts_count, likes_count,"
                " quotes_count, bookmarks_count, views_count) VALUES (?,?,?,?,?,?,?,?,?)",
                (post.post_id, job_id, now, *[row[m] for m in _METRICS]),
            )
        return is_new

    if conn is not None:
        return _run(conn)
    with db.get_conn() as c:
        return _run(c)


def job_post_count(job_id: int) -> int:
    return int(db.fetch_value("SELECT COUNT(*) FROM job_posts WHERE job_id = ?", (job_id,), default=0))


# --------------------------------------------------------- saved searches
def save_search(name: str, search_type: str, params: dict) -> None:
    db.execute(
        "INSERT INTO saved_searches(name, search_type, params_json, created_at) VALUES (?,?,?,?) "
        "ON CONFLICT(name) DO UPDATE SET search_type = excluded.search_type, params_json = excluded.params_json",
        (name.strip(), search_type, json.dumps(params, ensure_ascii=False, default=str), db.utcnow()),
    )


def list_saved_searches() -> list[dict]:
    rows = db.fetch_all("SELECT * FROM saved_searches ORDER BY name")
    for r in rows:
        r["params"] = json.loads(r["params_json"])
    return rows


def delete_saved_search(search_id: int) -> None:
    db.execute("DELETE FROM saved_searches WHERE id = ?", (search_id,))
