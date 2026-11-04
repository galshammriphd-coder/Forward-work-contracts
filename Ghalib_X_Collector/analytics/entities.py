"""Named-entity recognition (local).

* ``rules`` engine (always available): Arabic trigger-word patterns
  (وزارة/هيئة… → government, شركة/جامعة… → organization, مؤتمر/معرض… → event,
  titles such as الأمير/الدكتور → person), a gazetteer of cities and countries,
  a product list, and English capitalised patterns. It is precise on these
  patterns but does not find entities without such cues.
* ``transformers`` engine (optional): a locally executed token-classification
  model (default Arabic: CAMeL-Lab/bert-base-arabic-camelbert-msa-ner,
  English/other: dslim/bert-base-NER).
"""
from __future__ import annotations

import re
from collections import Counter

import pandas as pd

import config
from database import db
from processing.cleaning import clean_text, URL_RE, MENTION_RE

TYPE_LABELS_AR = {
    "person": "أشخاص", "organization": "مؤسسات", "government": "جهات حكومية",
    "location": "مدن ومواقع", "product": "منتجات", "event": "أحداث", "misc": "أخرى",
}

_GOV = r"وزارة|وزارات|هيئة|الهيئة|أمانة|امانة|إمارة|امارة|مجلس|ديوان|رئاسة|النيابة|المحكمة|محكمة|بلدية|البلدية|الأمن العام|المديرية|مديرية|مكتب|صندوق|البنك المركزي|الحرس الوطني|الدفاع المدني|ministry of|authority|council of|department of"
_ORG = r"شركة|شركات|جامعة|الجامعة|بنك|مصرف|مؤسسة|جمعية|مستشفى|مركز|نادي|النادي|معهد|أكاديمية|اكاديمية|كلية|مجموعة|منظمة|اتحاد|المنظمة"
_EVENT = r"مؤتمر|معرض|منتدى|قمة|القمة|مهرجان|موسم|بطولة|كأس|ملتقى|هاكاثون|ماراثون|أسبوع|حفل|اليوم الوطني|يوم التأسيس"
_PERSON = r"الأمير|الامير|الأميرة|الملك|الشيخ|الشيخة|الدكتور|الدكتورة|د\.|المهندس|المهندسة|الأستاذ|الاستاذ|الأستاذة|معالي|سمو|صاحب السمو|الوزير|الرئيس|السفير|اللاعب|المدرب|الفنان|الفنانة"
_STOP = set("""في من على إلى الى عن مع و أو او ثم الذي التي الذين هذا هذه ذلك تلك قد لقد كان كانت يوم اليوم أمس امس غدا
عبر خلال حول بعد قبل منذ لدى عند هو هي بحضور بمشاركة برعاية بتنظيم تحت ضمن حيث وذلك كما أن ان إن لا ما
يقام تقام يعقد تعقد ينطلق تنطلق أعلن أعلنت اعلن اعلنت أكد أكدت قال قالت يستضيف تستضيف""".split())

CITIES = """
الرياض جدة مكة المكرمة المدينة المنورة الدمام الخبر الظهران الأحساء الاحساء الطائف تبوك أبها ابها
القصيم بريدة عنيزة حائل جازان نجران الباحة الجوف سكاكا عرعر ينبع العلا نيوم القطيف الجبيل خميس مشيط
السعودية المملكة الإمارات الامارات دبي أبوظبي ابوظبي الشارقة الكويت قطر الدوحة البحرين المنامة عمان مسقط
مصر القاهرة الإسكندرية الأردن عمّان لبنان بيروت سوريا دمشق العراق بغداد اليمن صنعاء عدن المغرب الرباط
الجزائر تونس ليبيا السودان فلسطين غزة القدس تركيا إسطنبول اسطنبول إيران طهران أمريكا امريكا واشنطن
نيويورك لندن بريطانيا باريس فرنسا ألمانيا المانيا برلين الصين بكين اليابان طوكيو الهند روسيا موسكو أوروبا
""".split()
CITIES_EN = """Riyadh Jeddah Makkah Mecca Medina Madinah Dammam Khobar Dhahran Taif Tabuk Abha NEOM AlUla Dubai
Abu Dhabi Doha Kuwait Bahrain Muscat Cairo Amman Beirut Baghdad London Paris Berlin Washington New York Tokyo
Beijing Saudi Arabia UAE Qatar Egypt Jordan Oman USA America China Japan India Europe""".split()
PRODUCTS = """ChatGPT GPT-4 GPT-5 Gemini Claude Copilot iPhone iPad MacBook Android Windows Tesla PlayStation Xbox
Netflix WhatsApp Instagram TikTok Snapchat YouTube Telegram Excel PowerPoint Python Bitcoin Ethereum
آيفون ايفون أندرويد اندرويد واتساب سناب تيك_توك يوتيوب بيتكوين""".split()

_AR_WORD = r"[ء-ي٠-٩A-Za-z0-9]+"


def _take_words(text: str, start: int, max_words: int = 3) -> str:
    words = []
    for m in re.finditer(_AR_WORD, text[start:]):
        w = m.group(0)
        if w in _STOP or len(words) >= max_words:
            break
        words.append(w)
        rest = text[start + m.end(): start + m.end() + 2]
        if re.match(r"\s*[،,.!?؟:\n]", rest):
            break
    return " ".join(words)


def _trim_person(name: str) -> str:
    words = name.split()
    # keep "محمد بن سلمان" chains, drop a trailing connector
    while words and words[-1] in ("بن", "بنت", "ابن", "آل", "ال", "عبد"):
        words.pop()
    return " ".join(words)


def rule_entities(text: str | None) -> list[tuple[str, str]]:
    if not text:
        return []
    t = MENTION_RE.sub(" ", URL_RE.sub(" ", clean_text(text))).replace("#", " ").replace("_", " ")
    found: list[tuple[str, str]] = []
    for pattern, etype, max_w in ((_GOV, "government", 3), (_ORG, "organization", 3), (_EVENT, "event", 3),
                                   (_PERSON, "person", 4)):
        for m in re.finditer(rf"(?<![\w])({pattern})\s+", t, flags=re.IGNORECASE):
            tail = _take_words(t, m.end(), max_w)
            if etype == "person":
                tail = _trim_person(tail)
            if tail:
                found.append((f"{m.group(1)} {tail}".strip(), etype))
    for city in CITIES:
        if re.search(rf"(?<![\w])(?:[وبلف]|في\s)?{re.escape(city)}(?![\w])", t):
            found.append((city, "location"))
    for city in CITIES_EN:
        if re.search(rf"\b{re.escape(city)}\b", t):
            found.append((city, "location"))
    for prod in PRODUCTS:
        p = prod.replace("_", " ")
        if re.search(rf"(?<![\w]){re.escape(p)}(?![\w])", t, flags=re.IGNORECASE):
            found.append((p, "product"))
    # English: "King Salman", "Dr. John Smith"
    for m in re.finditer(r"\b(?:King|Prince|Princess|Sheikh|Dr\.|Minister|President|Mr\.|Ms\.)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})", t):
        found.append((m.group(0), "person"))
    for m in re.finditer(r"\b([A-Z][A-Za-z&]+(?:\s+[A-Z][A-Za-z&]+){0,3})\s+(?:Inc|Ltd|LLC|Company|Corp|Group|University|Bank)\b", t):
        found.append((m.group(0), "organization"))
    seen, out = set(), []
    for ent, typ in found:
        k = (ent.lower(), typ)
        if k not in seen:
            seen.add(k)
            out.append((ent, typ))
    return out


_ner_pipes: dict[str, object] = {}
_HF_MAP = {"PER": "person", "PERS": "person", "ORG": "organization", "LOC": "location", "GPE": "location",
           "MISC": "misc", "PROD": "product", "EVENT": "event"}


def transformer_entities(texts: list[str], langs: list[str]) -> list[list[tuple[str, str]]]:
    from transformers import pipeline
    ar_model = db.get_setting("ner_model_ar", "CAMeL-Lab/bert-base-arabic-camelbert-msa-ner")
    en_model = db.get_setting("ner_model_multi", "dslim/bert-base-NER")
    out: list[list] = [[] for _ in texts]
    for i, (t, lang) in enumerate(zip(texts, langs)):
        name = ar_model if lang == "ar" else en_model
        if name not in _ner_pipes:
            _ner_pipes[name] = pipeline("ner", model=name, aggregation_strategy="simple",
                                        model_kwargs={"cache_dir": str(config.MODELS_DIR)})
        for e in _ner_pipes[name](t or ""):
            grp = str(e.get("entity_group", "MISC")).upper().replace("B-", "").replace("I-", "")
            word = str(e.get("word", "")).replace("##", "").strip()
            if len(word) > 1:
                out[i].append((word, _HF_MAP.get(grp, "misc")))
    return out


def analyze_entities(df: pd.DataFrame, engine: str = "rules", store: bool = True) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["post_id", "entity", "entity_type"])
    texts = df["clean_text"].fillna(df["raw_text"]).fillna("").tolist()
    if engine == "transformers":
        from analytics.sentiment import transformers_available
        if not transformers_available():
            raise RuntimeError("مكتبة Transformers غير مثبتة؛ استخدم محرك القواعد أو ثبّت requirements-ai.txt")
        results = transformer_entities(texts, df["lang"].fillna("und").tolist())
        model = "transformers"
    else:
        results = [rule_entities(t) for t in texts]
        model = "rules-v1"
    rows = [(pid, e, typ) for pid, ents in zip(df["post_id"], results) for e, typ in ents]
    out = pd.DataFrame(rows, columns=["post_id", "entity", "entity_type"])
    if store:
        now = db.utcnow()
        ids = list(df["post_id"])
        with db.get_conn() as c:
            for i in range(0, len(ids), 500):
                chunk = ids[i:i + 500]
                c.execute(f"DELETE FROM entity_results WHERE model = ? AND post_id IN ({','.join('?' * len(chunk))})",
                          (model, *chunk))
            c.executemany("INSERT INTO entity_results(post_id, entity, entity_type, model, analyzed_at) VALUES (?,?,?,?,?)",
                          [(p, e, t, model, now) for p, e, t in rows])
    return out


def top_entities(ents: pd.DataFrame, n: int = 15) -> pd.DataFrame:
    if ents.empty:
        return pd.DataFrame(columns=["entity", "entity_type", "posts"])
    c = Counter(zip(ents["entity"], ents["entity_type"]))
    return pd.DataFrame([(e, t, k) for (e, t), k in c.most_common(n * 3)], columns=["entity", "entity_type", "posts"])
