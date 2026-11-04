"""Trend detection: which terms / hashtags rise in a recent window vs. the window before.

growth = ((recent + 1) / (baseline + 1)) after normalising both windows by their
number of posts, so a larger recent sample does not inflate every term.
Terms need a minimum recent count to avoid noise.
"""
from __future__ import annotations

from collections import Counter
from datetime import timedelta

import pandas as pd

from analytics.statistics import tokenize
from processing.cleaning import normalize_hashtag


def _terms(df: pd.DataFrame, kind: str) -> Counter:
    c = Counter()
    if kind == "hashtags":
        for tags in df["hashtags"]:
            c.update({"#" + normalize_hashtag(t) for t in tags})
    else:
        for t in df["clean_text"].fillna(df["raw_text"]).fillna(""):
            c.update(set(tokenize(t)))
    return c


def detect_trends(df: pd.DataFrame, window_days: int = 1, kind: str = "words", min_count: int = 3,
                  top_n: int = 25, reference_end=None) -> pd.DataFrame:
    d = df.dropna(subset=["published_dt"])
    cols = ["term", "recent", "baseline", "recent_share", "baseline_share", "growth"]
    if d.empty:
        return pd.DataFrame(columns=cols)
    end = pd.Timestamp(reference_end, tz="UTC") if reference_end is not None else d["published_dt"].max()
    w = timedelta(days=window_days)
    recent = d[(d["published_dt"] > end - w) & (d["published_dt"] <= end)]
    base = d[(d["published_dt"] > end - 2 * w) & (d["published_dt"] <= end - w)]
    if recent.empty:
        return pd.DataFrame(columns=cols)
    rc, bc = _terms(recent, kind), _terms(base, kind) if not base.empty else Counter()
    nr, nb = max(len(recent), 1), max(len(base), 1)
    rows = []
    for term, r in rc.items():
        if r < min_count:
            continue
        b = bc.get(term, 0)
        rs, bs = r / nr, b / nb
        growth = (rs + 1 / nr) / (bs + 1 / nb)
        rows.append({"term": term, "recent": r, "baseline": b, "recent_share": round(rs, 4),
                     "baseline_share": round(bs, 4), "growth": round(growth, 2)})
    out = pd.DataFrame(rows, columns=cols)
    if out.empty:
        return out
    return out.sort_values(["growth", "recent"], ascending=False).head(top_n)


def term_timeseries(df: pd.DataFrame, terms: list[str], freq: str = "D") -> pd.DataFrame:
    d = df.dropna(subset=["published_dt"]).copy()
    rows = []
    for term in terms:
        if term.startswith("#"):
            key = normalize_hashtag(term)
            m = d["hashtags"].apply(lambda tags: key in {normalize_hashtag(t) for t in tags})
        else:
            tk = tokenize(term)
            m = d["clean_text"].fillna(d["raw_text"]).fillna("").apply(lambda t: all(x in tokenize(t) for x in tk)) if tk else False
        s = d[m].set_index("published_dt").resample(freq).size()
        for period, n in s.items():
            rows.append({"term": term, "period": period, "posts": int(n)})
    return pd.DataFrame(rows, columns=["term", "period", "posts"])


def hashtag_growth(df: pd.DataFrame, tag: str, freq: str = "W") -> pd.DataFrame:
    ts = term_timeseries(df, ["#" + tag.lstrip("#")], freq)
    if ts.empty:
        return ts
    ts["growth_pct"] = ts["posts"].pct_change().replace([float("inf")], None).mul(100).round(1)
    return ts
