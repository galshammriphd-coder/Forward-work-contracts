"""Data processing pipeline.

Steps (each one is written to ``processing_logs``):
 1. validate        – structural checks (id, author, date, content)
 2. deduplicate     – flag posts whose normalised text repeats an earlier post
 3. clean_text      – decode entities, remove invisible chars / tatweel / t.co links
 4. whitespace      – collapse spaces and symbol runs (part of clean_text, logged separately)
 5. hashtags        – merge X entities with regex extraction; rebuild hashtag tables
 6. mentions        – merge X entities with regex extraction
 7. language        – X language code or offline script-based detection
 8. datetime        – normalise to ISO UTC + local date/time (settings timezone)
 9. urls            – keep only syntactically valid http(s) URLs
10. missing_values  – fill display fallbacks, note fields X did not expose
11. document        – summary row

The original record (raw_text, raw_json, the X ``language`` code and every row of
post_sources) is never modified; outputs go to clean_text, detected_language,
validation_notes and the normalised list/date columns.
"""
from __future__ import annotations

import json
import uuid
from collections import Counter

from database import db
from database.models import refresh_processed_count
from processing import cleaning
from processing.deduplication import find_content_duplicates
from processing.language_detection import detect_language


def _log(run_id: str, job_id: int | None, step: str, n_in: int, n_aff: int, msg: str) -> None:
    db.execute(
        "INSERT INTO processing_logs(run_id, job_id, step, ts, records_in, records_affected, message)"
        " VALUES (?,?,?,?,?,?,?)",
        (run_id, job_id, step, db.utcnow(), n_in, n_aff, msg),
    )


def rebuild_hashtag_tables() -> int:
    """Recompute hashtags / post_hashtags from the processed hashtag lists of all posts."""
    rows = db.fetch_all("SELECT post_id, hashtags_json, published_at FROM posts WHERE is_valid = 1")
    stats: dict[str, dict] = {}
    links: list[tuple[str, str]] = []
    for r in rows:
        try:
            tags = json.loads(r["hashtags_json"] or "[]")
        except json.JSONDecodeError:
            tags = []
        seen = set()
        for t in tags:
            norm = cleaning.normalize_hashtag(str(t))
            if not norm:
                continue
            s = stats.setdefault(norm, {"display": Counter(), "occ": 0, "posts": 0, "first": None, "last": None})
            s["display"][str(t).lstrip("#")] += 1
            s["occ"] += 1
            if norm in seen:
                continue
            seen.add(norm)
            s["posts"] += 1
            d = r["published_at"]
            if d:
                s["first"] = d if not s["first"] or d < s["first"] else s["first"]
                s["last"] = d if not s["last"] or d > s["last"] else s["last"]
            links.append((r["post_id"], norm))
    now = db.utcnow()
    with db.get_conn() as c:
        c.execute("DELETE FROM post_hashtags")
        c.execute("DELETE FROM hashtags")
        for norm, s in stats.items():
            c.execute(
                "INSERT INTO hashtags(tag, display_tag, occurrences, post_count, first_seen, last_seen, updated_at)"
                " VALUES (?,?,?,?,?,?,?)",
                (norm, s["display"].most_common(1)[0][0], s["occ"], s["posts"], s["first"], s["last"], now),
            )
        ids = {r[0]: r[1] for r in c.execute("SELECT tag, id FROM hashtags").fetchall()}
        c.executemany(
            "INSERT OR IGNORE INTO post_hashtags(post_id, hashtag_id) VALUES (?,?)",
            [(pid, ids[t]) for pid, t in links if t in ids],
        )
    return len(stats)


def run_pipeline(job_id: int | None = None, reprocess: bool = False, tz_name: str | None = None) -> dict:
    run_id = uuid.uuid4().hex[:12]
    tz_name = tz_name or db.get_setting("timezone", "Asia/Riyadh")
    where, params = [], []
    if job_id is not None:
        where.append("post_id IN (SELECT post_id FROM job_posts WHERE job_id = ?)")
        params.append(job_id)
    if not reprocess:
        where.append("is_processed = 0")
    sql = "SELECT * FROM posts" + (" WHERE " + " AND ".join(where) if where else "")
    rows = db.fetch_all(sql, params)
    n = len(rows)
    summary: dict = {"run_id": run_id, "records": n}
    if n == 0:
        _log(run_id, job_id, "document", 0, 0, "لا توجد سجلات جديدة للمعالجة")
        return summary

    # 1. validation ---------------------------------------------------------
    notes: dict[str, list[str]] = {r["post_id"]: [] for r in rows}
    invalid = set()
    for r in rows:
        if not str(r["post_id"]).isdigit():
            notes[r["post_id"]].append("invalid_id")
            invalid.add(r["post_id"])
        if not r["username"]:
            notes[r["post_id"]].append("missing_author")
        if not (r["raw_text"] or "").strip() and r["media_json"] in (None, "[]"):
            notes[r["post_id"]].append("empty_content")
            invalid.add(r["post_id"])
        if r["published_at"] and not cleaning.parse_x_datetime(r["published_at"]):
            notes[r["post_id"]].append("bad_date")
    _log(run_id, job_id, "validate", n, len(invalid), f"سجلات غير صالحة: {len(invalid)}")

    # 2. content duplicates (checked against the whole database) ---------------
    universe = db.fetch_all("SELECT post_id, raw_text, published_at FROM posts")
    dups = find_content_duplicates(universe)
    batch_ids = set(notes)
    n_dup = 0
    for pid, original in dups.items():
        if pid in batch_ids:
            notes[pid].append(f"duplicate_text_of:{original}")
            n_dup += 1
    _log(run_id, job_id, "deduplicate", n, n_dup, f"منشورات بنص مكرر (تم وسمها دون حذف): {n_dup}")

    updates: dict[str, dict] = {}
    changed_clean = changed_space = 0
    hashtag_added = mention_added = 0
    lang_counter: Counter = Counter()
    date_fixed = url_dropped = 0
    missing_counter: Counter = Counter()

    for r in rows:
        pid = r["post_id"]
        raw = r["raw_text"] or ""
        # 3-4. cleaning
        cleaned = cleaning.clean_text(raw)
        if cleaned != raw.strip():
            changed_clean += 1
        if "  " in raw or "ـ" in raw or "‏" in raw:
            changed_space += 1
        # 5. hashtags (X entities ∪ regex)
        tags = json.loads(r["hashtags_json"] or "[]")
        merged = list(dict.fromkeys([*map(str, tags), *cleaning.extract_hashtags(raw)]))
        uniq, seen = [], set()
        for t in merged:
            k = cleaning.normalize_hashtag(t)
            if k and k not in seen:
                seen.add(k)
                uniq.append(t.lstrip("#"))
        hashtag_added += max(0, len(uniq) - len(tags))
        # 6. mentions
        ments = json.loads(r["mentions_json"] or "[]")
        mmerged, mseen = [], set()
        for m in [*map(str, ments), *cleaning.extract_mentions(raw)]:
            if m.lower() not in mseen:
                mseen.add(m.lower())
                mmerged.append(m.lstrip("@"))
        mention_added += max(0, len(mmerged) - len(ments))
        # 7. language
        lang = detect_language(raw, r["language"])
        lang_counter[lang] += 1
        # 8. datetime
        iso = cleaning.parse_x_datetime(r["published_at"]) if r["published_at"] else None
        pdate, ptime = cleaning.local_date_time(iso, tz_name)
        if iso and (iso != r["published_at"] or pdate != r["published_date"]):
            date_fixed += 1
        # 9. urls
        urls = json.loads(r["urls_json"] or "[]")
        good_urls = [u for u in urls if cleaning.is_valid_url(u)]
        url_dropped += len(urls) - len(good_urls)
        # 10. missing values
        for col in ("published_at", "likes_count", "reposts_count", "replies_count", "views_count", "display_name"):
            if r[col] in (None, ""):
                missing_counter[col] += 1
        if r["views_count"] is None:
            notes[pid].append("views_not_available")
        if not r["published_at"]:
            notes[pid].append("date_not_available")
        updates[pid] = {
            "clean_text": cleaned,
            "hashtags_json": json.dumps(uniq, ensure_ascii=False),
            "mentions_json": json.dumps(mmerged, ensure_ascii=False),
            "detected_language": lang,
            "published_at": iso or r["published_at"],
            "published_date": pdate or r["published_date"],
            "published_time": ptime or r["published_time"],
            "urls_json": json.dumps(good_urls, ensure_ascii=False),
            "display_name": r["display_name"] or r["username"],
            "is_valid": 0 if pid in invalid else 1,
            "validation_notes": ";".join(dict.fromkeys(notes[pid])) or None,
        }

    _log(run_id, job_id, "clean_text", n, changed_clean, "تنظيف النصوص: فك ترميز HTML وإزالة المحارف الخفية والتطويل وروابط t.co")
    _log(run_id, job_id, "whitespace", n, changed_space, "توحيد المسافات ومعالجة الرموز المتكررة")
    _log(run_id, job_id, "hashtags", n, hashtag_added, f"وسوم إضافية مستخرجة من النص: {hashtag_added}")
    _log(run_id, job_id, "mentions", n, mention_added, f"إشارات إضافية مستخرجة من النص: {mention_added}")
    _log(run_id, job_id, "language", n, n, "توزيع اللغات: " + ", ".join(f"{k}={v}" for k, v in lang_counter.most_common()))
    _log(run_id, job_id, "datetime", n, date_fixed, f"توحيد التاريخ إلى UTC والمنطقة الزمنية {tz_name}")
    _log(run_id, job_id, "urls", n, url_dropped, f"روابط غير صالحة مستبعدة: {url_dropped}")
    _log(run_id, job_id, "missing_values", n, sum(missing_counter.values()),
         "قيم غير متاحة: " + (", ".join(f"{k}={v}" for k, v in missing_counter.items()) or "لا يوجد"))

    now = db.utcnow()
    cols = list(next(iter(updates.values())).keys())
    with db.get_conn() as c:
        c.executemany(
            f"UPDATE posts SET {', '.join(f'{k} = ?' for k in cols)}, is_processed = 1, processed_at = ? WHERE post_id = ?",
            [(*[u[k] for k in cols], now, pid) for pid, u in updates.items()],
        )
    n_tags = rebuild_hashtag_tables()
    if job_id is not None:
        refresh_processed_count(job_id)
    else:
        for j in db.fetch_all("SELECT id FROM search_jobs"):
            refresh_processed_count(j["id"])
    _log(run_id, job_id, "document", n, n,
         f"اكتملت المعالجة: {n} سجل، {len(invalid)} غير صالح، {n_dup} نص مكرر، {n_tags} هاشتاق في القاعدة")
    summary.update({
        "invalid": len(invalid), "content_duplicates": n_dup, "languages": dict(lang_counter),
        "hashtags_total": n_tags, "urls_dropped": url_dropped,
    })
    db.audit("process_data", f"job:{job_id}" if job_id else "all", summary)
    return summary
