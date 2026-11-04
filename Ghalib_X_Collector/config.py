"""Central configuration for Ghalib X Data Collector.

Every path is resolved relative to the project folder so the application runs
from any location on Windows or Linux. Values can be overridden with
environment variables (prefix ``GHALIB_``).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "Ghalib X Data Collector"
APP_VERSION = "1.0.0"

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = Path(os.getenv("GHALIB_DATA_DIR", BASE_DIR / "data"))
DB_PATH = Path(os.getenv("GHALIB_DB_PATH", DATA_DIR / "ghalib_x.db"))
SESSION_DIR = Path(os.getenv("GHALIB_SESSION_DIR", DATA_DIR / "browser_session"))
LOG_DIR = Path(os.getenv("GHALIB_LOG_DIR", BASE_DIR / "logs"))
BACKUP_DIR = Path(os.getenv("GHALIB_BACKUP_DIR", BASE_DIR / "backups"))
EXPORT_DIR = Path(os.getenv("GHALIB_EXPORT_DIR", BASE_DIR / "exports_data"))
ASSETS_DIR = BASE_DIR / "assets"
SCHEMA_PATH = BASE_DIR / "database" / "schema.sql"
MODELS_DIR = Path(os.getenv("GHALIB_MODELS_DIR", DATA_DIR / "models"))

X_BASE_URL = "https://x.com"
X_LOGIN_URL = "https://x.com/i/flow/login"
X_HOME_URL = "https://x.com/home"
X_LOGOUT_URL = "https://x.com/logout"

IS_WINDOWS = sys.platform.startswith("win")

# Collection defaults (all of them can be changed from the Settings page).
DEFAULTS = {
    "timezone": "Asia/Riyadh",
    "browser_headless": "false",          # login always needs a visible window
    "browser_channel": "",                # "" = bundled Chromium, "msedge" / "chrome" = installed browser
    "browser_executable": "",             # optional full path to a Chromium-based browser executable
    "scroll_delay_min": "2.0",            # seconds between scrolls (lower bound)
    "scroll_delay_max": "4.5",            # seconds between scrolls (upper bound)
    "max_posts_per_query": "300",
    "max_scrolls_per_query": "120",
    "max_idle_scrolls": "6",              # stop a query after N scrolls without new posts
    "page_timeout_ms": "45000",
    "retry_backoff_seconds": "30",
    "max_retries": "3",
    "ui_theme": "light",
    "auth_enabled": "false",
}

ARABIC_FONT_CANDIDATES = [
    os.getenv("GHALIB_PDF_FONT", ""),
    r"C:\Windows\Fonts\tahoma.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\segoeui.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
]


def pdf_font_path() -> str | None:
    for candidate in ARABIC_FONT_CANDIDATES:
        if candidate and Path(candidate).exists():
            return candidate
    return None


def ensure_dirs() -> None:
    for d in (DATA_DIR, SESSION_DIR, LOG_DIR, BACKUP_DIR, EXPORT_DIR, MODELS_DIR):
        d.mkdir(parents=True, exist_ok=True)
