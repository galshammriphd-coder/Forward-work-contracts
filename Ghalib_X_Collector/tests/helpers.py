"""Builds a temporary test corpus (fixture data, see tests/fixtures.py)."""
from collectors import collection_manager as cm
from collectors.result_importer import parse_graphql_payload
from database import models
from processing.pipeline import run_pipeline
from tests import fixtures as fx

TOPICS = [
    ("الذكاء الاصطناعي يغير التعليم والتعلم في الجامعات بشكل رائع وممتاز", ["الذكاء_الاصطناعي", "التعليم"]),
    ("مشكلة كبيرة في انقطاع الخدمة وتأخير سيء في الاستجابة للعملاء", ["الخدمات"]),
    ("وزارة الصحة تطلق مبادرة جديدة للصحة الرقمية في الرياض", ["الصحة_الرقمية"]),
    ("Artificial intelligence and machine learning improve healthcare outcomes", ["AI", "Health"]),
    ("مؤتمر التقنية في جدة يناقش البيانات الضخمة والحوسبة السحابية", ["البيانات", "الحوسبة"]),
]


def seed(n: int = 60, job_name: str = "fixture corpus", days: int = 6) -> int:
    jid = models.create_job(job_name, "keyword", "fixture", ["fixture"], {"keywords": "fixture"})
    tweets = []
    for i in range(1, n + 1):
        text, tags = TOPICS[i % len(TOPICS)]
        day = 2 + (i % days)
        lang = "en" if i % len(TOPICS) == 3 else "ar"
        tweets.append(fx.tweet(i, author=1 + i % 7, text=f"{text} (عينة اختبار {i})", lang=lang, hashtags=tags,
                               created=f"Mon Nov {day:02d} {8 + i % 12:02d}:15:00 +0000 2026", likes=i * 3))
    posts, accs = parse_graphql_payload(fx.search_timeline(tweets))
    cm.store_batch(jid, "fixture", posts, accs, "Asia/Riyadh", set())
    run_pipeline(job_id=jid)
    return jid
