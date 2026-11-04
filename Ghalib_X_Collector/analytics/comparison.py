"""Comparison of several groups of posts (keywords, hashtags, accounts, periods, jobs)."""
from __future__ import annotations

import pandas as pd

from analytics import statistics as stx
from analytics.sentiment import LABELS_AR, lexicon_sentiment, stored_sentiment


def compare_groups(groups: dict[str, pd.DataFrame], top_words: int = 40) -> dict:
    summary, series, accounts, sent_rows, words = [], [], [], [], {}
    for name, df in groups.items():
        k = stx.kpis(df) if not df.empty else {"total_posts": 0, "unique_accounts": 0, "avg_engagement": None}
        tl = stx.posts_over_time(df, "D")
        growth = None
        if len(tl) >= 2:
            half = len(tl) // 2
            a, b = tl["posts"].iloc[:half].mean(), tl["posts"].iloc[half:].mean()
            growth = round((b - a) / a * 100, 1) if a else None
        summary.append({"group": name, "posts": k["total_posts"], "accounts": k["unique_accounts"],
                        "avg_engagement": round(k["avg_engagement"], 2) if k.get("avg_engagement") is not None else None,
                        "avg_views": round(df["views_count"].mean(), 1) if not df.empty and df["views_count"].notna().any() else None,
                        "growth_pct": growth})
        if not tl.empty:
            series.append(tl.assign(term=name))
        ta = stx.top_accounts(df, 5)
        accounts.append(ta.assign(group=name))
        if not df.empty:
            s = stored_sentiment(df["post_id"].tolist())
            labels = dict(zip(s["post_id"], s["label"])) if not s.empty else {}
            texts = df.set_index("post_id")["clean_text"].fillna(df.set_index("post_id")["raw_text"])
            lab = [labels.get(pid) or lexicon_sentiment(t)["label"] for pid, t in texts.items()]
            vc = pd.Series(lab).value_counts(normalize=True) * 100
            for l in LABELS_AR:
                sent_rows.append({"group": name, "label": l, "label_ar": LABELS_AR[l], "share": round(float(vc.get(l, 0)), 1)})
        words[name] = stx.top_words(df, top_words)["word"].tolist() if not df.empty else []
    sets = [set(v) for v in words.values() if v]
    common = sorted(set.intersection(*sets)) if len(sets) >= 2 else []
    distinctive = {g: [w for w in ws if all(w not in set(o) for gg, o in words.items() if gg != g)][:15]
                   for g, ws in words.items()}
    return {
        "summary": pd.DataFrame(summary),
        "timeline": pd.concat(series) if series else pd.DataFrame(columns=["period", "posts", "term"]),
        "accounts": pd.concat(accounts) if accounts else pd.DataFrame(),
        "sentiment": pd.DataFrame(sent_rows),
        "common_words": common,
        "distinctive_words": distinctive,
    }
