import sys
from pathlib import Path

import os

import pytest

# Use a preinstalled Chromium when the Playwright-managed one is absent (CI containers).
if not os.getenv("GHALIB_BROWSER_EXECUTABLE") and Path("/opt/pw-browsers/chromium").exists():
    os.environ["GHALIB_BROWSER_EXECUTABLE"] = "/opt/pw-browsers/chromium"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from database import db  # noqa: E402


@pytest.fixture(autouse=True)
def temp_env(tmp_path, monkeypatch):
    """Every test gets its own database, session, export and backup folders."""
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(config, "SESSION_DIR", tmp_path / "session")
    monkeypatch.setattr(config, "EXPORT_DIR", tmp_path / "exports")
    monkeypatch.setattr(config, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(config, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(config, "MODELS_DIR", tmp_path / "models")
    config.ensure_dirs()
    db.reset_init_cache()
    db.init_db()
    yield tmp_path
    db.reset_init_cache()
