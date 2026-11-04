"""Sentiment analysis — runs locally, nothing is sent to an external service.

Two engines:
* ``lexicon``  – built-in Arabic (MSA + Gulf dialect) / English lexicon with
  negation and emoji handling. Always available, transparent, fast. It is a
  baseline: it misses sarcasm and context, and its accuracy is lower than a
  trained model. Supports the *mixed* class (positive and negative cues together).
* ``transformers`` – a locally executed Hugging Face model (downloaded once to
  ``data/models`` and then used offline). Default models are configurable in
  Settings: Arabic → CAMeL-Lab/bert-base-arabic-camelbert-da-sentiment,
  other languages → cardiffnlp/twitter-xlm-roberta-base-sentiment.
"""
from __future__ import annotations

import json
import re

import pandas as pd

import config
from database import db
from processing.cleaning import analysis_text, normalize_arabic

LABELS_AR = {"positive": "إيجابي", "negative": "سلبي", "neutral": "محايد", "mixed": "مختلط"}

_POS_AR = """
جميل رائع ممتاز مذهل نجاح ناجح نجح فخر فخور سعيد سعاده فرح فرحه مبروك تهانينا شكرا شكر
ممتن امتنان احسنت احسنتم ابداع مبدع متميز تميز افضل احسن جيد طيب حلو زين كفو مبهر عظيم
تقدم تطور انجاز انجازات ريادي رياده قوي قوه امل متفائل تفاؤل ايجابي ايجابيه دعم داعم
حب احب احبك محبه رائعه جميله ممتازه ناجحه مفيد مفيده نافع فرصه فرص ازدهار نمو مزدهر
مميز مميزه استثنائي فوز فاز يستاهل يستحق تستاهل مشكور مشكورين يعطيك العافيه بارك مبارك
اعجبني يعجبني افتخر نفتخر سهل سهوله سريع امان امن موفق توفيق تحقيق حقق ملهم الهام
""".split()
_NEG_AR = """
سيء سيئ سيئه سوء فشل فاشل فشلت خساره خسر خسائر حزين حزن مؤسف للاسف اسف كارثه كارثي
مشكله مشاكل ازمه ازمات ضعيف ضعف تراجع انخفاض سلبي سلبيه ظلم فساد فاسد غضب غاضب زعل
كره اكره مقرف تافه سخيف خطير خطر تهديد مخيف خوف قلق قلقه ممل مزعج ازعاج احباط محبط
صعب صعوبه معاناه يعاني تعب متعب غلاء غالي ارتفاع_الاسعار بطاله فقر مرض وفاه موت قتل
حرب عنف هجوم اعتداء احتيال نصب سرقه كذب كذاب مخالفه مخالفات تاخير تاخر عطل معطل خلل
خيبه مخيب ماينفع مايصلح زفت خايس سيئين رديء رديئه ضرر اضرار تضرر شكوى شكاوى ندم
""".split()
_POS_EN = """
good great excellent amazing awesome love loved lovely best better happy glad proud success successful
win won wonderful fantastic brilliant beautiful nice thanks thank congrats congratulations impressive
innovative innovation growth improve improved improvement positive hope hopeful inspiring helpful useful
easy fast safe secure strong outstanding remarkable progress achievement achieve achieved recommend
""".split()
_NEG_EN = """
bad worse worst terrible awful horrible hate hated sad angry fail failed failure problem problems issue
issues crisis weak decline drop negative poor disappointing disappointed corrupt corruption danger
dangerous threat scary fear worried worry boring annoying difficult hard expensive unemployment poverty
death killed war violence attack fraud scam lie liar broken delay delayed bug damage complaint regret
""".split()
_NEGATORS = {normalize_arabic(w) for w in "لا ليس ليست لم لن ما مو مش غير بدون ابدا never not no without isn't wasn't don't doesn't didn't cannot can't".split()}
_POS_EMOJI = set("😀😃😄😁😊🙂😍🥰😘👍👏🙏💪🎉🎊❤💚💙💛🌹🔥✨🏆🥇😎🤩💯✅")
_NEG_EMOJI = set("😞😔😟😢😭😡😠🤬👎💔😤😩😫😱🤮🤢❌⚠😒🙄")

_PREFIXES = ("وال", "بال", "فال", "كال", "لل", "ال", "و", "ف", "ب", "ل", "ك")
_SUFFIXES = ("هما", "كما", "ات", "ون", "ين", "ان", "ها", "هم", "كم", "نا", "ه", "ي", "ك", "ا")


def _norm_set(words):
    return {normalize_arabic(w).lower().replace("_", " ") for w in words}


POS = _norm_set(_POS_AR) | _norm_set(_POS_EN)
NEG = _norm_set(_NEG_AR) | _norm_set(_NEG_EN)


def _variants(tok: str):
    yield tok
    for p in _PREFIXES:
        if tok.startswith(p) and len(tok) - len(p) >= 3:
            base = tok[len(p):]
            yield base
            for s in _SUFFIXES:
                if base.endswith(s) and len(base) - len(s) >= 3:
                    yield base[: -len(s)]
            break
    for s in _SUFFIXES:
        if tok.endswith(s) and len(tok) - len(s) >= 3:
            yield tok[: -len(s)]


def _polarity(tok: str) -> int:
    for v in _variants(tok):
        if v in POS:
            return 1
        if v in NEG:
            return -1
    return 0


def lexicon_sentiment(text: str | None) -> dict:
    raw = text or ""
    toks = analysis_text(raw).split()
    pos = neg = 0
    for i, tok in enumerate(toks):
        pol = _polarity(tok)
        if pol == 0:
            continue
        # A negator up to two words before flips the polarity, unless another
        # sentiment word sits in between ("not good, terrible" → two negatives).
        for j in (i - 1, i - 2):
            if j < 0:
                break
            if toks[j] in _NEGATORS:
                pol = -pol
                break
            if _polarity(toks[j]) != 0:
                break
        if pol > 0:
            pos += 1
        else:
            neg += 1
    pos += sum(1 for ch in raw if ch in _POS_EMOJI)
    neg += sum(1 for ch in raw if ch in _NEG_EMOJI)
    total = pos + neg
    if total == 0:
        label, score = "neutral", 0.0
    elif pos and neg and min(pos, neg) / max(pos, neg) >= 0.5:
        label, score = "mixed", (pos - neg) / total
    elif pos > neg:
        label, score = "positive", (pos - neg) / total
    else:
        label, score = "negative", (pos - neg) / total
    return {"label": label, "score": round(score, 3), "pos": pos, "neg": neg}


# ------------------------------------------------------------ transformers
_pipelines: dict[str, object] = {}


def transformers_available() -> bool:
    try:
        import transformers  # noqa: F401
        import torch  # noqa: F401
        return True
    except Exception:
        return False


def _get_pipeline(model_name: str):
    if model_name not in _pipelines:
        from transformers import pipeline
        _pipelines[model_name] = pipeline(
            "sentiment-analysis", model=model_name, tokenizer=model_name,
            model_kwargs={"cache_dir": str(config.MODELS_DIR)}, truncation=True, max_length=256,
        )
    return _pipelines[model_name]


def _map_label(label: str) -> str:
    l = label.lower()
    if l in ("label_0",):
        return "negative"
    if l in ("label_1",):
        return "neutral"
    if l in ("label_2",):
        return "positive"
    if "pos" in l:
        return "positive"
    if "neg" in l:
        return "negative"
    if "mix" in l:
        return "mixed"
    return "neutral"


def transformer_sentiment(texts: list[str], langs: list[str]) -> list[dict]:
    ar_model = db.get_setting("sentiment_model_ar", "CAMeL-Lab/bert-base-arabic-camelbert-da-sentiment")
    multi_model = db.get_setting("sentiment_model_multi", "cardiffnlp/twitter-xlm-roberta-base-sentiment")
    out: list[dict | None] = [None] * len(texts)
    groups: dict[str, list[int]] = {}
    for i, lang in enumerate(langs):
        groups.setdefault(ar_model if lang == "ar" else multi_model, []).append(i)
    for model_name, idx in groups.items():
        pipe = _get_pipeline(model_name)
        preds = pipe([texts[i] or "" for i in idx], batch_size=16)
        for i, p in zip(idx, preds):
            out[i] = {"label": _map_label(p["label"]), "score": round(float(p["score"]), 4), "model": model_name}
    return out  # type: ignore[return-value]


# ------------------------------------------------------------------ runner
def analyze_posts(df: pd.DataFrame, engine: str = "lexicon", store: bool = True) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["post_id", "label", "score", "model"])
    texts = df["clean_text"].fillna(df["raw_text"]).fillna("").tolist()
    if engine == "transformers":
        if not transformers_available():
            raise RuntimeError("مكتبة Transformers/PyTorch غير مثبتة. ثبّت requirements-ai.txt أو استخدم المحرك المعجمي.")
        res = transformer_sentiment(texts, df["lang"].fillna("und").tolist())
        model_tag = "transformers"
    else:
        res = [lexicon_sentiment(t) for t in texts]
        model_tag = "lexicon-v1"
    out = pd.DataFrame({
        "post_id": df["post_id"].values,
        "label": [r["label"] for r in res],
        "score": [r["score"] for r in res],
        "model": [r.get("model", model_tag) for r in res],
    })
    if store:
        now = db.utcnow()
        with db.get_conn() as c:
            c.executemany(
                "INSERT INTO sentiment_results(post_id, model, label, score, scores_json, analyzed_at) VALUES (?,?,?,?,?,?)"
                " ON CONFLICT(post_id, model) DO UPDATE SET label = excluded.label, score = excluded.score,"
                " scores_json = excluded.scores_json, analyzed_at = excluded.analyzed_at",
                [(pid, model_tag, r["label"], r["score"], json.dumps(r, ensure_ascii=False), now)
                 for pid, r in zip(out["post_id"], res)],
            )
    return out


def stored_sentiment(post_ids: list[str] | None = None, model: str | None = None) -> pd.DataFrame:
    sql = "SELECT post_id, model, label, score, analyzed_at FROM sentiment_results"
    where, params = [], []
    if model:
        where.append("model = ?")
        params.append(model)
    df = db.read_df(sql + (" WHERE " + " AND ".join(where) if where else ""), params)
    if post_ids is not None:
        df = df[df["post_id"].isin(set(post_ids))]
    # One label per post: prefer the transformer result when both exist.
    if not df.empty:
        df["_rank"] = (df["model"] != "transformers").astype(int)
        df = df.sort_values("_rank").drop_duplicates("post_id").drop(columns="_rank")
    return df


def sentiment_split(text: str) -> list[str]:
    return [s for s in re.split(r"[.!?؟\n]+", text or "") if s.strip()]
