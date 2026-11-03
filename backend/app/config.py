"""Runtime configuration (environment variables)."""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("RA_DATA_DIR", BASE_DIR / "data")).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'research_analytics.db'}")
# Fernet key used to encrypt uploaded files at rest. Generated on first run if not provided.
ENCRYPTION_KEY = os.getenv("RA_ENCRYPTION_KEY")
TOKEN_TTL_HOURS = int(os.getenv("RA_TOKEN_TTL_HOURS", "72"))
MAX_UPLOAD_MB = int(os.getenv("RA_MAX_UPLOAD_MB", "200"))
ALLOW_REGISTRATION = os.getenv("RA_ALLOW_REGISTRATION", "1") == "1"
CORS_ORIGINS = [o for o in os.getenv("RA_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o]
FRONTEND_DIST = Path(os.getenv("RA_FRONTEND_DIST", BASE_DIR.parent / "frontend" / "dist"))
PDF_FONT = os.getenv("RA_PDF_FONT", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
PDF_FONT_BOLD = os.getenv("RA_PDF_FONT_BOLD", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
