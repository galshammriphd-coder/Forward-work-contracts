import sqlite3

import pytest

from database import db, models
from database.models import Post

EXPECTED_TABLES = {"search_jobs", "posts", "accounts", "hashtags", "post_hashtags", "post_metrics", "collection_logs",
                   "processing_logs", "sentiment_results", "topic_results", "exports", "application_settings",
                   "job_posts", "post_sources", "entity_results", "saved_searches", "app_users", "audit_log"}


def test_connection_and_schema():
    tables = set(db.table_counts())
    assert EXPECTED_TABLES <= tables
    assert db.fetch_value("PRAGMA foreign_keys") == 1
    idx = {r["name"] for r in db.fetch_all("SELECT name FROM sqlite_master WHERE type='index'")}
    assert {"idx_posts_username", "idx_posts_published", "idx_post_hashtags_tag"} <= idx


def test_settings_roundtrip():
    assert db.get_setting("timezone") == "Asia/Riyadh"
    db.set_setting("max_posts_per_query", 42)
    assert db.get_setting_int("max_posts_per_query", 0) == 42
    db.set_setting("browser_headless", True)
    assert db.get_setting_bool("browser_headless") is True


def test_create_and_update_job():
    jid = models.create_job("اختبار", "keyword", "ذكاء", ["ذكاء"], {"keywords": "ذكاء"})
    j = models.get_job(jid)
    assert j["status"] == "new" and j["queries"] == ["ذكاء"]
    models.update_job(jid, status="running", progress={"0": {"collected": 3}})
    models.increment_job(jid, received=5, new=4, duplicate=1)
    j = models.get_job(jid)
    assert (j["status"], j["received_count"], j["new_count"], j["duplicate_count"]) == ("running", 5, 4, 1)
    assert j["progress"]["0"]["collected"] == 3
    with pytest.raises(ValueError):
        models.update_job(jid, status="bogus")
    with pytest.raises(ValueError):
        models.create_job(" ", "keyword", "x", ["x"], {})
    with pytest.raises(ValueError):
        models.create_job("a", "keyword", "x", [], {})


def _post(i, user="fixture_a"):
    return Post(post_id=str(1850000000000000000 + i), raw_text=f"test {i}", username=user,
                published_at="2026-11-01T10:00:00+00:00", likes_count=i)


def test_backup_and_restore(temp_env):
    jid = models.create_job("j", "keyword", "x", ["x"], {})
    models.save_post(_post(1), jid, "x")
    backup = db.backup_database()
    assert db.verify_database_file(backup)
    models.save_post(_post(2), jid, "x")
    assert db.fetch_value("SELECT COUNT(*) FROM posts") == 2
    safety = db.restore_database(backup)
    assert db.fetch_value("SELECT COUNT(*) FROM posts") == 1
    assert safety.exists() and "before_restore" in safety.name
    bad = temp_env / "bad.db"
    bad.write_bytes(b"not a database")
    with pytest.raises(ValueError):
        db.restore_database(bad)


def test_delete_job_keeps_shared_posts():
    j1 = models.create_job("j1", "keyword", "x", ["x"], {})
    j2 = models.create_job("j2", "keyword", "y", ["y"], {})
    models.save_post(_post(1), j1, "x")
    models.save_post(_post(2), j1, "x")
    models.save_post(_post(2), j2, "y")   # shared with j2
    r = db.delete_job_data(j1)
    assert r["posts_deleted"] == 1
    assert db.fetch_value("SELECT COUNT(*) FROM posts") == 1
    assert db.fetch_value("SELECT COUNT(*) FROM search_jobs") == 1
    db.delete_all_data()
    assert db.fetch_value("SELECT COUNT(*) FROM posts") == 0
    assert db.get_setting("timezone") == "Asia/Riyadh"   # settings survive


def test_audit_log():
    db.audit("unit_test", "target", {"a": 1})
    row = db.fetch_one("SELECT * FROM audit_log WHERE action = 'unit_test'")
    assert row["target"] == "target" and '"a": 1' in row["details"]
