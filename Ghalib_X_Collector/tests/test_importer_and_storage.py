import json

from collectors import collection_manager as cm
from collectors.result_importer import parse_file, parse_graphql_payload, post_from_dom
from database import db, models
from tests import fixtures as fx


def test_parse_search_timeline_new_layout():
    payload = fx.search_timeline([fx.tweet(1), fx.tweet(2, author=2, lang="en", text="Testing fixture #AI content")])
    posts, accounts = parse_graphql_payload(payload)
    assert [p.post_id for p in posts] == [str(fx.BASE_ID + 1), str(fx.BASE_ID + 2)]
    p = posts[0]
    assert p.username == "fixture_user1" and p.display_name == "مستخدم اختبار 1"
    assert p.published_at == "2026-11-02T08:15:00+00:00"
    assert (p.likes_count, p.reposts_count, p.views_count, p.language) == (10, 1, 100, "ar")
    assert p.hashtags == ["الذكاء_الاصطناعي"] and p.mentions == ["fixture_mention"]
    assert p.urls == ["https://example.org/article/1"]
    acc = {a.username: a for a in accounts}["fixture_user1"]
    assert acc.followers_count == 1000 and acc.location == "الرياض" and acc.account_created_at.startswith("2015-03-10")


def test_parse_old_layout_reply_and_profile():
    payload = fx.search_timeline([fx.tweet(3, author=3, reply_to=fx.BASE_ID + 1, new_layout=False)])
    posts, accounts = parse_graphql_payload(payload)
    assert posts[0].post_type == "reply" and posts[0].username == "fixture_user3"
    assert accounts[0].location == "جدة"
    _, accs = parse_graphql_payload(fx.profile_payload(5))
    assert accs[0].is_profile and accs[0].followers_count == 5000


def test_parse_repost_and_long_note():
    inner = fx.tweet(10, author=4, text="النص الأصلي الكامل")
    rt = fx.tweet(11, author=5, text="RT @fixture_user4: النص الأصلي…")
    rt["legacy"]["retweeted_status_result"] = {"result": inner}
    note = fx.tweet(12)
    note["note_tweet"] = {"note_tweet_results": {"result": {"text": "منشور طويل " * 50, "entity_set": {"hashtags": [{"text": "طويل"}]}}}}
    posts, _ = parse_graphql_payload(fx.search_timeline([rt, note]))
    by = {p.post_id: p for p in posts}
    assert by[str(fx.BASE_ID + 11)].post_type == "repost"
    assert by[str(fx.BASE_ID + 11)].raw_text == "RT @fixture_user4: النص الأصلي الكامل"
    assert str(fx.BASE_ID + 10) not in by        # nested original is not counted as a search result
    assert by[str(fx.BASE_ID + 12)].raw_text.startswith("منشور طويل") and by[str(fx.BASE_ID + 12)].hashtags == ["طويل"]


def test_tombstones_and_garbage_are_ignored():
    posts, accs = parse_graphql_payload({"data": {"x": [{"__typename": "TweetTombstone"}, {"legacy": {}}, None, 5]}})
    assert posts == [] and accs == []


def test_dom_item_conversion():
    p = post_from_dom({"post_id": "1850000000000000099", "username": "fixture_dom", "text": "مرحبا #تجربة @someone",
                       "datetime": "2026-11-01T09:00:00.000Z", "likes": "1.2K", "reposts": "١٢", "replies": "3",
                       "views": "12,345"})
    assert (p.likes_count, p.reposts_count, p.views_count) == (1200, 12, 12345)
    assert p.hashtags == ["تجربة"] and p.mentions == ["someone"] and p.source == "dom"
    assert post_from_dom({"post_id": "abc"}) is None


def test_store_batch_counts_new_and_duplicates():
    j1 = models.create_job("j1", "keyword", "x", ["x"], {})
    posts, accs = parse_graphql_payload(fx.search_timeline([fx.tweet(i) for i in range(1, 6)]))
    seen = set()
    c = cm.store_batch(j1, "x", posts, accs, "Asia/Riyadh", seen)
    assert c == {"received": 5, "new": 5, "duplicate": 0}
    # Same posts again in the same job are not recounted
    assert cm.store_batch(j1, "x", posts, accs, "Asia/Riyadh", seen)["received"] == 0
    j2 = models.create_job("j2", "keyword", "x", ["x"], {})
    c2 = cm.store_batch(j2, "x", posts[:3], accs, "Asia/Riyadh", set())
    assert c2 == {"received": 3, "new": 0, "duplicate": 3}
    j = models.get_job(j2)
    assert (j["received_count"], j["new_count"], j["duplicate_count"]) == (3, 0, 3)
    assert db.fetch_value("SELECT COUNT(*) FROM posts") == 5
    assert db.fetch_value("SELECT COUNT(*) FROM job_posts") == 8
    # every capture leaves provenance and a metrics snapshot
    assert db.fetch_value("SELECT COUNT(*) FROM post_sources") >= 8
    assert db.fetch_value("SELECT COUNT(*) FROM post_metrics") >= 8
    row = db.fetch_one("SELECT * FROM posts WHERE post_id = ?", (str(fx.BASE_ID + 1),))
    assert row["published_date"] == "2026-11-02" and row["published_time"] == "11:15:00"   # Riyadh = UTC+3
    assert row["first_job_id"] == j1 and row["search_keyword"] == "x"
    acc = db.fetch_one("SELECT * FROM accounts WHERE username = 'fixture_user1'")
    assert acc["followers_count"] == 1000


def test_graphql_capture_upgrades_dom_capture():
    jid = models.create_job("j", "keyword", "x", ["x"], {})
    dom = post_from_dom({"post_id": str(fx.BASE_ID + 1), "username": "fixture_user1", "text": "partial", "likes": "5"})
    cm.store_batch(jid, "x", [dom], [], "UTC", set())
    posts, _ = parse_graphql_payload(fx.search_timeline([fx.tweet(1)]))
    cm.store_batch(jid, "x", posts, [], "UTC", set())
    row = db.fetch_one("SELECT * FROM posts WHERE post_id = ?", (str(fx.BASE_ID + 1),))
    assert row["source"] == "graphql" and "نص اختبار" in row["raw_text"] and row["likes_count"] == 10
    assert row["language"] == "ar"


def test_import_files_har_json_csv(temp_env):
    payload = fx.search_timeline([fx.tweet(i) for i in range(1, 4)])
    har = {"log": {"entries": [{"request": {"url": "https://x.com/i/api/graphql/abc/SearchTimeline?v=1"},
                                "response": {"content": {"text": json.dumps(payload)}}},
                               {"request": {"url": "https://x.com/other"}, "response": {"content": {"text": "{}"}}}]}}
    r = cm.import_file_as_job("har import", "capture.har", fx.to_bytes(har))
    assert r["format"] == "har" and r["received"] == 3 and r["new"] == 3
    assert models.get_job(r["job_id"])["status"] == "completed"
    # re-import our own JSON export → all duplicates
    from analytics.statistics import load_posts
    from exports.service import export_posts
    df = load_posts()
    jpath = export_posts(df, "json", "roundtrip", base=temp_env / "x")
    r2 = cm.import_file_as_job("json import", jpath.name, jpath.read_bytes())
    assert r2["format"] == "export_json" and r2["duplicate"] == 3 and r2["new"] == 0
    cpath = export_posts(df, "csv", "roundtrip", base=temp_env / "y")
    posts, _, fmt = parse_file(cpath.name, cpath.read_bytes())
    assert fmt == "csv" and len(posts) == 3 and posts[0].likes_count is not None
