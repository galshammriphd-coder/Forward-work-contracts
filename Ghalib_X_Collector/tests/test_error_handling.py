import pytest

from browser.browser_manager import BrowserBusy, BrowserManager
from collectors import collection_manager as cm
from collectors.result_importer import parse_file
from database import db, models
from database.models import Post
from exports.service import export_posts, export_report
from analytics.statistics import load_posts
from analytics.topic_modeling import run_topic_model


def test_import_rejects_files_without_posts():
    with pytest.raises(ValueError):
        cm.import_file_as_job("bad", "x.json", b'{"hello": "world"}')
    posts, _, fmt = parse_file("x.csv", b"col1,col2\n1,2\n")
    assert posts == [] and fmt == "csv"
    assert db.fetch_value("SELECT COUNT(*) FROM search_jobs") == 0


def test_invalid_post_ids_rejected():
    with pytest.raises(ValueError):
        models.save_post(Post(post_id="abc"), None, None)


def test_start_job_guards():
    with pytest.raises(ValueError):
        cm.start_job(999)
    r = cm.import_file_as_job("imp", "a.csv", "Post ID,Post Text,Username\n1850000000000000001,hello,u\n".encode())
    with pytest.raises(ValueError):
        cm.start_job(r["job_id"])       # imports are not browser jobs
    jid = models.create_job("j", "keyword", "x", ["x"], {})
    with pytest.raises(RuntimeError):
        cm.start_job(jid, resume=True)  # cannot resume a job that never ran


def test_unsupported_export_format(temp_env):
    with pytest.raises(ValueError):
        export_posts(load_posts(), "docx", "x")
    with pytest.raises(ValueError):
        export_report({}, "csv", "x")


def test_topic_model_needs_enough_data():
    with pytest.raises(ValueError):
        run_topic_model(load_posts(), n_topics=5)


def test_browser_errors_are_forwarded_and_busy_is_reported():
    bm = BrowserManager()
    try:
        with pytest.raises(ZeroDivisionError):
            bm.call(lambda b: 1 / 0, timeout=10)
        assert "ZeroDivisionError" in bm.last_error
        bm.busy_with = "job:1"
        with pytest.raises(BrowserBusy):
            bm.call(lambda b: None, timeout=5)
        assert bm.check_status()["busy"] == "job:1"     # cached status instead of blocking
        bm.busy_with = None
        assert bm.call(lambda b: 42, timeout=10) == 42  # worker thread still alive after an error
    finally:
        bm.shutdown()
