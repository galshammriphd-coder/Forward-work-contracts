"""Builds X search queries with X's own advanced-search operators.

The operators used here are the ones X's web search box understands:
``"exact phrase"``, ``-exclude``, ``(a OR b)``, ``#tag``, ``from:``, ``to:``, ``@user``,
``lang:``, ``since:``, ``until:``, ``min_faves:``, ``min_retweets:``, ``min_replies:``,
``filter:replies``, ``filter:media``, ``filter:images``, ``filter:videos``,
``filter:links``, ``filter:quote``. AND is implicit in X (a space), so a typed
``AND`` is converted to a space; ``NOT word`` becomes ``-word``.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from urllib.parse import quote

from processing.cleaning import normalize_hashtag

POST_TYPE_FILTERS = {
    "any": "",
    "original": "-filter:replies -filter:quote",
    "no_replies": "-filter:replies",
    "replies": "filter:replies",
    "quotes": "filter:quote",
    "media": "filter:media",
    "images": "filter:images",
    "videos": "filter:videos",
    "links": "filter:links",
}
POST_TYPE_LABELS_AR = {
    "any": "كل المنشورات",
    "original": "منشورات أصلية فقط",
    "no_replies": "استبعاد الردود",
    "replies": "الردود فقط",
    "quotes": "الاقتباسات فقط",
    "media": "تحتوي وسائط",
    "images": "تحتوي صوراً",
    "videos": "تحتوي فيديو",
    "links": "تحتوي روابط",
}
SORT_LABELS_AR = {"live": "الأحدث", "top": "الأكثر تفاعلاً (الأبرز)"}

_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{1,15}$")


@dataclass
class SearchParams:
    search_type: str = "keyword"              # hashtag | user | keyword | advanced
    keywords: str = ""                        # free query (supports "phrases", AND, OR, NOT, -word)
    exact_phrase: str = ""
    any_words: str = ""                       # space separated → (a OR b)
    exclude_words: str = ""                   # space separated → -a -b
    hashtags: list[str] = field(default_factory=list)
    hashtag_mode: str = "any"                 # any (OR) | all (AND) | separate (one query per tag)
    usernames: list[str] = field(default_factory=list)
    user_mode: str = "separate"               # separate (one query per account) | combined
    to_user: str = ""
    mention_user: str = ""
    lang: str = ""                            # "", ar, en, ...
    since: str | None = None                  # YYYY-MM-DD (inclusive)
    until: str | None = None                  # YYYY-MM-DD (inclusive in the UI; X's until is exclusive)
    post_type: str = "any"
    min_likes: int = 0
    min_reposts: int = 0
    min_replies: int = 0
    sort: str = "live"                        # live | top
    collect_profiles: bool = True             # open profile pages for account info (user search)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "SearchParams":
        known = {k: v for k, v in (d or {}).items() if k in cls.__dataclass_fields__}
        return cls(**known)


def split_list(value: str | list | None) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        items = value
    else:
        items = re.split(r"[,\n،;]+|\s+(?=[#@])", value)
    out = []
    for it in items:
        it = str(it).strip()
        if it and it not in out:
            out.append(it)
    return out


def clean_hashtag(tag: str) -> str:
    t = tag.strip().lstrip("#＃").strip()
    t = re.sub(r"\s+", "_", t)
    return t


def clean_username(name: str) -> str:
    n = name.strip()
    n = re.sub(r"^https?://(www\.)?(x|twitter)\.com/", "", n, flags=re.I).split("/")[0].split("?")[0]
    n = n.lstrip("@").strip()
    if not _USERNAME_RE.match(n):
        raise ValueError(f"اسم مستخدم غير صالح: {name!r} (المسموح: حروف إنجليزية وأرقام و _ حتى 15 حرفاً)")
    return n


def normalize_keyword_query(text: str) -> str:
    """Translate a user-friendly boolean query to X syntax, keeping quoted phrases intact."""
    if not text or not text.strip():
        return ""
    tokens = re.findall(r'"[^"]*"|\(|\)|\S+', text.strip())
    out: list[str] = []
    negate_next = False
    for tok in tokens:
        up = tok.upper()
        if up in ("AND", "&&", "و_أيضا"):
            continue
        if up in ("OR", "||", "أو"):
            out.append("OR")
            continue
        if up in ("NOT", "!", "ليس"):
            negate_next = True
            continue
        if negate_next:
            tok = "-" + tok.lstrip("-")
            negate_next = False
        out.append(tok)
    # Remove dangling ORs
    while out and out[0] == "OR":
        out.pop(0)
    while out and out[-1] == "OR":
        out.pop()
    q = " ".join(out)
    q = re.sub(r"\(\s+", "(", q)
    q = re.sub(r"\s+\)", ")", q)
    return q


def _date(value) -> date | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


def _common_filters(p: SearchParams) -> list[str]:
    parts: list[str] = []
    if p.exact_phrase.strip():
        parts.append(f'"{p.exact_phrase.strip().strip(chr(34))}"')
    anyw = [w for w in re.split(r"[\s,،]+", p.any_words.strip()) if w]
    if len(anyw) == 1:
        parts.append(anyw[0])
    elif anyw:
        parts.append("(" + " OR ".join(anyw) + ")")
    for w in re.split(r"[\s,،]+", p.exclude_words.strip()):
        if w:
            parts.append("-" + w.lstrip("-"))
    if p.to_user.strip():
        parts.append("to:" + clean_username(p.to_user))
    if p.mention_user.strip():
        parts.append("@" + clean_username(p.mention_user))
    if p.lang.strip():
        parts.append("lang:" + p.lang.strip().lower())
    flt = POST_TYPE_FILTERS.get(p.post_type, "")
    if flt:
        parts.append(flt)
    if p.min_likes:
        parts.append(f"min_faves:{int(p.min_likes)}")
    if p.min_reposts:
        parts.append(f"min_retweets:{int(p.min_reposts)}")
    if p.min_replies:
        parts.append(f"min_replies:{int(p.min_replies)}")
    s, u = _date(p.since), _date(p.until)
    if s and u and s > u:
        raise ValueError("تاريخ البداية بعد تاريخ النهاية")
    if s:
        parts.append(f"since:{s.isoformat()}")
    if u:
        # X's until: is exclusive; the UI end date is inclusive.
        parts.append(f"until:{(u + timedelta(days=1)).isoformat()}")
    return parts


def build_queries(p: SearchParams) -> list[str]:
    """Return the list of X queries to execute for these parameters."""
    common = _common_filters(p)
    kw = normalize_keyword_query(p.keywords)
    tags = [clean_hashtag(t) for t in split_list(p.hashtags) if clean_hashtag(t)]
    users = [clean_username(u) for u in split_list(p.usernames)]
    queries: list[str] = []

    def join(*parts) -> str:
        return re.sub(r"\s+", " ", " ".join(x for x in parts if x)).strip()

    if p.search_type == "hashtag":
        if not tags:
            raise ValueError("أدخل هاشتاقاً واحداً على الأقل")
        if p.hashtag_mode == "separate":
            queries = [join(f"#{t}", kw, *common) for t in tags]
        elif p.hashtag_mode == "all":
            queries = [join(*[f"#{t}" for t in tags], kw, *common)]
        else:
            tag_q = f"#{tags[0]}" if len(tags) == 1 else "(" + " OR ".join(f"#{t}" for t in tags) + ")"
            queries = [join(tag_q, kw, *common)]
    elif p.search_type == "user":
        if not users:
            raise ValueError("أدخل اسم مستخدم واحداً على الأقل")
        if p.user_mode == "combined" and len(users) > 1:
            queries = [join("(" + " OR ".join(f"from:{u}" for u in users) + ")", kw, *common)]
        else:
            queries = [join(f"from:{u}", kw, *common) for u in users]
    elif p.search_type in ("keyword", "advanced"):
        tag_part = ""
        if tags:
            tag_part = f"#{tags[0]}" if len(tags) == 1 else "(" + " OR ".join(f"#{t}" for t in tags) + ")"
        user_part = ""
        if users:
            user_part = f"from:{users[0]}" if len(users) == 1 else "(" + " OR ".join(f"from:{u}" for u in users) + ")"
        q = join(kw, tag_part, user_part, *common)
        if p.search_type == "keyword" and not (kw or p.exact_phrase.strip() or p.any_words.strip()):
            raise ValueError("أدخل كلمة أو عبارة للبحث")
        queries = [q]
    else:
        raise ValueError(f"نوع بحث غير معروف: {p.search_type}")

    queries = [q for q in queries if q]
    # A query made only of negative terms / filters returns nothing on X.
    for q in queries:
        positive = [t for t in re.findall(r'"[^"]*"|\S+', q) if not t.startswith("-") and ":" not in t and t not in ("OR", "(", ")")]
        if not positive and "from:" not in q and "#" not in q and "@" not in q:
            raise ValueError(f"الاستعلام لا يحتوي على كلمات بحث موجبة: {q}")
    if any(len(q) > 500 for q in queries):
        raise ValueError("الاستعلام أطول من الحد المسموح في X (500 حرف)")
    return queries


def search_url(query: str, sort: str = "live") -> str:
    url = f"https://x.com/search?q={quote(query, safe='')}&src=typed_query"
    if sort == "live":
        url += "&f=live"
    return url


def describe(p: SearchParams) -> str:
    """Short human-readable description for job names / reports."""
    if p.search_type == "hashtag":
        return " ".join(f"#{clean_hashtag(t)}" for t in split_list(p.hashtags))
    if p.search_type == "user":
        return " ".join(f"@{u.lstrip('@')}" for u in split_list(p.usernames))
    return (p.keywords or p.exact_phrase or p.any_words or "").strip()


def related_hashtag_key(tag: str) -> str:
    return normalize_hashtag(tag)
