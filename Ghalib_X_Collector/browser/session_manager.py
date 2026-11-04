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


# ------------------------------------------------- reuse an existing login
# Chrome/Edge 136+ refuse automation of the user's main profile and encrypt its
# cookies (app-bound encryption), so the app cannot read them by itself. The user
# copies the X session cookies from their own browser once; they are added to the
# app's private browser profile and never written to the database or the logs.
import json as _json
import re as _re
import time as _time

_X_DOMAINS = ("x.com", "twitter.com")
_USEFUL = {"auth_token", "ct0", "twid", "kdt", "att", "guest_id", "personalization_id", "lang"}


class CookieInputError(ValueError):
    pass


def _norm_cookie(name: str, value: str, expires=None, http_only=None, same_site=None) -> dict:
    exp = None
    try:
        if expires not in (None, "", "Session") and float(expires) > _time.time():
            exp = int(float(expires))
    except (TypeError, ValueError):
        exp = None
    return {
        "name": name.strip(),
        "value": value.strip().strip('"'),
        "domain": ".x.com",
        "path": "/",
        "expires": exp or int(_time.time()) + 180 * 24 * 3600,
        "httpOnly": bool(http_only) if http_only is not None else name in ("auth_token", "kdt"),
        "secure": True,
        "sameSite": "None" if (same_site or "").lower() in ("", "none", "no_restriction", "unspecified") else (
            "Lax" if (same_site or "").lower() == "lax" else "Strict"),
    }


def parse_cookie_input(text: str, ct0: str | None = None) -> list[dict]:
    """Accepts: the auth_token value alone, a Cookie header ("a=b; c=d"), or a JSON
    export (Cookie-Editor / EditThisCookie). Returns Playwright cookies for .x.com."""
    t = (text or "").strip()
    if not t:
        raise CookieInputError("الصق قيمة auth_token أولاً")
    cookies: list[dict] = []
    if t.startswith("[") or t.startswith("{"):
        try:
            data = _json.loads(t)
        except _json.JSONDecodeError as exc:
            raise CookieInputError("نص JSON غير صالح") from exc
        if isinstance(data, dict):
            data = data.get("cookies", [data])
        for c in data:
            if not isinstance(c, dict) or not c.get("name"):
                continue
            dom = str(c.get("domain", "x.com"))
            if not any(d in dom for d in _X_DOMAINS) or c["name"] not in _USEFUL:
                continue
            cookies.append(_norm_cookie(c["name"], str(c.get("value", "")), c.get("expirationDate") or c.get("expires"),
                                        c.get("httpOnly"), c.get("sameSite")))
    elif "=" in t:
        if t.lower().startswith("cookie:"):
            t = t[7:]
        for part in t.split(";"):
            if "=" not in part:
                continue
            name, value = part.split("=", 1)
            if name.strip() in _USEFUL and value.strip():
                cookies.append(_norm_cookie(name, value))
    else:
        cookies.append(_norm_cookie("auth_token", t))
    if ct0 and ct0.strip():
        cookies = [c for c in cookies if c["name"] != "ct0"] + [_norm_cookie("ct0", ct0)]
    auth = [c for c in cookies if c["name"] == "auth_token"]
    if not auth:
        raise CookieInputError("لم يتم العثور على auth_token في النص الملصوق")
    if not _re.fullmatch(r"[0-9a-fA-F]{20,80}", auth[0]["value"]):
        raise CookieInputError("قيمة auth_token غير صحيحة (يجب أن تكون حروفاً وأرقاماً سداسية عشرية، عادة 40 خانة)")
    for c in cookies:
        if _re.search(r"[\s;,]", c["value"]):
            raise CookieInputError(f"قيمة {c['name']} تحتوي على مسافات أو فواصل")
    # keep the last occurrence of each name
    return list({c["name"]: c for c in cookies}.values())
