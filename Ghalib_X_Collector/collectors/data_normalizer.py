"""Normalises parsed records before they are stored (uniform types and formats)."""
from __future__ import annotations

from database.models import Account, Post
from processing.cleaning import parse_x_datetime


def _uniq(items, key=lambda x: str(x).lower()):
    seen, out = set(), []
    for it in items or []:
        if it in (None, ""):
            continue
        k = key(it)
        if k not in seen:
            seen.add(k)
            out.append(it)
    return out


def normalize_post(p: Post) -> Post:
    p.post_id = str(p.post_id).strip()
    p.raw_text = (p.raw_text or "").replace("\r\n", "\n")
    if p.username:
        p.username = p.username.strip().lstrip("@")
    if p.display_name:
        p.display_name = p.display_name.strip()
    if p.published_at:
        p.published_at = parse_x_datetime(p.published_at) or p.published_at
    if p.language:
        p.language = p.language.strip().lower()
    p.hashtags = _uniq([str(h).lstrip("#＃") for h in p.hashtags])
    p.mentions = _uniq([str(m).lstrip("@") for m in p.mentions])
    p.urls = _uniq(p.urls, key=str)
    p.media = [m for m in (p.media or []) if isinstance(m, dict)]
    for f in ("replies_count", "reposts_count", "likes_count", "quotes_count", "bookmarks_count", "views_count"):
        v = getattr(p, f)
        if v is not None:
            try:
                v = int(v)
                setattr(p, f, v if v >= 0 else None)
            except (TypeError, ValueError):
                setattr(p, f, None)
    if p.post_type not in ("original", "reply", "quote", "repost"):
        p.post_type = "original"
    return p


def normalize_account(a: Account) -> Account:
    a.username = a.username.strip().lstrip("@")
    if a.display_name:
        a.display_name = a.display_name.strip()
    if a.description:
        a.description = a.description.strip()
    return a
