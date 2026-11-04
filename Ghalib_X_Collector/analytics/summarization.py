"""Extractive summarisation of a discussion (local, deterministic).

The summary is built from the collected posts themselves: posts are scored by
TF-IDF similarity to the corpus centroid (how representative they are) plus a
small engagement bonus, then selected with Maximal Marginal Relevance so the
summary covers different angles instead of repeating one. Every sentence in
the summary is a real post with its link — nothing is generated or invented.
An optional abstractive model can be used when Transformers is installed.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import config
from analytics.stopwords import STOPWORDS
from database import db
from processing.cleaning import analysis_text


def extractive_summary(df: pd.DataFrame, k: int = 5, diversity: float = 0.6) -> pd.DataFrame:
    from sklearn.feature_extraction.text import TfidfVectorizer

    cols = ["post_id", "username", "text", "post_url", "engagement", "score"]
    d = df.copy()
    if "validation_notes" in d:
        d = d[~d["validation_notes"].fillna("").str.contains("duplicate_text_of")]
    d["_t"] = d["clean_text"].fillna(d["raw_text"]).fillna("")
    d["_a"] = d["_t"].apply(lambda t: " ".join(w for w in analysis_text(t).split() if w not in STOPWORDS))
    d = d[d["_a"].str.split().str.len() >= 4]
    if len(d) < 2:
        return pd.DataFrame(columns=cols)
    vec = TfidfVectorizer(ngram_range=(1, 2), token_pattern=r"(?u)\b\w\w+\b")
    X = vec.fit_transform(d["_a"])
    centroid = np.asarray(X.mean(axis=0))
    rel = (X @ centroid.T).ravel()
    rel = rel / (rel.max() or 1)
    eng = d["engagement"].fillna(0).to_numpy(dtype=float)
    bonus = np.log1p(eng) / (np.log1p(eng).max() or 1)
    score = 0.85 * rel + 0.15 * bonus
    sim = (X @ X.T).toarray()
    chosen: list[int] = []
    cand = list(range(len(d)))
    while cand and len(chosen) < k:
        if not chosen:
            best = max(cand, key=lambda i: score[i])
        else:
            best = max(cand, key=lambda i: diversity * score[i] - (1 - diversity) * max(sim[i][j] for j in chosen))
        chosen.append(best)
        cand.remove(best)
    sel = d.iloc[chosen]
    return pd.DataFrame({
        "post_id": sel["post_id"].values, "username": sel["username"].values, "text": sel["_t"].values,
        "post_url": sel["post_url"].values, "engagement": sel["engagement"].values,
        "score": np.round(score[chosen], 3),
    })


def abstractive_summary(texts: list[str], max_chars: int = 3500) -> str:
    from transformers import pipeline
    model = db.get_setting("summary_model", "csebuetnlp/mT5_multilingual_XLSum")
    pipe = pipeline("summarization", model=model, tokenizer=model, model_kwargs={"cache_dir": str(config.MODELS_DIR)})
    joined = "\n".join(texts)[:max_chars]
    return pipe(joined, max_length=160, min_length=30, truncation=True)[0]["summary_text"]
