"""Runtime configuration. Everything is overridable by environment variables."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("PMO_DATA_DIR", BASE_DIR / "data"))
STORAGE_DIR = DATA_DIR / "documents"
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DATA_DIR / 'pmo.db'}")
DEV_SECRET = "dev-only-secret-change-me-before-any-real-deployment"
SECRET_KEY = os.environ.get("PMO_SECRET_KEY", DEV_SECRET)
TOKEN_TTL_MINUTES = int(os.environ.get("PMO_TOKEN_TTL_MINUTES", "480"))
MAX_UPLOAD_MB = int(os.environ.get("PMO_MAX_UPLOAD_MB", "40"))
SEED_DEMO = os.environ.get("PMO_SEED_DEMO", "1") == "1"
SCHEDULER_ENABLED = os.environ.get("PMO_SCHEDULER", "1") == "1"
# Key for an optional LLM endpoint. Unused unless Settings > AI selects an endpoint.
LLM_API_KEY = os.environ.get("PMO_LLM_API_KEY", "")
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".txt", ".md", ".csv"}

DEFAULT_SETTINGS = {
    "org": {"name_ar": "الهيئة النموذجية", "name_en": "Model Authority", "currency": "SAR",
            "numerals": "latn", "calendar": "gregory"},
    "risk_thresholds": {"low": 4, "moderate": 9, "high": 14},  # upper bounds; above "high" = critical
    "work_calendar": {"weekend": [4, 5], "holidays": []},  # Python weekday(): Fri=4, Sat=5
    # LLM: "local" = built-in extractive engine. "endpoint" = any OpenAI-compatible chat API
    # (Ollama, vLLM, LM Studio on-premises, or a cloud service once the organisation consents).
    "ai": {"mode": "local", "endpoint_url": "", "endpoint_model": "", "endpoint_is_external": True,
           "external_consent": False, "allow_confidential_external": False, "embedding_model": "local-hash-v1"},
    "evm": {"spi_warning": 0.9, "spi_critical": 0.8, "cpi_warning": 0.9, "cpi_critical": 0.8},
}
