from analytics import statistics as stx
from analytics.comparison import compare_groups
from analytics.entities import analyze_entities, rule_entities
from analytics.sentiment import analyze_posts, lexicon_sentiment, stored_sentiment
from analytics.summarization import extractive_summary
from analytics.topic_modeling import extract_keywords, run_topic_model
from analytics.trend_analysis import detect_trends, term_timeseries
from database import db
from tests.helpers import seed


def test_statistics():
    seed(60)
    df = stx.load_posts()
    k = stx.kpis(df)
    assert k["total_posts"] == 60 and k["unique_accounts"] == 7 and k["total_jobs"] == 1
    assert k["avg_engagement"] > 0
    assert stx.posts_over_time(df, "D")["posts"].sum() == 60
    assert set(stx.language_distribution(df)["lang"]) == {"ar", "en"}
    th = stx.top_hashtags(df, 5)
    assert th.iloc[0]["posts"] == 12
    assert stx.top_accounts(df, 3)["posts"].iloc[0] >= 8
    words = stx.top_words(df, 20)["word"].tolist()
    assert "عينه" in words and "في" not in words
    assert stx.engagement_distribution(df)["posts"].sum() == 60
    assert len(stx.load_posts(keyword="وزارة")) == 12
    assert len(stx.load_posts(hashtag="#الصحة_الرقمية")) == 12
    assert len(stx.load_posts(languages=["en"])) == 12
    assert len(stx.load_posts(usernames=["@fixture_user1"])) > 0


def test_sentiment_lexicon_and_storage():
    assert lexicon_sentiment("خدمة رائعة وممتازة شكرا")["label"] == "positive"
    assert lexicon_sentiment("تجربة سيئة جدا وتأخير مزعج")["label"] == "negative"
    assert lexicon_sentiment("الاجتماع غدا الساعة العاشرة")["label"] == "neutral"
    assert lexicon_sentiment("المنتج رائع لكن التوصيل سيء")["label"] == "mixed"
    assert lexicon_sentiment("ليس جيدا")["label"] == "negative"
    assert lexicon_sentiment("This is not good, terrible")["label"] == "negative"
    seed(30)
    df = stx.load_posts()
    out = analyze_posts(df, engine="lexicon")
    assert len(out) == 30 and set(out["label"]) <= {"positive", "negative", "neutral", "mixed"}
    assert len(stored_sentiment(df["post_id"].tolist())) == 30


def test_topics_keywords_trends_entities_summary():
    seed(60)
    df = stx.load_posts()
    res = run_topic_model(df, n_topics=5)
    assert len(res["topics"]) == 5 and sum(t["posts"] for t in res["topics"]) == 60
    assert db.fetch_value("SELECT COUNT(*) FROM topic_results WHERE run_id = ?", (res["run_id"],)) == 60
    kw = extract_keywords(df, 10)
    assert len(kw) == 10
    tr = detect_trends(df, window_days=1, kind="hashtags", min_count=1)
    assert not tr.empty and (tr["growth"] > 0).all()
    ts = term_timeseries(df, ["#الذكاء_الاصطناعي"])
    assert ts["posts"].sum() == 12
    ents = analyze_entities(df, engine="rules")
    types = set(ents["entity_type"])
    assert {"government", "location", "event"} <= types
    assert ("وزارة الصحة", "government") in rule_entities("أعلنت وزارة الصحة اليوم")
    summ = extractive_summary(df, k=4)
    assert len(summ) == 4 and summ["post_id"].is_unique


def test_comparison():
    seed(60)
    groups = {"ai": stx.load_posts(hashtag="الذكاء_الاصطناعي"), "health": stx.load_posts(hashtag="الصحة_الرقمية")}
    r = compare_groups(groups)
    assert list(r["summary"]["posts"]) == [12, 12]
    assert set(r["sentiment"]["group"]) == {"ai", "health"}
    assert "عينه" in r["common_words"]
    assert r["distinctive_words"]["health"]
