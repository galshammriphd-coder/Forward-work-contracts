"""Turns what the X web client receives into unified Post / Account records.

Sources handled:
* GraphQL JSON received by the logged-in browser page (SearchTimeline, UserTweets,
  UserByScreenName, TweetDetail, ...). The walker is schema-tolerant: it looks
  for ``Tweet`` and ``User`` objects anywhere in the payload, and supports both
  the older ``legacy`` user layout and the newer ``core``/``avatar`` layout.
* Items scraped from the rendered page (DOM fallback), see ``browser.dom_extractor``.
* Files: HAR captures saved from a browser, raw GraphQL JSON, or this app's own
  JSON / CSV exports (re-import / restore between machines).
"""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any, Iterator

from database.models import Account, Post
from processing.cleaning import (
    extract_hashtags, extract_mentions, extract_urls, parse_count, parse_x_datetime,
)

_SKIP_KEYS = {"quoted_status_result", "retweeted_status_result"}


def _to_int(v: Any) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return parse_count(str(v))


# --------------------------------------------------------------- users
def parse_user(obj: dict) -> Account | None:
    """Parse a GraphQL ``User`` result (old and new layouts)."""
    if not isinstance(obj, dict):
        return None
    if obj.get("__typename") == "UserUnavailable":
        return None
    legacy = obj.get("legacy") or {}
    core = obj.get("core") or {}
    screen = core.get("screen_name") or legacy.get("screen_name")
    if not screen:
        return None
    loc = obj.get("location")
    location = loc.get("location") if isinstance(loc, dict) else legacy.get("location")
    avatar = (obj.get("avatar") or {}).get("image_url") or legacy.get("profile_image_url_https")
    verified = (obj.get("verification") or {}).get("verified")
    if verified is None:
        verified = legacy.get("verified")
    if obj.get("is_blue_verified"):
        verified = True
    desc = legacy.get("description")
    if desc is None:
        desc = ((obj.get("profile_bio") or {}).get("description"))
    created = core.get("created_at") or legacy.get("created_at")
    return Account(
        username=screen,
        user_id=obj.get("rest_id"),
        display_name=core.get("name") or legacy.get("name"),
        description=desc,
        location=location or None,
        followers_count=_to_int(legacy.get("followers_count")),
        following_count=_to_int(legacy.get("friends_count")),
        statuses_count=_to_int(legacy.get("statuses_count")),
        account_created_at=parse_x_datetime(created) if created else None,
        verified=None if verified is None else bool(verified),
        profile_image_url=avatar,
        raw=obj,
    )


# -------------------------------------------------------------- tweets
def _unwrap(obj: dict | None) -> dict | None:
    if not isinstance(obj, dict):
        return None
    if obj.get("__typename") == "TweetWithVisibilityResults" and isinstance(obj.get("tweet"), dict):
        return obj["tweet"]
    if "result" in obj and isinstance(obj["result"], dict) and len(obj) <= 2:
        return _unwrap(obj["result"])
    return obj


def parse_tweet(obj: dict) -> tuple[Post | None, Account | None]:
    tw = _unwrap(obj)
    if not tw or tw.get("__typename") not in (None, "Tweet") or "legacy" not in tw:
        return None, None
    legacy = tw.get("legacy") or {}
    pid = str(tw.get("rest_id") or legacy.get("id_str") or "")
    if not pid.isdigit():
        return None, None
    user_res = _unwrap(((tw.get("core") or {}).get("user_results") or {}).get("result"))
    account = parse_user(user_res) if user_res else None
    screen = account.username if account else None

    text = legacy.get("full_text") or legacy.get("text") or ""
    note = (((tw.get("note_tweet") or {}).get("note_tweet_results") or {}).get("result") or {})
    entities = legacy.get("entities") or {}
    if note.get("text"):
        text = note["text"]
        entities = {**entities, **(note.get("entity_set") or {})}

    post_type = "original"
    rt = _unwrap((legacy.get("retweeted_status_result") or {}).get("result"))
    if rt and rt.get("legacy"):
        post_type = "repost"
        inner, _ = parse_tweet(rt)
        if inner and inner.raw_text:
            text = f"RT @{inner.username}: {inner.raw_text}"
    elif legacy.get("in_reply_to_status_id_str"):
        post_type = "reply"
    elif legacy.get("is_quote_status"):
        post_type = "quote"

    hashtags = [h.get("text") for h in entities.get("hashtags", []) if h.get("text")] or extract_hashtags(text)
    mentions = [m.get("screen_name") for m in entities.get("user_mentions", []) if m.get("screen_name")] or extract_mentions(text)
    urls = [u.get("expanded_url") or u.get("url") for u in entities.get("urls", []) if (u.get("expanded_url") or u.get("url"))]
    if not urls:
        urls = [u for u in extract_urls(text) if "t.co/" not in u]
    media = []
    for m in (legacy.get("extended_entities") or {}).get("media", []) or entities.get("media", []):
        item = {"type": m.get("type"), "url": m.get("media_url_https"), "expanded_url": m.get("expanded_url")}
        variants = ((m.get("video_info") or {}).get("variants") or [])
        mp4 = [v for v in variants if v.get("content_type") == "video/mp4"]
        if mp4:
            item["video_url"] = max(mp4, key=lambda v: v.get("bitrate") or 0).get("url")
        media.append(item)

    quoted_id = legacy.get("quoted_status_id_str")
    if not quoted_id:
        q = _unwrap((tw.get("quoted_status_result") or {}).get("result"))
        quoted_id = (q or {}).get("rest_id")
    post = Post(
        post_id=pid,
        raw_text=text,
        username=screen,
        display_name=account.display_name if account else None,
        profile_url=f"https://x.com/{screen}" if screen else None,
        post_url=f"https://x.com/{screen}/status/{pid}" if screen else f"https://x.com/i/status/{pid}",
        published_at=parse_x_datetime(legacy.get("created_at")),
        language=legacy.get("lang"),
        post_type=post_type,
        hashtags=hashtags,
        mentions=mentions,
        urls=urls,
        media=media,
        replies_count=_to_int(legacy.get("reply_count")),
        reposts_count=_to_int(legacy.get("retweet_count")),
        likes_count=_to_int(legacy.get("favorite_count")),
        quotes_count=_to_int(legacy.get("quote_count")),
        bookmarks_count=_to_int(legacy.get("bookmark_count")),
        views_count=_to_int((tw.get("views") or {}).get("count")),
        conversation_id=legacy.get("conversation_id_str"),
        in_reply_to_post_id=legacy.get("in_reply_to_status_id_str"),
        in_reply_to_user=legacy.get("in_reply_to_screen_name"),
        quoted_post_id=quoted_id,
        source="graphql",
        raw=tw,
    )
    return post, account


def _walk(node: Any, skip_nested: bool = True) -> Iterator[dict]:
    stack = [node]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            yield cur
            for k, v in cur.items():
                if skip_nested and k in _SKIP_KEYS:
                    continue
                if isinstance(v, (dict, list)):
                    stack.append(v)
        elif isinstance(cur, list):
            stack.extend(reversed(cur))


def parse_graphql_payload(payload: Any) -> tuple[list[Post], list[Account]]:
    """Extract every top-level post and every user object from a GraphQL response."""
    posts: dict[str, Post] = {}
    accounts: dict[str, Account] = {}
    profile_user = None
    if isinstance(payload, dict):
        u = ((payload.get("data") or {}).get("user") or {}).get("result")
        if isinstance(u, dict) and u.get("__typename") == "User":
            profile_user = u
    for d in _walk(payload):
        tn = d.get("__typename")
        if tn in ("Tweet", "TweetWithVisibilityResults"):
            p, a = parse_tweet(d)
            if p and p.post_id not in posts:
                posts[p.post_id] = p
            if a:
                accounts.setdefault(a.username.lower(), a)
        elif tn == "User":
            a = parse_user(d)
            if a:
                if d is profile_user:
                    a.is_profile = True
                    accounts[a.username.lower()] = a
                else:
                    accounts.setdefault(a.username.lower(), a)
    return list(posts.values()), list(accounts.values())


# ----------------------------------------------------------------- DOM
def post_from_dom(item: dict) -> Post | None:
    """Convert an item produced by ``browser.dom_extractor.EXTRACT_JS``."""
    pid = str(item.get("post_id") or "")
    if not pid.isdigit():
        return None
    user = (item.get("username") or "").lstrip("@") or None
    text = item.get("text") or ""
    return Post(
        post_id=pid,
        raw_text=text,
        username=user,
        display_name=item.get("display_name"),
        profile_url=f"https://x.com/{user}" if user else None,
        post_url=item.get("post_url") or (f"https://x.com/{user}/status/{pid}" if user else None),
        published_at=parse_x_datetime(item.get("datetime")),
        language=item.get("lang"),
        post_type=item.get("post_type") or "original",
        hashtags=extract_hashtags(text),
        mentions=extract_mentions(text),
        urls=[u for u in (item.get("links") or []) if u and "t.co/" not in u],
        media=[{"type": "photo", "url": u} for u in (item.get("images") or [])]
        + ([{"type": "video"}] if item.get("has_video") else []),
        replies_count=parse_count(item.get("replies")),
        reposts_count=parse_count(item.get("reposts")),
        likes_count=parse_count(item.get("likes")),
        views_count=parse_count(item.get("views")),
        source="dom",
        raw=item,
    )


# ---------------------------------------------------------------- files
_CSV_ALIASES = {
    "post_id": ["post_id", "Post ID", "id", "معرف المنشور"],
    "raw_text": ["raw_text", "Post Text", "text", "clean_text", "نص المنشور"],
    "username": ["username", "Username", "اسم المستخدم"],
    "display_name": ["display_name", "Display Name", "الاسم الظاهر"],
    "post_url": ["post_url", "Post URL", "رابط المنشور"],
    "published_at": ["published_at", "Published At", "Published Date", "تاريخ النشر"],
    "language": ["language", "Language", "اللغة"],
    "replies_count": ["replies_count", "Replies Count", "الردود"],
    "reposts_count": ["reposts_count", "Reposts Count", "إعادة النشر"],
    "likes_count": ["likes_count", "Likes Count", "الإعجابات"],
    "views_count": ["views_count", "Views Count", "المشاهدات"],
}


def _post_from_flat(d: dict) -> Post | None:
    def g(field):
        for alias in _CSV_ALIASES.get(field, [field]):
            if alias in d and d[alias] not in (None, ""):
                return d[alias]
        return None

    pid = str(g("post_id") or "").split(".")[0]
    if not pid.isdigit():
        return None
    text = str(g("raw_text") or "")
    pub = g("published_at")
    if pub and "Published Time" in d and len(str(pub)) == 10:
        pub = f"{pub}T{d['Published Time']}"

    def lst(key):
        v = d.get(key)
        if isinstance(v, list):
            return v
        if isinstance(v, str) and v.strip().startswith("["):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return []
        return None

    return Post(
        post_id=pid,
        raw_text=text,
        username=(str(g("username")).lstrip("@") if g("username") else None),
        display_name=g("display_name"),
        post_url=g("post_url"),
        published_at=parse_x_datetime(pub),
        language=g("language"),
        post_type=d.get("post_type") or "original",
        hashtags=lst("hashtags") or lst("hashtags_json") or extract_hashtags(text),
        mentions=lst("mentions") or lst("mentions_json") or extract_mentions(text),
        urls=lst("urls") or lst("urls_json") or [],
        media=lst("media") or lst("media_json") or [],
        replies_count=_to_int(g("replies_count")),
        reposts_count=_to_int(g("reposts_count")),
        likes_count=_to_int(g("likes_count")),
        views_count=_to_int(g("views_count")),
        source="import",
        raw=d,
    )


def parse_file(name: str, data: bytes) -> tuple[list[Post], list[Account], str]:
    """Parse an uploaded file. Returns (posts, accounts, detected_format)."""
    suffix = Path(name).suffix.lower()
    text = data.decode("utf-8-sig", errors="replace")
    if suffix == ".csv":
        rows = list(csv.DictReader(io.StringIO(text)))
        posts = [p for p in (_post_from_flat(r) for r in rows) if p]
        return posts, [], "csv"
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        # JSON lines
        obj = [json.loads(line) for line in text.splitlines() if line.strip()]
    if isinstance(obj, dict) and "log" in obj and "entries" in (obj.get("log") or {}):
        posts, accounts = [], []
        for e in obj["log"]["entries"]:
            url = (e.get("request") or {}).get("url", "")
            content = ((e.get("response") or {}).get("content") or {})
            body = content.get("text")
            if "/graphql/" not in url or not body:
                continue
            if content.get("encoding") == "base64":
                import base64
                body = base64.b64decode(body).decode("utf-8", errors="replace")
            try:
                p, a = parse_graphql_payload(json.loads(body))
            except json.JSONDecodeError:
                continue
            posts.extend(p)
            accounts.extend(a)
        return posts, accounts, "har"
    # Our own exports: {"posts": [...]} or [ {post_id: ...}, ...]
    records = obj.get("posts") if isinstance(obj, dict) and isinstance(obj.get("posts"), list) else obj
    if isinstance(records, list) and records and isinstance(records[0], dict) and (
        "post_id" in records[0] or "Post ID" in records[0]
    ):
        return [p for p in (_post_from_flat(r) for r in records) if p], [], "export_json"
    posts, accounts = parse_graphql_payload(obj)
    return posts, accounts, "graphql_json"
