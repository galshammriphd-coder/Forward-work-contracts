"""Central manager for collection jobs.

A job is a list of X search queries. Each query is opened in the logged-in
browser page and the result list is scrolled like a person would do, at a
configurable, randomised pace. While the page loads results, the posts are read
from two places:

1. the GraphQL JSON responses the X web client itself receives (complete data:
   exact counters, language, entities, author profile);
2. the rendered page (DOM) as a fallback for anything not seen in (1).

Each job runs on the browser worker thread; Streamlit only reads the job
state from SQLite, so the UI stays responsive and survives page reloads.
"""
from __future__ import annotations

import json
import logging
import random
import threading
import time
from concurrent.futures import Future
from datetime import datetime, timedelta

from browser.browser_manager import BrowserError, BrowserManager, get_browser_manager
from browser.dom_extractor import CLICK_RETRY_JS, EXTRACT_JS
from browser import session_manager as sm
from collectors.data_normalizer import normalize_account, normalize_post
from collectors.result_importer import parse_file, parse_graphql_payload, post_from_dom
from database import db
from database import models
from processing.deduplication import dedupe_batch
from search.query_builder import SearchParams, build_queries, describe, search_url

log = logging.getLogger("ghalib.collector")

_stop_flags: dict[int, threading.Event] = {}
_futures: dict[int, Future] = {}


class SessionExpired(BrowserError):
    pass


# ------------------------------------------------------------ job creation
def create_job_from_params(name: str, params: SearchParams, max_posts: int | None = None,
                           parent_job_id: int | None = None, created_by: str | None = None) -> int:
    queries = build_queries(params)
    job_id = models.create_job(
        name=name,
        search_type=params.search_type,
        query_text=describe(params) or queries[0],
        queries=queries,
        params=params.to_dict(),
        start_date=params.since,
        end_date=params.until,
        sort_mode=params.sort,
        max_posts=max_posts or db.get_setting_int("max_posts_per_query", 300),
        parent_job_id=parent_job_id,
        created_by=created_by,
    )
    models.log_collection(job_id, "INFO", "job_created", f"تم إنشاء العملية ({len(queries)} استعلام)",
                          {"queries": queries})
    db.audit("job_created", f"job:{job_id}", {"name": name, "queries": queries}, actor=created_by)
    return job_id


def rerun_job(job_id: int, created_by: str | None = None) -> int:
    job = models.get_job(job_id)
    if not job:
        raise ValueError("العملية غير موجودة")
    params = SearchParams.from_dict(job["params"])
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    return create_job_from_params(f"{job['name']} (إعادة {stamp})", params, job["max_posts"],
                                  parent_job_id=job_id, created_by=created_by)


def recover_interrupted_jobs() -> int:
    """Jobs left 'running' by a closed application are marked 'stopped' (resumable)."""
    rows = db.fetch_all("SELECT id FROM search_jobs WHERE status = 'running'")
    for r in rows:
        if r["id"] in _futures and not _futures[r["id"]].done():
            continue
        models.update_job(r["id"], status="stopped", last_error="توقفت العملية بسبب إغلاق التطبيق")
        models.log_collection(r["id"], "WARNING", "job_interrupted", "تم إيقاف العملية لأن التطبيق أُغلق أثناء التنفيذ")
    return len(rows)


# ------------------------------------------------------------- control
def is_running(job_id: int) -> bool:
    f = _futures.get(job_id)
    return bool(f and not f.done())


def any_running() -> int | None:
    for jid, f in _futures.items():
        if not f.done():
            return jid
    return None


def start_job(job_id: int, resume: bool = False, manager: BrowserManager | None = None) -> Future:
    job = models.get_job(job_id)
    if not job:
        raise ValueError("العملية غير موجودة")
    if job["search_type"] == "import":
        raise ValueError("عمليات الاستيراد لا تُنفذ عبر المتصفح")
    running = any_running()
    if running is not None:
        raise RuntimeError(f"توجد عملية قيد التنفيذ حالياً (رقم {running}). أوقفها أو انتظر انتهاءها.")
    if job["status"] == "running":
        raise RuntimeError("العملية قيد التنفيذ بالفعل")
    if not resume and job["status"] != "new":
        raise RuntimeError("العملية نُفذت سابقاً؛ استخدم «استئناف» أو «إعادة تنفيذ»")
    if resume and job["status"] not in ("stopped", "failed"):
        raise RuntimeError("الاستئناف متاح للعمليات المتوقفة أو الفاشلة فقط")
    manager = manager or get_browser_manager()
    stop = threading.Event()
    _stop_flags[job_id] = stop
    models.update_job(job_id, status="running", started_at=job["started_at"] or db.utcnow(),
                      finished_at=None, last_error=None)
    models.log_collection(job_id, "INFO", "job_resumed" if resume else "job_started",
                          "استئناف العملية" if resume else "بدء تنفيذ العملية")
    fut = manager.submit(lambda bm: _run_job(bm, job_id, stop, resume), label=f"job:{job_id}")
    _futures[job_id] = fut
    return fut


def stop_job(job_id: int) -> bool:
    ev = _stop_flags.get(job_id)
    if ev and is_running(job_id):
        ev.set()
        models.log_collection(job_id, "INFO", "stop_requested", "طلب المستخدم إيقاف العملية")
        return True
    job = models.get_job(job_id)
    if job and job["status"] == "running":
        models.update_job(job_id, status="stopped", finished_at=db.utcnow())
        return True
    return False


# --------------------------------------------------------- persistence
def store_batch(job_id: int | None, query: str | None, posts, accounts, tz_name: str,
                seen_in_job: set[str], source_url: str | None = None) -> dict:
    """Save a batch; returns counters relative to this job."""
    posts, _ = dedupe_batch(posts)
    received = new = dup = 0
    with db.get_conn() as conn:
        for a in accounts:
            try:
                models.upsert_account(normalize_account(a), conn=conn)
            except Exception as exc:  # one bad account must not lose the batch
                log.warning("account %s not saved: %s", getattr(a, "username", "?"), exc)
        for p in posts:
            p = normalize_post(p)
            if p.post_id in seen_in_job:
                # Already counted for this job; still refresh metrics from a richer capture.
                if p.source == "graphql":
                    models.save_post(p, job_id, query, tz_name, source_url, conn=conn)
                continue
            is_new = models.save_post(p, job_id, query, tz_name, source_url, conn=conn)
            seen_in_job.add(p.post_id)
            received += 1
            if is_new:
                new += 1
            else:
                dup += 1
    if job_id is not None and received:
        models.increment_job(job_id, received=received, new=new, duplicate=dup)
    return {"received": received, "new": new, "duplicate": dup}


def import_file_as_job(name: str, filename: str, data: bytes, created_by: str | None = None) -> dict:
    posts, accounts, fmt = parse_file(filename, data)
    if not posts and not accounts:
        raise ValueError("لم يتم العثور على منشورات في الملف")
    job_id = models.create_job(name=name, search_type="import", query_text=filename, queries=[filename],
                               params={"file": filename, "format": fmt}, status="running",
                               created_by=created_by)
    models.update_job(job_id, started_at=db.utcnow())
    tz = db.get_setting("timezone", "Asia/Riyadh")
    counts = store_batch(job_id, f"file:{filename}", posts, accounts, tz, set())
    from processing.pipeline import run_pipeline
    run_pipeline(job_id=job_id)
    models.update_job(job_id, status="completed", finished_at=db.utcnow())
    models.log_collection(job_id, "INFO", "import_done", f"تم استيراد {counts['received']} منشور من {filename}",
                          {**counts, "format": fmt, "accounts": len(accounts)})
    db.audit("file_imported", f"job:{job_id}", {"file": filename, **counts}, actor=created_by)
    return {"job_id": job_id, "format": fmt, "accounts": len(accounts), **counts}


# --------------------------------------------------------------- runner
def _sleep(stop: threading.Event, lo: float, hi: float) -> None:
    stop.wait(random.uniform(lo, max(lo, hi)))


def _resume_query(query: str, oldest_iso: str | None, sort: str) -> str:
    if not oldest_iso or sort != "live":
        return query
    try:
        oldest = datetime.fromisoformat(oldest_iso).date()
    except ValueError:
        return query
    until = (oldest + timedelta(days=1)).isoformat()
    import re
    if "until:" in query:
        return re.sub(r"until:\d{4}-\d{2}-\d{2}", f"until:{until}", query)
    return f"{query} until:{until}"


def _collect_profile(bm: BrowserManager, job_id: int, username: str, tz: str) -> None:
    page = bm.page
    bm.drain_responses()
    page.goto(f"https://x.com/{username}", wait_until="domcontentloaded")
    page.wait_for_timeout(4000)
    accounts = []
    for url, payload in bm.drain_responses():
        if isinstance(payload, dict) and "__http_status__" in payload:
            continue
        _, accs = parse_graphql_payload(payload)
        accounts.extend(a for a in accs if a.username.lower() == username.lower())
    if accounts:
        best = next((a for a in accounts if a.is_profile), accounts[0])
        models.upsert_account(normalize_account(best))
        models.log_collection(job_id, "INFO", "profile_collected", f"تم جمع بيانات الحساب @{username}",
                              {"followers": best.followers_count, "following": best.following_count})
    else:
        models.log_collection(job_id, "WARNING", "profile_not_found", f"تعذر قراءة بيانات الحساب @{username}")


def _run_query(bm: BrowserManager, job: dict, query_index: int, query: str, stop: threading.Event,
               seen: set[str], progress: dict, tz: str) -> str:
    """Collect one query. Returns the end reason."""
    job_id = job["id"]
    page = bm.page
    max_posts = int(job["max_posts"])
    max_scrolls = db.get_setting_int("max_scrolls_per_query", 120)
    max_idle = db.get_setting_int("max_idle_scrolls", 6)
    dmin = db.get_setting_float("scroll_delay_min", 2.0)
    dmax = db.get_setting_float("scroll_delay_max", 4.5)
    backoff = db.get_setting_int("retry_backoff_seconds", 30)
    max_retries = db.get_setting_int("max_retries", 3)

    qp = progress.setdefault(str(query_index), {"query": query, "collected": 0, "done": False, "oldest": None})
    effective = _resume_query(query, qp.get("oldest"), job["sort_mode"]) if qp["collected"] else query
    url = search_url(effective, job["sort_mode"])
    models.log_collection(job_id, "INFO", "query_started", f"تنفيذ الاستعلام: {effective}", {"url": url})
    bm.drain_responses()
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_timeout(3500)
    state = bm.page_state()
    if state.get("login_form") or "/i/flow/login" in page.url:
        raise SessionExpired("انتهت جلسة X أو لم يتم تسجيل الدخول. سجّل الدخول من صفحة الاتصال ثم استأنف العملية.")
    if state.get("locked"):
        raise BrowserError("حساب X مقفل أو معلّق؛ أوقِف الجمع وراجع الحساب من المتصفح.")

    idle = retries = 0
    reason = "end_of_results"
    for scroll in range(max_scrolls):
        if stop.is_set():
            return "stopped"
        batch_new_to_job = 0
        graph_ids: set[str] = set()
        # 1) GraphQL responses
        for rurl, payload in bm.drain_responses():
            if isinstance(payload, dict) and "__http_status__" in payload:
                if payload["__http_status__"] == 429:
                    models.log_collection(job_id, "WARNING", "rate_limited", "X طلب إبطاء الطلبات (429)؛ انتظار قبل المتابعة")
                    stop.wait(backoff)
                continue
            posts, accounts = parse_graphql_payload(payload)
            graph_ids.update(p.post_id for p in posts)
            c = store_batch(job_id, query, posts, accounts, tz, seen, source_url=rurl.split("?")[0])
            batch_new_to_job += c["received"]
            for p in posts:
                if p.published_at and (not qp["oldest"] or p.published_at < qp["oldest"]):
                    qp["oldest"] = p.published_at
        # 2) DOM fallback
        try:
            items = page.evaluate(EXTRACT_JS)
        except Exception as exc:
            items = []
            log.warning("DOM extraction failed: %s", exc)
        dom_posts = [p for p in (post_from_dom(i) for i in items) if p and p.post_id not in graph_ids]
        if dom_posts:
            c = store_batch(job_id, query, dom_posts, [], tz, seen, source_url=page.url)
            batch_new_to_job += c["received"]
        qp["collected"] += batch_new_to_job
        models.update_job(job_id, progress=progress)
        if scroll % 3 == 0:
            bm.snapshot()

        if qp["collected"] >= max_posts:
            reason = "max_posts"
            break
        state = bm.page_state()
        if state.get("login_form"):
            raise SessionExpired("انتهت جلسة X أثناء الجمع. سجّل الدخول مرة أخرى ثم استأنف العملية.")
        if state.get("retry_button") or (state.get("rate_limited") and batch_new_to_job == 0):
            retries += 1
            if retries > max_retries:
                reason = "rate_limited"
                models.log_collection(job_id, "WARNING", "retry_exhausted",
                                      "توقف الاستعلام بعد تكرار رسالة الخطأ من X؛ يمكن الاستئناف لاحقاً")
                break
            wait = backoff * retries
            models.log_collection(job_id, "WARNING", "x_error_retry",
                                  f"ظهرت رسالة خطأ من X؛ إعادة المحاولة بعد {wait} ثانية ({retries}/{max_retries})")
            stop.wait(wait)
            try:
                page.evaluate(CLICK_RETRY_JS)
            except Exception:
                pass
            page.wait_for_timeout(3000)
            continue
        if state.get("empty_state") and not seen:
            reason = "no_results"
            break
        if batch_new_to_job == 0:
            idle += 1
            if idle >= max_idle:
                reason = "end_of_results"
                break
        else:
            idle = 0
        # Scroll like a reader would.
        try:
            page.mouse.wheel(0, random.randint(1800, 3200))
        except Exception:
            page.evaluate("window.scrollBy(0, window.innerHeight * 2)")
        _sleep(stop, dmin, dmax)
    else:
        reason = "max_scrolls"
    qp["done"] = reason in ("end_of_results", "max_posts", "no_results", "max_scrolls")
    models.update_job(job_id, progress=progress)
    models.log_collection(job_id, "INFO", "query_finished", f"انتهى الاستعلام ({reason}): {query}",
                          {"collected": qp["collected"], "reason": reason})
    return reason


def _run_job(bm: BrowserManager, job_id: int, stop: threading.Event, resume: bool) -> str:
    job = models.get_job(job_id)
    tz = db.get_setting("timezone", "Asia/Riyadh")
    progress = job["progress"] if resume else {}
    seen = {r["post_id"] for r in db.fetch_all("SELECT post_id FROM job_posts WHERE job_id = ?", (job_id,))}
    final = "completed"
    try:
        bm._start()
        bm.capture_enabled = True
        cookies = bm.context.cookies(["https://x.com"])
        if not sm.has_auth_cookie(cookies):
            raise SessionExpired("لم يتم تسجيل الدخول إلى X. افتح صفحة الاتصال وسجّل الدخول أولاً.")
        params = SearchParams.from_dict(job["params"])
        if job["search_type"] == "user" and params.collect_profiles and not resume:
            from search.query_builder import clean_username, split_list
            for u in split_list(params.usernames):
                if stop.is_set():
                    break
                try:
                    _collect_profile(bm, job_id, clean_username(u), tz)
                except Exception as exc:
                    models.log_collection(job_id, "WARNING", "profile_error", f"@{u}: {exc}")
                _sleep(stop, 1.5, 3.0)
        for i, q in enumerate(job["queries"]):
            if stop.is_set():
                final = "stopped"
                break
            if progress.get(str(i), {}).get("done"):
                continue
            reason = _run_query(bm, job, i, q, stop, seen, progress, tz)
            if reason == "stopped":
                final = "stopped"
                break
            _sleep(stop, 2.0, 4.0)
        if final == "completed" and any(not v.get("done") for v in progress.values()):
            final = "stopped"   # a query ended early (rate limit) → resumable
    except SessionExpired as exc:
        final = "failed"
        sm.record_status(sm.STATUS_EXPIRED, message=str(exc))
        models.update_job(job_id, last_error=str(exc))
        models.increment_job(job_id, errors=1)
        models.log_collection(job_id, "ERROR", "session_expired", str(exc))
    except Exception as exc:  # noqa: BLE001
        final = "failed"
        log.exception("job %s failed", job_id)
        models.update_job(job_id, last_error=f"{type(exc).__name__}: {exc}")
        models.increment_job(job_id, errors=1)
        models.log_collection(job_id, "ERROR", "job_failed", f"{type(exc).__name__}: {exc}")
    finally:
        bm.capture_enabled = False
        try:
            bm.snapshot()
        except Exception:
            pass
    # Process what was collected, whatever the outcome.
    try:
        from processing.pipeline import run_pipeline
        run_pipeline(job_id=job_id)
    except Exception as exc:  # noqa: BLE001
        models.log_collection(job_id, "ERROR", "processing_failed", str(exc))
    models.update_job(job_id, status=final, finished_at=db.utcnow(), progress=progress)
    j = models.get_job(job_id)
    models.log_collection(job_id, "INFO", "job_finished",
                          f"انتهت العملية بالحالة: {models.STATUS_LABELS_AR[final]}",
                          {k: j[k] for k in ("received_count", "new_count", "duplicate_count", "processed_count")})
    db.audit("job_finished", f"job:{job_id}", {"status": final})
    return final


def job_summary(job_id: int) -> dict:
    j = models.get_job(job_id)
    if not j:
        return {}
    j["running_now"] = is_running(job_id)
    j["status_ar"] = models.STATUS_LABELS_AR.get(j["status"], j["status"])
    return j


def wait(job_id: int, timeout: float | None = None) -> str | None:
    f = _futures.get(job_id)
    if not f:
        return None
    return f.result(timeout=timeout)


def to_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)
