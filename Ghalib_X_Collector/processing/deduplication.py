"""Duplicate handling.

1. Exact duplicates (same X post id) are prevented at insert time by the primary
   key; ``collectors`` count them as duplicates for the job statistics.
2. Content duplicates (different post ids carrying the same normalised text, e.g.
   copy-paste campaigns) are *flagged*, never deleted, so the original data stays
   intact. Analyses can exclude them with ``posts.validation_notes``.
"""
from __future__ import annotations

import hashlib
from typing import Iterable

from processing.cleaning import analysis_text


def text_fingerprint(text: str | None) -> str | None:
    norm = analysis_text(text)
    if len(norm) < 15:          # very short texts ("شكرا", "😂") are not campaign duplicates
        return None
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()


def dedupe_batch(posts: Iterable, key=lambda p: p.post_id) -> tuple[list, int]:
    """Remove repeated ids inside one capture batch; returns (unique, removed)."""
    seen, out, removed = set(), [], 0
    for p in posts:
        k = key(p)
        if k in seen:
            removed += 1
            continue
        seen.add(k)
        out.append(p)
    return out, removed


def find_content_duplicates(rows: list[dict]) -> dict[str, str]:
    """Map post_id → id of the earliest post with the same normalised text."""
    first: dict[str, tuple[str, str]] = {}
    dup: dict[str, str] = {}
    for r in sorted(rows, key=lambda r: (r.get("published_at") or "", r["post_id"])):
        fp = text_fingerprint(r.get("raw_text"))
        if not fp:
            continue
        if fp in first:
            dup[r["post_id"]] = first[fp][0]
        else:
            first[fp] = (r["post_id"], r.get("published_at") or "")
    return dup
