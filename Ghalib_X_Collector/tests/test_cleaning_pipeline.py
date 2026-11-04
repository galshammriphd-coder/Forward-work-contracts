from database import db, models
from database.models import Post
from processing import cleaning
from processing.language_detection import detect_language
from processing.pipeline import run_pipeline


def test_arabic_text_cleaning():
    raw = "  مرحبـــا‏ بكم &amp; أهلاً   في  #رؤية_السعودية_2030!!!!!!  https://t.co/xyz ​"
    out = cleaning.clean_text(raw)
    assert out == "مرحبا بكم & أهلاً في #رؤية_السعودية_2030!!!"
    norm = cleaning.analysis_text("الإمارات وأبوظبي مُبَارَكٌ ١٢٣ @user https://x.com")
    assert "الامارات" in norm and "مبارك" in norm and "user" not in norm and "١٢٣" not in norm


def test_hashtag_and_mention_extraction():
    # Same boundary rule as X: a letter glued before "#" (e.g. "و#") does not start a hashtag.
    t = "#الذكاء_الاصطناعي و #AI مع @user_1 و email@test.com و #2030 و#غير_وسم (#رؤية_السعودية_2030)"
    assert cleaning.extract_hashtags(t) == ["الذكاء_الاصطناعي", "AI", "رؤية_السعودية_2030"]
    assert cleaning.extract_mentions(t) == ["user_1"]
    assert cleaning.normalize_hashtag("#الإبتكار") == "الابتكار"


def test_counts_and_dates():
    assert cleaning.parse_count("1,234") == 1234
    assert cleaning.parse_count("12.5K") == 12500
    assert cleaning.parse_count("3M") == 3_000_000
    assert cleaning.parse_count("١٫٢ ألف") == 1200
    assert cleaning.parse_count("") is None
    assert cleaning.parse_x_datetime("Wed Oct 10 20:19:24 +0000 2018") == "2018-10-10T20:19:24+00:00"
    assert cleaning.parse_x_datetime("2026-11-01T09:00:00.000Z") == "2026-11-01T09:00:00+00:00"
    assert cleaning.parse_x_datetime("1700000000000") == "2023-11-14T22:13:20+00:00"
    assert cleaning.parse_x_datetime("garbage") is None
    assert cleaning.local_date_time("2026-11-01T22:30:00+00:00", "Asia/Riyadh") == ("2026-11-02", "01:30:00")
    assert cleaning.is_valid_url("https://example.org/a?b=1") and not cleaning.is_valid_url("javascript:alert(1)")


def test_language_detection():
    assert detect_language("الذكاء الاصطناعي في السعودية") == "ar"
    assert detect_language("Artificial intelligence is the future of the world") == "en"
    assert detect_language("hello", x_lang="fr") == "fr"
    assert detect_language("#AI 😂", x_lang="und") == "en"
    assert detect_language("😂😂") == "und"
    assert detect_language("نوشتن فارسی پیچیده گچ") == "fa"


def test_pipeline_end_to_end():
    jid = models.create_job("j", "keyword", "x", ["x"], {})
    base = 1850000000000000000
    long = "هذا نص طويل بما يكفي ليتم اكتشافه كنص مكرر في الحملات المنسقة"
    posts = [
        Post(post_id=str(base + 1), raw_text=long + " #حملة", username="a", published_at="2026-11-01T10:00:00+00:00",
             hashtags=[], urls=["https://ok.example/x", "not a url"]),
        Post(post_id=str(base + 2), raw_text=long + " #حملة", username="b", published_at="2026-11-01T11:00:00+00:00"),
        Post(post_id=str(base + 3), raw_text="", username="c", published_at="2026-11-01T12:00:00+00:00"),
        Post(post_id=str(base + 4), raw_text="Short english post about #AI", username="d", language="en"),
    ]
    for p in posts:
        models.save_post(p, jid, "x")
    r = run_pipeline(job_id=jid)
    assert r["records"] == 4 and r["invalid"] == 1 and r["content_duplicates"] == 1
    rows = {x["post_id"]: x for x in db.fetch_all("SELECT * FROM posts")}
    p1, p2, p3, p4 = (rows[str(base + i)] for i in range(1, 5))
    assert p1["hashtags_json"] == '["حملة"]' and p1["urls_json"] == '["https://ok.example/x"]'
    assert p1["raw_text"] == long + " #حملة"                       # original kept
    assert "duplicate_text_of:" + str(base + 1) in p2["validation_notes"]
    assert p3["is_valid"] == 0 and "empty_content" in p3["validation_notes"]
    assert p4["detected_language"] == "en" and "date_not_available" in p4["validation_notes"]
    assert db.fetch_value("SELECT post_count FROM hashtags WHERE tag = 'حمله'") == 2
    steps = [x["step"] for x in db.fetch_all("SELECT step FROM processing_logs WHERE run_id = ? ORDER BY id", (r["run_id"],))]
    assert steps == ["validate", "deduplicate", "clean_text", "whitespace", "hashtags", "mentions", "language",
                     "datetime", "urls", "missing_values", "document"]
    assert models.get_job(jid)["processed_count"] == 4
    assert run_pipeline(job_id=jid)["records"] == 0      # idempotent
