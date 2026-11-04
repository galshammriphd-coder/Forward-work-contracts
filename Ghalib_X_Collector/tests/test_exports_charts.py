import csv
import json

from openpyxl import load_workbook

from analytics import statistics as stx
from dashboard import charts
from database import db
from exports.common import export_folder, slugify
from exports.report_builder import build_report
from exports.service import export_posts, export_posts_all_formats, export_report
from tests.helpers import seed


def test_data_exports(temp_env):
    jid = seed(25, job_name="بحث #الذكاء_الاصطناعي")
    df = stx.load_posts(job_ids=[jid])
    paths = export_posts_all_formats(df, "بحث #الذكاء_الاصطناعي", job_id=jid)
    folder = paths[0].parent
    assert all(p.parent == folder for p in paths) and folder.parent == temp_env / "exports"
    assert folder.name.startswith("بحث_الذكاء_الاصطناعي_")
    wb = load_workbook(paths[0])
    assert wb.sheetnames == ["Posts", "Accounts", "Hashtags", "Summary"]
    ws = wb["Posts"]
    headers = [c.value for c in ws[1]]
    for h in ("Post ID", "Post Text", "Username", "Display Name", "Profile URL", "Post URL", "Published Date",
              "Published Time", "Language", "Hashtags", "Mentions", "Replies Count", "Reposts Count", "Likes Count",
              "Views Count", "Search Keyword", "Collection Date"):
        assert h in headers
    assert ws.max_row == 26
    with open(paths[1], encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 25 and rows[0]["Post ID"].isdigit()
    data = json.loads(paths[2].read_text(encoding="utf-8"))
    assert data["count"] == 25 and isinstance(data["posts"][0]["hashtags"], list)
    assert db.fetch_value("SELECT COUNT(*) FROM exports") == 3


def test_excel_formula_injection_is_neutralised(temp_env):
    from database import models
    from database.models import Post
    jid = models.create_job("j", "keyword", "x", ["x"], {})
    models.save_post(Post(post_id="1850000000000000001", raw_text="=HYPERLINK(\"http://evil\")", username="u"), jid, "x")
    p = export_posts(stx.load_posts(), "xlsx", "inj")
    cell = load_workbook(p)["Posts"]["B2"].value
    assert cell.startswith("'=")


def test_reports_excel_and_pdf(temp_env):
    jid = seed(60)
    rep = build_report("تقرير اختبار", job_ids=[jid], n_topics=4)
    assert rep["n_posts"] == 60 and len(rep["conclusions"]) >= 5
    assert not rep["topics"].empty and rep["sentiment"]["posts"].sum() == 60
    x = export_report(rep, "xlsx", "تقرير اختبار", job_id=jid)
    wb = load_workbook(x)
    assert "الملخص التنفيذي" in wb.sheetnames and "المشاعر" in wb.sheetnames
    assert len(wb["الهاشتاقات"]._charts) == 1
    p = export_report(rep, "pdf", "تقرير اختبار", job_id=jid)
    head = p.read_bytes()[:5]
    assert head == b"%PDF-" and p.stat().st_size > 10_000
    empty = build_report("فارغ", keyword="لا_يوجد_هذا_النص")
    assert empty["empty"]
    assert export_report(empty, "pdf", "فارغ").exists()


def test_slug_and_folders(temp_env):
    assert slugify('a/b:c*?"<>|#x y') == "a_b_c_x_y"
    f1, _ = export_folder("same")
    f2, _ = export_folder("same")
    assert f1 != f2 and f1.exists() and f2.exists()


def test_charts_build_with_and_without_data():
    seed(30)
    df = stx.load_posts()
    figs = [
        charts.timeline(stx.posts_over_time(df)), charts.languages_pie(stx.language_distribution(df)),
        charts.bar(stx.top_hashtags(df), "hashtag", "posts", "t"), charts.treemap_words(stx.top_words(df)),
        charts.engagement_hist(stx.engagement_distribution(df)), charts.heatmap(stx.hourly_heatmap(df)),
        charts.account_activity(stx.account_activity(df)),
    ]
    for f in figs:
        assert f.to_dict()["data"], "figure must contain traces"
    assert figs[0].to_dict()["data"][0]["y"].sum() == 30 if hasattr(figs[0].to_dict()["data"][0]["y"], "sum") else True
    empty = stx.load_posts(keyword="لا_يوجد")
    e = charts.timeline(stx.posts_over_time(empty))
    assert e.to_dict()["layout"]["annotations"][0]["text"] == "لا توجد بيانات"
    charts.set_dark(True)
    assert charts.bar(stx.top_hashtags(df), "hashtag", "posts", "t").layout.template.layout.paper_bgcolor is not None
    charts.set_dark(False)
