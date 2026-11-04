"""Browser tests: real headless Chromium through Playwright.

x.com is never contacted: every request to https://x.com/** is answered by a
Playwright route with local TEST FIXTURES (tests/fixtures.py) that mimic the
page structure and GraphQL responses of the X web client. This exercises the
real browser thread, response capture, DOM extraction, scrolling loop, job
state machine, stop/resume and session handling.
"""
import json
import time
from urllib.parse import parse_qs, urlparse

import pytest

from browser import session_manager as sm
from browser.browser_manager import BrowserManager
from collectors import collection_manager as cm
from database import db, models
from search.query_builder import SearchParams
from tests import fixtures as fx

PER_PAGE = 10


def _fast_settings():
    for k, v in {"browser_headless": True, "scroll_delay_min": 0.05, "scroll_delay_max": 0.1, "max_idle_scrolls": 3,
                 "max_scrolls_per_query": 30, "retry_backoff_seconds": 1, "page_timeout_ms": 15000}.items():
        db.set_setting(k, v)


def _install_routes(bm: BrowserManager, pages: int = 3, offset: int = 0, calls: list | None = None):
    def handler(route):
        url = route.request.url
        if calls is not None:
            calls.append(url)
        u = urlparse(url)
        if "/i/api/graphql/" in u.path and u.path.endswith("/SearchTimeline"):
            page = int(parse_qs(u.query).get("page", ["0"])[0])
            tw = [fx.tweet(offset + page * PER_PAGE + i, author=1 + i % 3) for i in range(1, PER_PAGE + 1)]
            route.fulfill(status=200, content_type="application/json", body=json.dumps(fx.search_timeline(tw)))
        elif "/i/api/graphql/" in u.path and u.path.endswith("/UserByScreenName"):
            route.fulfill(status=200, content_type="application/json", body=json.dumps(fx.profile_payload(1)))
        elif u.path.startswith("/search"):
            route.fulfill(status=200, content_type="text/html", body=fx.fake_x_page(pages))
        elif u.path.startswith("/fixture_user"):
            route.fulfill(status=200, content_type="text/html", body=(
                "<html><body><script>fetch('/i/api/graphql/Q/UserByScreenName')</script>profile</body></html>"))
        else:
            logged = "auth_token=" in (route.request.headers.get("cookie") or "")
            nav = '<div data-testid="SideNav_AccountSwitcher_Button">fixture me @fixture_me</div>' if logged else \
                '<input autocomplete="username">'
            route.fulfill(status=200, content_type="text/html", body=f"<html><body>{nav} fixture home</body></html>")

    def _do(b):
        b._start(headless=True)
        b.context.route("https://x.com/**", handler)
    bm.call(_do, timeout=90)


def _login(bm: BrowserManager):
    bm.call(lambda b: b.context.add_cookies([{
        "name": "auth_token", "value": "fixture-token", "domain": ".x.com", "path": "/",
        "expires": int(time.time()) + 3600, "httpOnly": True, "secure": True, "sameSite": "None"}]), timeout=30)


@pytest.fixture
def bm():
    _fast_settings()
    m = BrowserManager()
    yield m
    m.shutdown()


def test_session_helpers(temp_env):
    assert sm.has_auth_cookie([{"name": "auth_token", "value": "v", "domain": ".x.com"}])
    assert not sm.has_auth_cookie([{"name": "auth_token", "value": "", "domain": ".x.com"}])
    assert not sm.has_auth_cookie([{"name": "ct0", "value": "v", "domain": ".x.com"}])
    assert sm.protect_session_dir()
    import os, stat
    assert stat.S_IMODE(os.stat(sm.session_dir()).st_mode) == 0o700
    sm.record_status(sm.STATUS_CONNECTED, "fixture_me")
    assert sm.current_status()["status"] == "connected" and sm.current_status()["username"] == "fixture_me"
    (sm.session_dir() / "Cookies").write_text("x")
    sm.wipe_session()
    assert not sm.session_exists() and sm.current_status()["status"] == "disconnected"


def test_session_persists_across_browser_restarts(bm):
    _install_routes(bm)
    st = bm.check_status(navigate=True)
    assert st["status"] == sm.STATUS_DISCONNECTED and not st["auth_cookie"]
    _login(bm)
    st = bm.check_status(navigate=True)
    assert st["status"] == sm.STATUS_CONNECTED and st["username"] == "fixture_me"
    assert bm.screenshot()[:2] == b"\xff\xd8"           # JPEG preview for the in-app viewer
    bm.close()
    assert not bm.is_open
    # New browser process, same profile → still logged in
    _install_routes(bm)
    assert bm.check_status(navigate=True)["status"] == sm.STATUS_CONNECTED
    # Logout clears the session
    bm.logout(wipe=True)
    assert sm.current_status()["status"] == sm.STATUS_DISCONNECTED
    _install_routes(bm)
    assert bm.check_status(navigate=True)["auth_cookie"] is False


def test_collection_job_end_to_end(bm):
    _install_routes(bm, pages=3)
    _login(bm)
    jid = cm.create_job_from_params("fixture e2e", SearchParams(search_type="keyword", keywords="ذكاء"), max_posts=500)
    fut = cm.start_job(jid, manager=bm)
    assert fut.result(timeout=180) == "completed"
    j = models.get_job(jid)
    assert j["status"] == "completed"
    assert j["received_count"] == 30 and j["new_count"] == 30 and j["duplicate_count"] == 0
    assert j["processed_count"] == 30
    sources = {r["source"] for r in db.fetch_all("SELECT source FROM posts")}
    assert sources == {"graphql"}
    row = db.fetch_one("SELECT * FROM posts WHERE post_id = ?", (str(fx.BASE_ID + 1),))
    assert row["likes_count"] == 10 and row["views_count"] == 100 and row["clean_text"]
    events = [r["event"] for r in db.fetch_all("SELECT event FROM collection_logs WHERE job_id = ?", (jid,))]
    assert "query_started" in events and "job_finished" in events
    # Re-running the same search: everything is a duplicate, nothing is lost
    j2 = cm.rerun_job(jid)
    assert cm.start_job(j2, manager=bm).result(timeout=180) == "completed"
    r2 = models.get_job(j2)
    assert (r2["received_count"], r2["new_count"], r2["duplicate_count"]) == (30, 0, 30)
    assert r2["parent_job_id"] == jid
    assert db.fetch_value("SELECT COUNT(*) FROM posts") == 30
    assert db.fetch_value("SELECT COUNT(*) FROM post_metrics") >= 60


def test_max_posts_limit_and_user_profile(bm):
    _install_routes(bm, pages=5)
    _login(bm)
    jid = cm.create_job_from_params("users", SearchParams(search_type="user", usernames=["fixture_user1"]), max_posts=15)
    assert cm.start_job(jid, manager=bm).result(timeout=180) == "completed"
    j = models.get_job(jid)
    assert 15 <= j["received_count"] < 50
    assert j["progress"]["0"]["done"]
    acc = db.fetch_one("SELECT * FROM accounts WHERE username = 'fixture_user1'")
    assert acc["followers_count"] == 1000 and acc["description"]
    assert "profile_collected" in [r["event"] for r in db.fetch_all("SELECT event FROM collection_logs WHERE job_id=?", (jid,))]


def test_stop_and_resume(bm):
    db.set_setting("scroll_delay_min", 1.0)
    db.set_setting("scroll_delay_max", 1.0)
    _install_routes(bm, pages=8)
    _login(bm)
    jid = cm.create_job_from_params("stop-resume", SearchParams(search_type="keyword", keywords="x"), max_posts=1000)
    fut = cm.start_job(jid, manager=bm)
    for _ in range(100):
        if models.get_job(jid)["received_count"] >= 10:
            break
        time.sleep(0.2)
    assert cm.stop_job(jid)
    assert fut.result(timeout=120) == "stopped"
    first = models.get_job(jid)
    assert first["status"] == "stopped" and 0 < first["received_count"] < 80
    with pytest.raises(RuntimeError):
        cm.start_job(jid, manager=bm)             # not "new" any more → only resume is allowed
    db.set_setting("scroll_delay_min", 0.05)
    db.set_setting("scroll_delay_max", 0.1)
    assert cm.start_job(jid, resume=True, manager=bm).result(timeout=180) == "completed"
    after = models.get_job(jid)
    assert after["received_count"] == 80
    assert after["progress"]["0"]["done"]


def test_expired_session_fails_cleanly(bm):
    _install_routes(bm)
    jid = cm.create_job_from_params("no login", SearchParams(search_type="keyword", keywords="x"))
    assert cm.start_job(jid, manager=bm).result(timeout=120) == "failed"
    j = models.get_job(jid)
    assert j["status"] == "failed" and "تسجيل الدخول" in j["last_error"] and j["error_count"] == 1
    assert sm.current_status()["status"] == sm.STATUS_EXPIRED
    # once logged in, the failed job can be resumed
    _login(bm)
    assert cm.start_job(jid, resume=True, manager=bm).result(timeout=180) == "completed"


def test_only_one_job_at_a_time_and_recovery(bm):
    _install_routes(bm, pages=8)
    _login(bm)
    db.set_setting("scroll_delay_min", 0.5)
    j1 = cm.create_job_from_params("a", SearchParams(search_type="keyword", keywords="a"))
    j2 = cm.create_job_from_params("b", SearchParams(search_type="keyword", keywords="b"))
    f1 = cm.start_job(j1, manager=bm)
    with pytest.raises(RuntimeError):
        cm.start_job(j2, manager=bm)
    cm.stop_job(j1)
    f1.result(timeout=120)
    # A job left "running" by a crashed process is recovered as "stopped"
    models.update_job(j2, status="running")
    assert cm.recover_interrupted_jobs() == 1
    assert models.get_job(j2)["status"] == "stopped"


def test_dom_fallback_without_graphql(bm):
    """When no GraphQL response is visible, posts are read from the rendered page."""
    article = """<article data-testid="tweet"><div data-testid="User-Name"><span>اسم {n}</span></div>
      <a href="/fixture_dom/status/{pid}"><time datetime="2026-11-01T10:0{n}:00.000Z">t</time></a>
      <div data-testid="tweetText" lang="ar">منشور اختبار من الصفحة {n} #وسم_اختبار <img alt="😀"></div>
      <button data-testid="reply" aria-label="{n} ردود"></button>
      <button data-testid="retweet" aria-label="1.5K reposts. Repost"></button>
      <button data-testid="like" aria-label="١٢ إعجاب"></button>
      <a href="/fixture_dom/status/{pid}/analytics" aria-label="2,345 views"></a></article>"""
    html = "<html><head><meta charset=\"utf-8\"></head><body>" + "".join(article.format(n=i, pid=fx.BASE_ID + 500 + i) for i in range(1, 6)) + "</body></html>"

    def _do(b):
        b._start(headless=True)
        b.context.route("https://x.com/**", lambda r: r.fulfill(status=200, content_type="text/html", body=html))
    bm.call(_do, timeout=90)
    _login(bm)
    jid = cm.create_job_from_params("dom", SearchParams(search_type="keyword", keywords="x"))
    assert cm.start_job(jid, manager=bm).result(timeout=120) == "completed"
    rows = db.fetch_all("SELECT * FROM posts ORDER BY post_id")
    assert len(rows) == 5 and {r["source"] for r in rows} == {"dom"}
    r = rows[0]
    assert r["username"] == "fixture_dom" and r["display_name"] == "اسم 1"
    assert (r["replies_count"], r["reposts_count"], r["likes_count"], r["views_count"]) == (1, 1500, 12, 2345)
    assert "😀" in r["raw_text"] and r["hashtags_json"] == '["وسم_اختبار"]'
    assert r["published_at"] == "2026-11-01T10:01:00+00:00"


TOKEN = "0123456789abcdef0123456789abcdef01234567"


def test_parse_cookie_input_formats():
    one = sm.parse_cookie_input(TOKEN)
    assert one[0]["name"] == "auth_token" and one[0]["domain"] == ".x.com" and one[0]["httpOnly"]
    hdr = sm.parse_cookie_input(f"Cookie: guest_id=v1%3A1; auth_token={TOKEN}; ct0=abcdef123; other=zzz")
    assert sorted(c["name"] for c in hdr) == ["auth_token", "ct0", "guest_id"]
    js = json.dumps([{"name": "auth_token", "value": TOKEN, "domain": ".x.com", "expirationDate": 4102444800,
                      "httpOnly": True, "sameSite": "no_restriction"},
                     {"name": "auth_token", "value": "ffff", "domain": ".google.com"}])
    parsed = sm.parse_cookie_input(js, ct0="beef")
    assert {c["name"] for c in parsed} == {"auth_token", "ct0"}
    assert [c for c in parsed if c["name"] == "auth_token"][0]["expires"] == 4102444800
    for bad in ("", "not-a-token!", "ct0=abc", "auth_token=12 34"):
        with pytest.raises(sm.CookieInputError):
            sm.parse_cookie_input(bad)


def test_import_session_connects_and_local_disconnect(bm):
    _install_routes(bm)
    r = bm.import_session(sm.parse_cookie_input(TOKEN, ct0="abc123"))
    assert r["status"] == sm.STATUS_CONNECTED and r["username"] == "fixture_me"
    # the imported session can collect immediately
    jid = cm.create_job_from_params("after import", SearchParams(search_type="keyword", keywords="x"), max_posts=10)
    assert cm.start_job(jid, manager=bm).result(timeout=180) == "completed"
    # local disconnect never visits x.com/logout (the user's own browser stays logged in)
    calls: list = []
    bm.call(lambda b: b.context.route("https://x.com/logout*", lambda route: (calls.append(1), route.abort())), timeout=30)
    bm.logout(wipe=True, server_logout=False)
    assert calls == [] and sm.current_status()["status"] == sm.STATUS_DISCONNECTED and not sm.session_exists()


def test_import_session_rejected_token_is_removed(bm):
    def _do(b):
        b._start(headless=True)
        # X answers with the login form → token rejected
        b.context.route("https://x.com/**", lambda r: r.fulfill(status=200, content_type="text/html",
                                                                body='<html><body><input autocomplete="username"></body></html>'))
    bm.call(_do, timeout=90)
    r = bm.import_session(sm.parse_cookie_input(TOKEN))
    assert r["status"] != sm.STATUS_CONNECTED
    assert not sm.has_auth_cookie(bm.call(lambda b: b.context.cookies(["https://x.com"]), timeout=30))
