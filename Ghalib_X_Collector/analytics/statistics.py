"""Descriptive statistics over the posts stored in SQLite.

Every function receives a DataFrame produced by ``load_posts`` (real collected
records) and returns plain DataFrames / dicts that the dashboard plots. Counts
that X did not expose are NULL and are excluded from averages, never treated as 0.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone

import pandas as pd

from analytics.stopwords import STOPWORDS
from database import db
from processing.cleaning import analysis_text, normalize_hashtag

METRIC_COLS = ["replies_count", "reposts_count", "likes_count", "quotes_count", "views_count"]


def load_posts(job_ids: list[int] | None = None, date_from=None, date_to=None, languages: list[str] | None = None,
               keyword: str | None = None, usernames: list[str] | None = None, hashtag: str | None = None,
               exclude_duplicate_text: bool = False, only_valid: bool = True, limit: int | None = None) -> pd.DataFrame:
    where, params = [], []
    if job_ids:
        where.append(f"p.post_id IN (SELECT post_id FROM job_posts WHERE job_id IN ({','.join('?' * len(job_ids))}))")
        params += list(job_ids)
    if date_from:
        where.append("p.published_date >= ?")
        params.append(str(date_from)[:10])
    if date_to:
        where.append("p.published_date <= ?")
        params.append(str(date_to)[:10])
    if languages:
        where.append(f"COALESCE(p.detected_language, p.language, 'und') IN ({','.join('?' * len(languages))})")
        params += list(languages)
    if usernames:
        names = [u.lower().lstrip("@") for u in usernames]
        where.append(f"p.username IN ({','.join('?' * len(names))})")
        params += names
    if hashtag:
        where.append("p.post_id IN (SELECT ph.post_id FROM post_hashtags ph JOIN hashtags h ON h.id = ph.hashtag_id WHERE h.tag = ?)")
        params.append(normalize_hashtag(hashtag))
    if keyword:
        where.append("(p.raw_text LIKE ? OR p.clean_text LIKE ?)")
        params += [f"%{keyword}%", f"%{keyword}%"]
    if exclude_duplicate_text:
        where.append("(p.validation_notes IS NULL OR p.validation_notes NOT LIKE '%duplicate_text_of%')")
    if only_valid:
        where.append("p.is_valid = 1")
    sql = (
        "SELECT p.*, COALESCE(p.detected_language, p.language, 'und') AS lang,"
        " a.followers_count AS author_followers FROM posts p LEFT JOIN accounts a ON a.username = p.username"
        + (" WHERE " + " AND ".join(where) if where else "")
        + " ORDER BY p.published_at DESC"
        + (f" LIMIT {int(limit)}" if limit else "")
    )
    df = db.read_df(sql, params)
    return enrich(df)


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        for c in ("engagement", "published_dt", "hashtags", "mentions"):
            df[c] = pd.Series(dtype="object")
        return df
    for c in METRIC_COLS:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    eng_cols = ["replies_count", "reposts_count", "likes_count", "quotes_count"]
    has_any = df[eng_cols].notna().any(axis=1)
    df["engagement"] = df[eng_cols].fillna(0).sum(axis=1).where(has_any)
    df["published_dt"] = pd.to_datetime(df["published_at"], errors="coerce", utc=True)
    df["hashtags"] = df["hashtags_json"].apply(lambda s: json.loads(s) if s else [])
    df["mentions"] = df["mentions_json"].apply(lambda s: json.loads(s) if s else [])
    return df


def kpis(df: pd.DataFrame) -> dict:
    now = datetime.now(timezone.utc)
    total = len(df)
    out = {
        "total_posts": total,
        "unique_accounts": int(df["username"].nunique()) if total else 0,
        "unique_hashtags": len({normalize_hashtag(t) for tags in df.get("hashtags", []) for t in tags}) if total else 0,
        "total_jobs": int(db.fetch_value("SELECT COUNT(*) FROM search_jobs", default=0)),
        "last_24h": int((df["published_dt"] >= now - timedelta(hours=24)).sum()) if total else 0,
        "last_7d": int((df["published_dt"] >= now - timedelta(days=7)).sum()) if total else 0,
        "avg_engagement": float(df["engagement"].mean()) if total and df["engagement"].notna().any() else None,
        "engagement_available": int(df["engagement"].notna().sum()) if total else 0,
        "new_posts_24h": int((pd.to_datetime(df["first_collected_at"], utc=True, errors="coerce") >= now - timedelta(hours=24)).sum()) if total else 0,
        "avg_views": float(df["views_count"].mean()) if total and df["views_count"].notna().any() else None,
    }
    return out


def posts_over_time(df: pd.DataFrame, freq: str = "D") -> pd.DataFrame:
    if df.empty or df["published_dt"].isna().all():
        return pd.DataFrame(columns=["period", "posts"])
    s = df.dropna(subset=["published_dt"]).set_index("published_dt").resample(freq).size()
    out = s.reset_index()
    out.columns = ["period", "posts"]
    return out


def language_distribution(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["lang", "posts"])
    out = df["lang"].fillna("und").value_counts().reset_index()
    out.columns = ["lang", "posts"]
    return out


def top_hashtags(df: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    counter, display = Counter(), {}
    for tags in df.get("hashtags", []):
        for t in set(normalize_hashtag(x) for x in tags):
            counter[t] += 1
        for x in tags:
            display.setdefault(normalize_hashtag(x), x)
    rows = [{"hashtag": "#" + display[k], "tag": k, "posts": v} for k, v in counter.most_common(n)]
    return pd.DataFrame(rows, columns=["hashtag", "tag", "posts"])


def top_accounts(df: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["username", "display_name", "posts", "avg_engagement", "total_engagement"])
    g = df.groupby("username", dropna=True).agg(
        display_name=("display_name", "first"),
        posts=("post_id", "count"),
        avg_engagement=("engagement", "mean"),
        total_engagement=("engagement", "sum"),
        followers=("author_followers", "max"),
    ).reset_index().sort_values(["posts", "total_engagement"], ascending=False)
    return g.head(n)


def tokenize(text: str) -> list[str]:
    return [w for w in analysis_text(text).split() if len(w) > 1 and w not in STOPWORDS and not w.isdigit()]


def top_words(df: pd.DataFrame, n: int = 30, exclude: set[str] | None = None) -> pd.DataFrame:
    exclude = {analysis_text(e) for e in (exclude or set())}
    counter = Counter()
    for t in df.get("clean_text", pd.Series(dtype=str)).fillna(df.get("raw_text", "")):
        counter.update(w for w in tokenize(t or "") if w not in exclude)
    return pd.DataFrame(counter.most_common(n), columns=["word", "count"])


def engagement_distribution(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["bucket", "posts"])
    e = df["engagement"].dropna()
    if e.empty:
        return pd.DataFrame(columns=["bucket", "posts"])
    bins = [-1, 0, 10, 50, 100, 500, 1000, 10000, float("inf")]
    labels = ["0", "1-10", "11-50", "51-100", "101-500", "501-1K", "1K-10K", "+10K"]
    cut = pd.cut(e, bins=bins, labels=labels)
    out = cut.value_counts().reindex(labels).fillna(0).astype(int).reset_index()
    out.columns = ["bucket", "posts"]
    return out


def metric_totals(df: pd.DataFrame) -> dict:
    return {c: (int(df[c].sum()) if c in df and df[c].notna().any() else None) for c in METRIC_COLS}


def account_activity(df: pd.DataFrame, top_n: int = 10) -> pd.DataFrame:
    """Posts per day for the most active accounts (long format)."""
    if df.empty:
        return pd.DataFrame(columns=["username", "date", "posts"])
    top = df["username"].value_counts().head(top_n).index
    sub = df[df["username"].isin(top)].dropna(subset=["published_date"])
    out = sub.groupby(["username", "published_date"]).size().reset_index(name="posts")
    out.columns = ["username", "date", "posts"]
    return out


def hourly_heatmap(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "published_time" not in df:
        return pd.DataFrame()
    d = df.dropna(subset=["published_date", "published_time"]).copy()
    if d.empty:
        return pd.DataFrame()
    d["hour"] = d["published_time"].str[:2].astype(int)
    d["weekday"] = pd.to_datetime(d["published_date"]).dt.dayofweek
    return d.pivot_table(index="weekday", columns="hour", values="post_id", aggfunc="count", fill_value=0)


def hashtag_cooccurrence(df: pd.DataFrame, tag: str, n: int = 15) -> pd.DataFrame:
    norm = normalize_hashtag(tag)
    c = Counter()
    for tags in df.get("hashtags", []):
        ns = {normalize_hashtag(t) for t in tags}
        if norm in ns:
            c.update(ns - {norm})
    return pd.DataFrame(c.most_common(n), columns=["tag", "posts"])


def words_for_posts(df: pd.DataFrame, n: int = 15) -> list[str]:
    return top_words(df, n)["word"].tolist()


def safe_ratio(a, b):
    return (a / b) if b else None


def strip_tag(t: str) -> str:
    return re.sub(r"^#", "", t or "")
