"""Separate, encrypted file storage. Originals are write-once and never modified."""
from __future__ import annotations

import hashlib
import os
import shutil

from .config import DATA_DIR
from .security import decrypt, encrypt


def project_dir(project_id: str):
    d = DATA_DIR / "projects" / project_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_original(project_id: str, version: int, raw: bytes) -> tuple[str, str]:
    sha = hashlib.sha256(raw).hexdigest()
    path = project_dir(project_id) / f"original_v{version}_{sha[:12]}.enc"
    path.write_bytes(encrypt(raw))
    os.chmod(path, 0o440)  # read-only: the original is immutable
    return str(path), sha


def load_original(path: str, expected_sha: str | None = None) -> bytes:
    with open(path, "rb") as fh:
        raw = decrypt(fh.read())
    if expected_sha and hashlib.sha256(raw).hexdigest() != expected_sha:
        raise ValueError("Integrity check failed: stored original does not match its SHA-256 hash.")
    return raw


def delete_project_files(project_id: str) -> None:
    d = DATA_DIR / "projects" / project_id
    if d.exists():
        for p in d.iterdir():
            os.chmod(p, 0o600)
        shutil.rmtree(d)
