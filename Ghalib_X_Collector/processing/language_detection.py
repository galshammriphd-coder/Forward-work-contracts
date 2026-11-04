"""Lightweight, offline language identification (no external service).

The language reported by X (``lang``) is used when it is a real language code.
Otherwise the script mix of the text decides: Arabic script → "ar" (Persian/Urdu
specific letters → "fa"/"ur"), Latin → "en" or another Latin language from a small
stop-word profile, both scripts → the dominant one, nothing alphabetic → "und".
"""
from __future__ import annotations

import re

from processing.cleaning import EMOJI_RE, MENTION_RE, URL_RE, HASHTAG_RE

X_NON_LANGUAGE_CODES = {"und", "qme", "qht", "qst", "zxx", "qam", "qct", "art", ""}
_ARABIC = re.compile(r"[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]")
_LATIN = re.compile(r"[A-Za-zÀ-ɏ]")
_PERSIAN_ONLY = re.compile(r"[پچژگ]")
_URDU_ONLY = re.compile(r"[ٹڈڑںھےۓ]")

_LATIN_PROFILES = {
    "en": {"the", "and", "is", "to", "of", "in", "for", "with", "this", "that", "on", "are", "you", "it"},
    "fr": {"le", "la", "les", "et", "est", "des", "une", "pour", "dans", "avec", "que", "pas", "sur"},
    "es": {"el", "los", "las", "que", "por", "para", "una", "con", "del", "es", "como", "pero", "muy"},
    "de": {"der", "die", "das", "und", "ist", "nicht", "mit", "ein", "eine", "auf", "für", "ich", "zu"},
    "tr": {"ve", "bir", "bu", "için", "ile", "çok", "da", "de", "ne", "gibi", "olarak", "daha"},
    "id": {"yang", "dan", "di", "ini", "itu", "dengan", "untuk", "tidak", "dari", "ada", "akan"},
}

LANGUAGE_NAMES_AR = {
    "ar": "العربية", "en": "الإنجليزية", "fr": "الفرنسية", "es": "الإسبانية", "de": "الألمانية",
    "tr": "التركية", "id": "الإندونيسية", "fa": "الفارسية", "ur": "الأردية", "hi": "الهندية",
    "ja": "اليابانية", "ko": "الكورية", "zh": "الصينية", "ru": "الروسية", "pt": "البرتغالية",
    "it": "الإيطالية", "und": "غير محددة", "mixed": "مختلطة",
}


def _strip_noise(text: str) -> str:
    t = URL_RE.sub(" ", text)
    t = MENTION_RE.sub(" ", t)
    t = HASHTAG_RE.sub(lambda m: " " + m.group(1).replace("_", " ") + " ", t)
    return EMOJI_RE.sub(" ", t)


def detect_language(text: str | None, x_lang: str | None = None) -> str:
    if x_lang and x_lang.lower() not in X_NON_LANGUAGE_CODES:
        return x_lang.lower()
    if not text:
        return "und"
    t = _strip_noise(text)
    ar = len(_ARABIC.findall(t))
    la = len(_LATIN.findall(t))
    if re.search(r"[぀-ヿ]", t):
        return "ja"
    if re.search(r"[가-힯]", t):
        return "ko"
    if re.search(r"[一-鿿]", t):
        return "zh"
    if re.search(r"[Ѐ-ӿ]", t):
        return "ru"
    if re.search(r"[ऀ-ॿ]", t):
        return "hi"
    total = ar + la
    if total < 2:
        return "und"
    if ar and la and min(ar, la) / total >= 0.35:
        return "mixed"
    if ar >= la:
        if _URDU_ONLY.search(t):
            return "ur"
        if _PERSIAN_ONLY.search(t) and len(_PERSIAN_ONLY.findall(t)) >= 2:
            return "fa"
        return "ar"
    words = set(re.findall(r"[a-zà-ÿğüşöçı]+", t.lower()))
    best, best_hits = "en", 0
    for lang, stops in _LATIN_PROFILES.items():
        hits = len(words & stops)
        if hits > best_hits:
            best, best_hits = lang, hits
    return best


def language_name(code: str | None) -> str:
    return LANGUAGE_NAMES_AR.get((code or "und").lower(), code or "غير محددة")
