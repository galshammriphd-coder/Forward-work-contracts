"""Open-ended responses: PII redaction, keywords, topic modelling (NMF) and a transparent
lexicon-based sentiment indicator. All outputs are exploratory aids for — not a substitute
for — human qualitative coding."""
from __future__ import annotations

import re
from collections import Counter

import numpy as np
import pandas as pd
from sklearn.decomposition import NMF
from sklearn.feature_extraction.text import TfidfVectorizer

from . import charts
from .utils import AnalysisError, col, normalize_text, result, table, warn

PII_PATTERNS = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[EMAIL]"),
    (re.compile(r"https?://\S+|www\.\S+"), "[URL]"),
    (re.compile(r"(?:\+?\d[\d\s\-()]{7,}\d)"), "[NUMBER]"),
    (re.compile(r"[٠-٩]{6,}"), "[NUMBER]"),
]
STOP_EN = set("""a an the and or but if then of to in on for with at by from as is are was were be been being it its this that these those i me my we our you your he she they them
their his her not no yes do does did so very can could would should will just also there here than too more most much many some any all about into over under up down out
what which who whom how why when where am has have had""".split())
STOP_AR = set(normalize_text(w) for w in """في من على إلى الى عن مع هذا هذه ذلك تلك التي الذي الذين و أو او ثم كما لكن لا لم لن ما هو هي هم نحن أنا انا كان كانت يكون تكون قد
كل بعض أي اي غير بين عند حتى إن ان أن اذا إذا فقط جدا جداً أكثر اكثر أيضا ايضا لدى لدي عليه عليها فيه فيها به بها له لها هناك هنا تم يتم""".split())
POS = set(normalize_text(w) for w in """good great excellent helpful satisfied happy useful clear easy fast friendly professional supportive improved best love like positive
جيد ممتاز رائع مفيد سعيد راض راضي سهل سريع واضح متعاون محترف مميز افضل أفضل احب أحب شكرا شكراً ايجابي إيجابي""".split())
NEG = set(normalize_text(w) for w in """bad poor slow difficult hard confusing unhelpful unhappy dissatisfied problem problems worst hate negative delay delays expensive rude
سيء سيئ ضعيف بطيء صعب معقد مشكله مشكلة مشاكل تأخير تاخير غالي سلبي سوء ممل متعب""".split())


def redact(text: str) -> str:
    out = str(text)
    for pat, rep in PII_PATTERNS:
        out = pat.sub(rep, out)
    return out


def tokens(text: str) -> list[str]:
    t = normalize_text(redact(text))
    words = re.findall(r"[\w؀-ۿ]+", t)
    out = []
    for w in words:
        if w.isdigit() or len(w) < 2 or w in STOP_EN or w in STOP_AR or w.startswith(("email", "url", "number")):
            continue
        if re.match(r"^ال[؀-ۿ]{3,}", w):
            w = w[2:]  # light Arabic stemming: drop the definite article
        out.append(w)
    return out


def run_text(df, params, ctx):
    v = params["variable"]
    s = df[v].dropna().astype(str).map(str.strip)
    s = s[s.str.len() > 1]
    if len(s) < 5:
        raise AnalysisError("At least 5 non-empty text responses are needed.", "يلزم 5 إجابات نصية غير فارغة على الأقل.")
    toks = s.map(tokens)
    docs = toks.map(" ".join)
    freq = Counter(w for t in toks for w in t)
    top = [{"term": w, "count": c, "docs": int(sum(w in t for t in toks))} for w, c in freq.most_common(30)]
    bigrams = Counter(f"{a} {b}" for t in toks for a, b in zip(t, t[1:]))
    top_bi = [{"term": w, "count": c} for w, c in bigrams.most_common(15) if c > 1]
    # topics
    topics, assign = [], None
    nonempty = docs[docs.str.len() > 0]
    k = int(params.get("n_topics") or max(2, min(6, len(nonempty) // 15)))
    if len(nonempty) >= 10:
        vec = TfidfVectorizer(min_df=2 if len(nonempty) >= 20 else 1, max_df=0.9, token_pattern=r"\S+")
        try:
            X = vec.fit_transform(nonempty)
            k = min(k, X.shape[1] - 1, X.shape[0] - 1)
            if k >= 2:
                nmf = NMF(n_components=k, random_state=42, init="nndsvda", max_iter=500)
                W = nmf.fit_transform(X)
                terms = np.array(vec.get_feature_names_out())
                assign = pd.Series(W.argmax(axis=1), index=nonempty.index)
                for j in range(k):
                    members = assign[assign == j].index
                    strength = pd.Series(W[:, j], index=nonempty.index).loc[members].sort_values(ascending=False)
                    quotes = [redact(s.loc[i])[:300] for i in strength.index[:3]]
                    topics.append({"topic": j + 1, "keywords": ", ".join(terms[np.argsort(nmf.components_[j])[::-1][:8]]), "n": int(len(members)),
                                   "pct": 100 * len(members) / len(nonempty), "quotes": quotes})
        except ValueError:
            pass
    # sentiment (lexicon)
    def score(t):
        p = sum(w in POS for w in t)
        n = sum(w in NEG for w in t)
        return "positive" if p > n else "negative" if n > p else "neutral/unclassified"
    sent = toks.map(score).value_counts()
    sent_rows = [{"sentiment": k_, "count": int(c), "pct": 100 * c / len(toks)} for k_, c in sent.items()]
    tables = [table("keywords", "Most frequent terms", "أكثر المصطلحات تكراراً", [col("term", "Term", "المصطلح"), col("count", "Frequency", "التكرار"), col("docs", "Responses", "عدد الإجابات")], top,
                    "After PII redaction, normalisation, stop-word removal and light stemming.", "بعد إخفاء البيانات الشخصية والتطبيع وحذف الكلمات الشائعة والتجذيع الخفيف.")]
    if top_bi:
        tables.append(table("bigrams", "Frequent phrases (bigrams)", "العبارات المتكررة (ثنائيات)", [col("term", "Phrase", "العبارة"), col("count", "Frequency", "التكرار")], top_bi))
    if topics:
        tables.append(table("topics", "Topic model (NMF)", "نمذجة الموضوعات (NMF)",
                            [col("topic", "Topic", "الموضوع"), col("keywords", "Top keywords", "الكلمات المفتاحية"), col("n", "Responses", "الإجابات"), col("pct", "%", "%", "1"),
                             col("quotes", "Supporting quotes (redacted)", "اقتباسات داعمة (بعد الإخفاء)")], topics,
                            "Topics are statistical word clusters; name and validate them through human qualitative coding.",
                            "الموضوعات تجمعات إحصائية للكلمات؛ ويجب تسميتها والتحقق منها عبر الترميز النوعي البشري."))
    tables.append(table("sentiment", "Lexicon-based sentiment (indicative)", "تحليل المشاعر المعجمي (استرشادي)",
                        [col("sentiment", "Polarity", "القطبية"), col("count", "N", "العدد"), col("pct", "%", "%", "1")], sent_rows,
                        "Simple bilingual word lists; sarcasm, negation and context are not handled.", "قوائم كلمات ثنائية اللغة بسيطة؛ لا تعالج السخرية أو النفي أو السياق."))
    ch = [charts.bar("terms", [t["term"] for t in top[:15]], [t["count"] for t in top[:15]], "Top terms", "أكثر المصطلحات", horizontal=True)]
    return result("text", f"Open-ended responses: {v}", f"تحليل الإجابات المفتوحة: {v}", params=params, n=len(s), tables=tables, charts=ch,
                  stats={"n_responses": len(s), "topics": topics, "keywords": top[:15], "sentiment": sent_rows}, nature="exploratory",
                  warnings=[warn("Automated text analysis is exploratory and does not replace systematic human coding and verification.",
                                 "التحليل الآلي للنصوص استكشافي ولا يغني عن الترميز البشري المنهجي والتحقق.")])
