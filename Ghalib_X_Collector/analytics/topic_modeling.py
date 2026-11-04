"""Topic modelling and keyword extraction (scikit-learn, fully local).

Topics: TF-IDF (unigrams + bigrams, Arabic-normalised, stop words removed) and
Non-negative Matrix Factorisation. Each post gets its dominant topic; the
topic label is made of its top keywords. Results are stored in topic_results
under a run id so different runs can be compared.
"""
from __future__ import annotations

import uuid

import numpy as np
import pandas as pd

from analytics.stopwords import STOPWORDS
from database import db
from processing.cleaning import analysis_text


def _corpus(df: pd.DataFrame) -> list[str]:
    texts = df["clean_text"].fillna(df["raw_text"]).fillna("")
    return [" ".join(w for w in analysis_text(t).split() if w not in STOPWORDS and len(w) > 1) for t in texts]


def extract_keywords(df: pd.DataFrame, n: int = 30, ngram_max: int = 2) -> pd.DataFrame:
    """Corpus-level TF-IDF keyword ranking."""
    from sklearn.feature_extraction.text import TfidfVectorizer

    docs = [d for d in _corpus(df) if d]
    if len(docs) < 2:
        return pd.DataFrame(columns=["keyword", "score", "documents"])
    vec = TfidfVectorizer(ngram_range=(1, ngram_max), min_df=2 if len(docs) >= 20 else 1, max_features=20000,
                          token_pattern=r"(?u)\b\w\w+\b")
    X = vec.fit_transform(docs)
    scores = np.asarray(X.sum(axis=0)).ravel()
    dfreq = np.asarray((X > 0).sum(axis=0)).ravel()
    terms = vec.get_feature_names_out()
    order = scores.argsort()[::-1][:n]
    return pd.DataFrame({"keyword": terms[order], "score": scores[order].round(3), "documents": dfreq[order]})


def post_keywords(text: str, vectorizer=None, n: int = 5) -> list[str]:
    toks = [w for w in analysis_text(text).split() if w not in STOPWORDS and len(w) > 2]
    seen = []
    for t in toks:
        if t not in seen:
            seen.append(t)
    return seen[:n]


def run_topic_model(df: pd.DataFrame, n_topics: int = 6, n_words: int = 8, store: bool = True) -> dict:
    from sklearn.decomposition import NMF
    from sklearn.feature_extraction.text import TfidfVectorizer

    docs = _corpus(df)
    mask = [bool(d.strip()) for d in docs]
    usable = [d for d, m in zip(docs, mask) if m]
    if len(usable) < max(10, n_topics * 3):
        raise ValueError(f"عدد المنشورات غير كافٍ لاكتشاف {n_topics} موضوعات (المتاح {len(usable)}، المطلوب {max(10, n_topics * 3)} على الأقل)")
    vec = TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_df=0.6, max_features=15000,
                          token_pattern=r"(?u)\b\w\w+\b")
    X = vec.fit_transform(usable)
    if X.shape[1] < n_topics:
        raise ValueError("المفردات المتاحة غير كافية لعدد الموضوعات المطلوب")
    model = NMF(n_components=n_topics, init="nndsvda", random_state=42, max_iter=400)
    W = model.fit_transform(X)
    H = model.components_
    terms = vec.get_feature_names_out()
    topics = []
    for k in range(n_topics):
        top = H[k].argsort()[::-1][:n_words]
        words = [terms[i] for i in top]
        topics.append({"topic_id": k, "label": " · ".join(words[:3]), "keywords": words})
    post_ids = df["post_id"].values[np.array(mask)]
    dominant = W.argmax(axis=1)
    weight = W.max(axis=1)
    assign = pd.DataFrame({"post_id": post_ids, "topic_id": dominant, "weight": weight.round(4)})
    assign = assign[assign["weight"] > 0]
    sizes = assign["topic_id"].value_counts().to_dict()
    for t in topics:
        t["posts"] = int(sizes.get(t["topic_id"], 0))
    run_id = uuid.uuid4().hex[:10]
    if store:
        now = db.utcnow()
        lab = {t["topic_id"]: t for t in topics}
        with db.get_conn() as c:
            c.executemany(
                "INSERT INTO topic_results(run_id, post_id, topic_id, topic_label, topic_keywords, weight, model, created_at)"
                " VALUES (?,?,?,?,?,?,?,?)",
                [(run_id, r.post_id, int(r.topic_id), lab[r.topic_id]["label"], ", ".join(lab[r.topic_id]["keywords"]),
                  float(r.weight), f"tfidf-nmf-k{n_topics}", now) for r in assign.itertuples()],
            )
    return {"run_id": run_id, "topics": topics, "assignments": assign}


def latest_topic_run() -> dict | None:
    row = db.fetch_one("SELECT run_id, model, created_at FROM topic_results ORDER BY id DESC LIMIT 1")
    if not row:
        return None
    df = db.read_df("SELECT topic_id, topic_label, topic_keywords, COUNT(*) AS posts FROM topic_results WHERE run_id = ?"
                    " GROUP BY topic_id, topic_label, topic_keywords ORDER BY posts DESC", (row["run_id"],))
    return {**row, "topics": df}
