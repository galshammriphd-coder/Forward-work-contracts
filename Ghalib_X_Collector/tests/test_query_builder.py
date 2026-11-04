import pytest

from search.query_builder import SearchParams, build_queries, clean_username, normalize_keyword_query, search_url


def test_keyword_boolean_translation():
    assert normalize_keyword_query("التحول الرقمي AND البيانات") == "التحول الرقمي البيانات"
    assert normalize_keyword_query('"Artificial Intelligence" OR AI NOT crypto') == '"Artificial Intelligence" OR AI -crypto'
    assert normalize_keyword_query("OR ذكاء OR") == "ذكاء"


def test_hashtag_modes():
    p = SearchParams(search_type="hashtag", hashtags=["#الذكاء_الاصطناعي", "رؤية_السعودية_2030"])
    assert build_queries(p) == ["(#الذكاء_الاصطناعي OR #رؤية_السعودية_2030)"]
    p.hashtag_mode = "all"
    assert build_queries(p) == ["#الذكاء_الاصطناعي #رؤية_السعودية_2030"]
    p.hashtag_mode = "separate"
    assert build_queries(p) == ["#الذكاء_الاصطناعي", "#رؤية_السعودية_2030"]


def test_user_search_with_dates_and_topic():
    p = SearchParams(search_type="user", usernames=["@acc_one", "https://x.com/acc_two/status/1"], keywords="ذكاء",
                     since="2026-01-01", until="2026-01-31")
    qs = build_queries(p)
    assert qs == ["from:acc_one ذكاء since:2026-01-01 until:2026-02-01", "from:acc_two ذكاء since:2026-01-01 until:2026-02-01"]
    p.user_mode = "combined"
    assert build_queries(p)[0].startswith("(from:acc_one OR from:acc_two)")


def test_advanced_filters():
    p = SearchParams(search_type="advanced", keywords="بيانات", exact_phrase="التحول الرقمي", any_words="AI ذكاء",
                     exclude_words="إعلان تسويق", lang="ar", post_type="no_replies", min_likes=10, to_user="acc",
                     mention_user="other")
    q = build_queries(p)[0]
    for part in ('"التحول الرقمي"', "(AI OR ذكاء)", "-إعلان", "-تسويق", "lang:ar", "-filter:replies", "min_faves:10",
                 "to:acc", "@other"):
        assert part in q


def test_validation_errors():
    with pytest.raises(ValueError):
        build_queries(SearchParams(search_type="hashtag"))
    with pytest.raises(ValueError):
        build_queries(SearchParams(search_type="keyword", keywords=""))
    with pytest.raises(ValueError):
        build_queries(SearchParams(search_type="keyword", keywords="x", since="2026-02-01", until="2026-01-01"))
    with pytest.raises(ValueError):
        clean_username("اسم عربي")
    with pytest.raises(ValueError):
        build_queries(SearchParams(search_type="keyword", keywords="-a -b"))


def test_search_url_encoding():
    url = search_url("#الذكاء_الاصطناعي lang:ar", "live")
    assert url.startswith("https://x.com/search?q=%23") and url.endswith("&f=live")
    assert "f=live" not in search_url("x", "top")
