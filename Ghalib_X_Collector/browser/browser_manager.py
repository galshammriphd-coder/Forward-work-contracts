"""Browser component: one Playwright browser owned by one dedicated thread.

Playwright's sync API objects can only be used from the thread that created
them, while Streamlit re-runs pages on many threads. Every browser action is
therefore sent to a single worker thread through ``BrowserManager.call()``.
The component is independent of the rest of the application: it knows nothing
about jobs or the database except the session status it records.
"""
from __future__ import annotations

import asyncio
import logging
import os
import queue
import sys
import threading
import time
from concurrent.futures import Future
from typing import Any, Callable

import config
from browser import session_manager as sm
from browser.dom_extractor import PAGE_STATE_JS
from database import db

log = logging.getLogger("ghalib.browser")

GRAPHQL_MARKERS = ("/i/api/graphql/", "/graphql/")


class BrowserError(RuntimeError):
    pass


class BrowserBusy(BrowserError):
    pass


class BrowserManager:
    def __init__(self) -> None:
        self._q: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._pw = None
        self.context = None
        self.page = None
        self.headless: bool | None = None
        self.busy_with: str | None = None
        self.last_screenshot: bytes | None = None
        self.last_screenshot_at: float = 0.0
        self.last_error: str | None = None
        self._responses: list = []
        self._resp_lock = threading.Lock()
        self.capture_enabled = False

    # ----------------------------------------------------------- thread
    def _ensure_thread(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._thread = threading.Thread(target=self._loop, name="ghalib-browser", daemon=True)
            self._thread.start()

    def _loop(self) -> None:
        if sys.platform.startswith("win"):
            # Playwright needs the Proactor loop (subprocess support) on Windows;
            # some web frameworks switch the global policy to Selector.
            try:
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", DeprecationWarning)
                    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            except Exception:  # pragma: no cover
                pass
        while True:
            fn, fut, label = self._q.get()
            if fn is None:
                break
            if not fut.set_running_or_notify_cancel():
                continue
            self.busy_with = label
            try:
                fut.set_result(fn(self))
            except BaseException as exc:  # noqa: BLE001 — forwarded to the caller
                self.last_error = f"{type(exc).__name__}: {exc}"
                log.exception("browser task %s failed", label)
                fut.set_exception(exc)
            finally:
                self.busy_with = None

    def submit(self, fn: Callable[["BrowserManager"], Any], label: str = "task") -> Future:
        self._ensure_thread()
        fut: Future = Future()
        self._q.put((fn, fut, label))
        return fut

    def call(self, fn: Callable[["BrowserManager"], Any], timeout: float = 120, label: str = "task",
             fail_if_busy: bool = True) -> Any:
        if fail_if_busy and self.busy_with and self.busy_with.startswith("job:"):
            raise BrowserBusy(f"المتصفح مشغول بعملية جمع ({self.busy_with})")
        return self.submit(fn, label).result(timeout=timeout)

    # ------------------------------------------------- browser lifecycle
    @property
    def is_open(self) -> bool:
        try:
            return self.context is not None and self.page is not None and not self.page.is_closed()
        except Exception:
            return False

    def _start(self, headless: bool | None = None) -> None:
        """Runs on the worker thread."""
        if headless is None:
            headless = db.get_setting_bool("browser_headless", False)
        if self.is_open and self.headless == headless:
            return
        if self.is_open:
            self._close()
        from playwright.sync_api import sync_playwright

        if self._pw is None:
            self._pw = sync_playwright().start()
        profile = sm.session_dir()
        profile.mkdir(parents=True, exist_ok=True)
        sm.protect_session_dir(profile)
        channel = (db.get_setting("browser_channel", "") or "").strip() or None
        kwargs: dict = dict(
            user_data_dir=str(profile),
            headless=headless,
            viewport={"width": 1280, "height": 900},
            locale="ar-SA",
            timezone_id=db.get_setting("timezone", "Asia/Riyadh") or "Asia/Riyadh",
        )
        executable = (db.get_setting("browser_executable", "") or os.getenv("GHALIB_BROWSER_EXECUTABLE", "")).strip()
        if executable:
            kwargs["executable_path"] = executable
        elif channel:
            kwargs["channel"] = channel
        try:
            self.context = self._pw.chromium.launch_persistent_context(**kwargs)
        except Exception as exc:
            msg = str(exc)
            if "Executable doesn't exist" in msg or "playwright install" in msg:
                raise BrowserError(
                    "متصفح Playwright غير مثبت. شغّل: python -m playwright install chromium "
                    "أو اختر Microsoft Edge من الإعدادات."
                ) from exc
            if "ProcessSingleton" in msg or "SingletonLock" in msg or "user data directory is already in use" in msg:
                raise BrowserError("ملف الجلسة مستخدم من نافذة متصفح أخرى. أغلقها ثم أعد المحاولة.") from exc
            raise
        self.context.set_default_timeout(db.get_setting_int("page_timeout_ms", 45000))
        self.context.on("close", lambda *_: self._on_closed())
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        self.page.on("response", self._on_response)
        self.headless = headless
        db.audit("browser_opened", "x.com", {"headless": headless, "channel": channel or "chromium"})

    def _on_closed(self) -> None:
        self.context = None
        self.page = None

    def _on_response(self, response) -> None:
        # Keep a reference only; the body is read later on the same thread.
        if not self.capture_enabled:
            return
        try:
            url = response.url
            if any(m in url for m in GRAPHQL_MARKERS) and response.request.method in ("GET", "POST"):
                with self._resp_lock:
                    self._responses.append(response)
        except Exception:
            pass

    def drain_responses(self) -> list[tuple[str, Any]]:
        """Return (url, json) for the GraphQL responses received since the last call."""
        with self._resp_lock:
            pending, self._responses = self._responses, []
        out = []
        for r in pending:
            try:
                if r.status != 200:
                    out.append((r.url, {"__http_status__": r.status}))
                    continue
                out.append((r.url, r.json()))
            except Exception:
                continue
        return out

    def _close(self) -> None:
        try:
            if self.context is not None:
                self.context.close()
        except Exception:
            pass
        self.context = None
        self.page = None

    def _shutdown(self) -> None:
        self._close()
        try:
            if self._pw is not None:
                self._pw.stop()
        except Exception:
            pass
        self._pw = None

    # --------------------------------------------------------- helpers
    def _page(self):
        if not self.is_open:
            self._start()
        return self.page

    def snapshot(self, full_page: bool = False) -> bytes | None:
        """Worker-thread helper: screenshot of the current page."""
        try:
            img = self.page.screenshot(full_page=full_page, type="jpeg", quality=70)
            self.last_screenshot, self.last_screenshot_at = img, time.time()
            return img
        except Exception:
            return None

    def page_state(self) -> dict:
        try:
            return self.page.evaluate(PAGE_STATE_JS)
        except Exception as exc:
            return {"error": str(exc)}

    def _status(self, navigate: bool) -> dict:
        page = self._page()
        if navigate:
            # Always (re)load: a page opened before login still shows the login form.
            try:
                page.goto(config.X_HOME_URL, wait_until="domcontentloaded")
                page.wait_for_timeout(3500)
            except Exception as exc:
                log.warning("home navigation failed: %s", exc)
        cookies = self.context.cookies(["https://x.com", "https://twitter.com"])
        has_cookie = sm.has_auth_cookie(cookies)
        state = self.page_state()
        handle = state.get("handle")
        if has_cookie and not state.get("login_form"):
            status = sm.STATUS_CONNECTED
        elif sm.session_exists() and db.get_setting("session_status") == sm.STATUS_CONNECTED:
            status = sm.STATUS_EXPIRED
        else:
            status = sm.STATUS_DISCONNECTED
        prev = db.get_setting("session_username", "") or ""
        sm.record_status(status, username=handle or (prev if status == sm.STATUS_CONNECTED else ""))
        self.snapshot()
        return {"status": status, "username": handle, "url": page.url, "auth_cookie": has_cookie,
                "state": state}

    # ------------------------------------------------- public operations
    def open_x(self, target: str | None = None, timeout: float = 120) -> dict:
        def _do(bm: "BrowserManager"):
            page = bm._page()
            url = target or config.X_BASE_URL
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(2500)
            if target is None:
                # Already logged in → home; otherwise X shows its login page.
                cookies = bm.context.cookies(["https://x.com"])
                if not sm.has_auth_cookie(cookies):
                    page.goto(config.X_LOGIN_URL, wait_until="domcontentloaded")
                    page.wait_for_timeout(1500)
            try:
                page.bring_to_front()
            except Exception:
                pass
            bm.snapshot()
            return {"url": page.url}

        return self.call(_do, timeout=timeout, label="open")

    def check_status(self, navigate: bool = True, timeout: float = 90) -> dict:
        if self.busy_with and self.busy_with.startswith("job:"):
            return {**sm.current_status(), "busy": self.busy_with}
        return self.call(lambda bm: bm._status(navigate), timeout=timeout, label="status")

    def logout(self, wipe: bool = False, timeout: float = 90) -> dict:
        def _do(bm: "BrowserManager"):
            result = {"logged_out": False}
            if bm.is_open or sm.session_exists():
                page = bm._page()
                try:
                    page.goto(config.X_LOGOUT_URL, wait_until="domcontentloaded")
                    page.wait_for_timeout(2000)
                    btn = page.locator('[data-testid="confirmationSheetConfirm"]')
                    if btn.count():
                        btn.first.click()
                        page.wait_for_timeout(3000)
                except Exception as exc:
                    log.warning("logout page failed: %s", exc)
                # Remove the authentication cookies locally in any case.
                try:
                    bm.context.clear_cookies()
                except Exception:
                    pass
                result["logged_out"] = True
            bm._close()
            if wipe:
                sm.wipe_session()
            sm.record_status(sm.STATUS_DISCONNECTED, username="", message="تم تسجيل الخروج")
            db.audit("logout", "x.com", {"wipe": wipe})
            return result

        return self.call(_do, timeout=timeout, label="logout")

    def screenshot(self, timeout: float = 30) -> bytes | None:
        if self.busy_with:
            return self.last_screenshot
        if not self.is_open:
            return self.last_screenshot
        return self.call(lambda bm: bm.snapshot(), timeout=timeout, label="screenshot")

    def goto(self, url: str, timeout: float = 90) -> dict:
        def _do(bm: "BrowserManager"):
            page = bm._page()
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            bm.snapshot()
            return {"url": page.url}

        return self.call(_do, timeout=timeout, label="goto")

    def close(self, timeout: float = 60) -> None:
        if self._thread and self._thread.is_alive():
            self.call(lambda bm: bm._close(), timeout=timeout, label="close")

    def shutdown(self) -> None:
        if self._thread and self._thread.is_alive():
            try:
                self.submit(lambda bm: bm._shutdown(), label="shutdown").result(timeout=60)
            except Exception:
                pass
            self._q.put((None, None, None))

    def info(self) -> dict:
        return {
            "thread_alive": bool(self._thread and self._thread.is_alive()),
            "open": self.is_open,
            "headless": self.headless,
            "busy_with": self.busy_with,
            "last_error": self.last_error,
            "url": (self.page.url if self.is_open else None) if not self.busy_with else None,
        }


_manager: BrowserManager | None = None
_manager_lock = threading.Lock()


def get_browser_manager() -> BrowserManager:
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = BrowserManager()
        return _manager
