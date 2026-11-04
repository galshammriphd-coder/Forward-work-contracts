"""Local browser-session handling.

* The user types the password into x.com directly; the application never sees,
  asks for or stores it. What persists is the browser profile (cookies) in
  ``data/browser_session``, exactly like a normal browser would keep it.
* The profile folder is restricted to the current OS user (chmod 700 on
  Linux/macOS, ``icacls`` on Windows).
* Session status is cached in ``application_settings`` so every page can show it.
"""
from __future__ import annotations

import getpass
import os
import shutil
import stat
import subprocess
from pathlib import Path

import config
from database import db

STATUS_CONNECTED = "connected"
STATUS_DISCONNECTED = "disconnected"
STATUS_EXPIRED = "expired"
STATUS_UNKNOWN = "unknown"
STATUS_LABELS_AR = {
    STATUS_CONNECTED: "متصل",
    STATUS_DISCONNECTED: "غير متصل",
    STATUS_EXPIRED: "انتهت الجلسة",
    STATUS_UNKNOWN: "غير معروف",
}
AUTH_COOKIE = "auth_token"


def session_dir() -> Path:
    return Path(config.SESSION_DIR)


def protect_session_dir(path: Path | None = None) -> bool:
    """Restrict the session folder to the current user. Returns True when applied."""
    path = Path(path or session_dir())
    path.mkdir(parents=True, exist_ok=True)
    try:
        if config.IS_WINDOWS:
            user = os.environ.get("USERNAME") or getpass.getuser()
            subprocess.run(
                ["icacls", str(path), "/inheritance:r", "/grant:r", f"{user}:(OI)(CI)F"],
                check=True, capture_output=True, timeout=30,
            )
        else:
            os.chmod(path, stat.S_IRWXU)
        return True
    except Exception:
        return False


def session_exists() -> bool:
    d = session_dir()
    return d.exists() and any(d.iterdir())


def has_auth_cookie(cookies: list[dict]) -> bool:
    for c in cookies or []:
        if c.get("name") == AUTH_COOKIE and c.get("value") and (
            "x.com" in (c.get("domain") or "") or "twitter.com" in (c.get("domain") or "")
        ):
            return True
    return False


def record_status(status: str, username: str | None = None, message: str = "") -> None:
    db.set_setting("session_status", status)
    db.set_setting("session_checked_at", db.utcnow())
    if username is not None:
        db.set_setting("session_username", username)
    if message:
        db.set_setting("session_message", message)


def current_status() -> dict:
    return {
        "status": db.get_setting("session_status", STATUS_UNKNOWN) or STATUS_UNKNOWN,
        "username": db.get_setting("session_username", "") or "",
        "checked_at": db.get_setting("session_checked_at", "") or "",
        "message": db.get_setting("session_message", "") or "",
        "profile_exists": session_exists(),
    }


def wipe_session() -> None:
    """Delete the stored browser profile (cookies, cache). Browser must be closed."""
    d = session_dir()
    if d.exists():
        shutil.rmtree(d, ignore_errors=False)
    d.mkdir(parents=True, exist_ok=True)
    protect_session_dir(d)
    record_status(STATUS_DISCONNECTED, username="", message="تم حذف ملفات الجلسة المحلية")
    db.audit("session_wiped", str(d))
