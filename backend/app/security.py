"""Password hashing, bearer tokens and at-rest encryption."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet

from .config import DATA_DIR, ENCRYPTION_KEY, TOKEN_TTL_HOURS

_ITER = 390_000


def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, _ITER)
    return f"pbkdf2_sha256${_ITER}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, it, salt, dk = stored.split("$")
        new = hashlib.pbkdf2_hmac("sha256", pw.encode(), base64.b64decode(salt), int(it))
        return hmac.compare_digest(new, base64.b64decode(dk))
    except ValueError:
        return False


def new_token() -> tuple[str, str, datetime]:
    token = secrets.token_urlsafe(32)
    return token, token_hash(token), datetime.now(timezone.utc) + timedelta(hours=TOKEN_TTL_HOURS)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _fernet() -> Fernet:
    key = ENCRYPTION_KEY
    if not key:
        key_file = DATA_DIR / "encryption.key"
        if not key_file.exists():
            key_file.write_bytes(Fernet.generate_key())
            os.chmod(key_file, 0o600)
        key = key_file.read_bytes().decode()
    return Fernet(key)


def encrypt(data: bytes) -> bytes:
    return _fernet().encrypt(data)


def decrypt(data: bytes) -> bytes:
    return _fernet().decrypt(data)
