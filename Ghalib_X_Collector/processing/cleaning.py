"""Text cleaning and normalisation for Arabic and English posts."""
from __future__ import annotations

import html
import re
import unicodedata
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore

# Arabic letter ranges + Latin letters/digits + underscore (X hashtags accept all of these).
_TAG_CHARS = r"0-9A-Za-z_ء-غف-ي٠-٩ٮ-ۓەۺ-ۼÀ-ɏ"
HASHTAG_RE = re.compile(rf"(?:^|(?<=[^{_TAG_CHARS}&]))[#＃]([{_TAG_CHARS}]*[A-Za-z_ء-ۓ][{_TAG_CHARS}]*)")
MENTION_RE = re.compile(r"(?:^|(?<=[^0-9A-Za-z_@]))@([A-Za-z0-9_]{1,15})\b")
URL_RE = re.compile(r"https?://[^\s<>\"'‏‎]+", re.IGNORECASE)

ARABIC_DIACRITICS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭ]")
TATWEEL = "ـ"
ZERO_WIDTH = re.compile(r"[​-‍⁠﻿­]")
BIDI_MARKS = re.compile(r"[‎‏‪-‮⁦-⁩]")
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF⬀-⯿️]+"
)
ARABIC_INDIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def clean_text(text: str | None) -> str:
    """Readable cleaned text: entities decoded, invisible chars removed, spaces collapsed.

    Meaning is preserved (hashtags, mentions, emoji stay); only noise is removed.
    t.co short links are removed because the expanded URLs are kept in urls_json.
    """
    if not text:
        return ""
    t = html.unescape(str(text))
    t = unicodedata.normalize("NFKC", t)
    t = CONTROL.sub(" ", t)
    t = ZERO_WIDTH.sub("", t)
    t = BIDI_MARKS.sub("", t)
    t = t.replace(TATWEEL, "")
    t = re.sub(r"https?://t\.co/\w+", " ", t)
    t = re.sub(r"[ \t ]+", " ", t)
    t = re.sub(r"\s*\n\s*", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    # repeated punctuation like "!!!!!!" → "!!!"
    t = re.sub(r"([!?؟.،,])\1{3,}", r"\1\1\1", t)
    return t.strip()


def normalize_arabic(text: str) -> str:
    """Aggressive normalisation used for matching / analysis only (never stored as the text)."""
    t = ARABIC_DIACRITICS.sub("", text)
    t = t.replace(TATWEEL, "")
    t = re.sub("[إأآٱ]", "ا", t)
    t = t.replace("ى", "ي").replace("ؤ", "و").replace("ئ", "ي").replace("ة", "ه")
    t = t.translate(ARABIC_INDIC_DIGITS)
    return t


def analysis_text(text: str | None) -> str:
    """Lower-cased, normalised text without URLs, mentions, emoji or punctuation (for NLP)."""
    if not text:
        return ""
    t = clean_text(text)
    t = URL_RE.sub(" ", t)
    t = MENTION_RE.sub(" ", t)
    t = t.replace("#", " ").replace("_", " ")
    t = EMOJI_RE.sub(" ", t)
    t = normalize_arabic(t).lower()
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\b\d+\b", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def extract_hashtags(text: str | None) -> list[str]:
    if not text:
        return []
    seen, out = set(), []
    for m in HASHTAG_RE.finditer(html.unescape(text)):
        tag = m.group(1)
        if tag.lower() not in seen:
            seen.add(tag.lower())
            out.append(tag)
    return out


def extract_mentions(text: str | None) -> list[str]:
    if not text:
        return []
    seen, out = set(), []
    for m in MENTION_RE.finditer(text):
        name = m.group(1)
        if name.lower() not in seen:
            seen.add(name.lower())
            out.append(name)
    return out


def extract_urls(text: str | None) -> list[str]:
    if not text:
        return []
    return list(dict.fromkeys(u.rstrip(".,،)!?؟") for u in URL_RE.findall(text)))


def normalize_hashtag(tag: str) -> str:
    return normalize_arabic(tag.lstrip("#＃").strip()).lower()


def is_valid_url(url: str | None) -> bool:
    if not url:
        return False
    return bool(re.match(r"^https?://[A-Za-z0-9.\-]+\.[A-Za-z]{2,}(?::\d+)?(?:[/?#][^\s]*)?$", url.strip()))


# --------------------------------------------------------------- dates
def parse_x_datetime(value: str | None) -> str | None:
    """Parse X date formats to ISO-8601 UTC.

    Accepts the legacy format ("Wed Oct 10 20:19:24 +0000 2018"), ISO strings
    from ``<time datetime>`` and epoch milliseconds.
    """
    if value is None or value == "":
        return None
    try:
        s = str(value).strip()
        if s.isdigit():
            n = int(s)
            dt = datetime.fromtimestamp(n / 1000 if n > 10**11 else n, tz=timezone.utc)
        elif re.match(r"^\w{3} \w{3} \d{1,2} \d{2}:\d{2}:\d{2} [+-]\d{4} \d{4}$", s):
            dt = datetime.strptime(s, "%a %b %d %H:%M:%S %z %Y")
        elif "T" in s or re.match(r"^\d{4}-\d{2}-\d{2}", s):
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = parsedate_to_datetime(s)
        return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    except (ValueError, TypeError, OverflowError):
        return None


def local_date_time(iso_utc: str | None, tz_name: str = "UTC") -> tuple[str | None, str | None]:
    if not iso_utc:
        return None, None
    try:
        dt = datetime.fromisoformat(iso_utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if ZoneInfo is not None and tz_name:
            try:
                dt = dt.astimezone(ZoneInfo(tz_name))
            except Exception:
                dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M:%S")
    except ValueError:
        return None, None


def parse_count(text: str | None) -> int | None:
    """Parse the abbreviated counters shown in X's interface: "1,234", "12.5K", "3M", "١٫٢ ألف"."""
    if text is None:
        return None
    s = str(text).strip().translate(ARABIC_INDIC_DIGITS).replace("٫", ".").replace("٬", ",")
    if not s:
        return None
    m = re.search(r"(\d[\d,\.]*)\s*([KkMmBb]|ألف|آلاف|مليون|مليار|ك|م)?", s)
    if not m:
        return None
    num, unit = m.group(1), (m.group(2) or "").lower()
    if unit:
        num = num.replace(",", "")
    else:
        # "1,234" or "1.234" (thousand separators) with no unit
        if re.fullmatch(r"\d{1,3}([,\.]\d{3})+", num):
            num = num.replace(",", "").replace(".", "")
        else:
            num = num.replace(",", "")
    try:
        value = float(num)
    except ValueError:
        return None
    mult = {"k": 1e3, "ألف": 1e3, "آلاف": 1e3, "ك": 1e3, "m": 1e6, "مليون": 1e6, "م": 1e6, "b": 1e9, "مليار": 1e9}
    return int(round(value * mult.get(unit, 1)))
