"""CSV ingestion & questionnaire-structure detection with different encodings and layouts."""
import pandas as pd

from app.engine.dictionary import build_dictionary
from app.engine.ingest import parse_csv
from app.engine.pipeline import apply_operations, new_op, transform, typed_frame
from app.engine.quality import propose_operations, quality_report

AR_CSV = "الرقم;الجنس;العمر;س1;س2;س3;ملاحظات\n1;ذكر;٣٤;5;4;4;الخدمة جيدة\n2;أنثى;29;3;3;2;\n3;انثى;41;4;5;5;ممتاز جدا\n4;ذكر;38;2;1;2;بطيء\n5;ذكر;27;5;5;4;\n"


def test_semicolon_utf8_bom_and_arabic_digits():
    p = parse_csv(("﻿" + AR_CSV).encode("utf-8"))
    assert p.delimiter == ";" and p.encoding.startswith("utf-8") and p.had_bom
    assert p.n_rows == 5 and p.n_cols == 7
    d = build_dictionary(p.df)
    v = {x["name"]: x for x in d["variables"]}
    assert v["العمر"]["dtype"] == "numeric" and v["العمر"]["role"] == "demographic"
    assert v["الجنس"]["role"] == "demographic"
    assert v["الرقم"]["role"] == "id"
    assert all(v[c]["is_likert"] for c in ("س1", "س2", "س3"))
    t = typed_frame(p.df, d)
    assert t["العمر"].tolist() == [34, 29, 41, 38, 27]


def test_cp1256_encoding():
    p = parse_csv(AR_CSV.replace(";", ",").replace("٣٤", "34").encode("cp1256"))
    assert p.encoding == "cp1256" and "الجنس" in p.df.columns


def test_tab_delimited_and_text_likert_mapping():
    csv = "id\tq1\tq2\tq3\n" + "\n".join(f"{i}\t{a}\t{b}\tAgree" for i, (a, b) in enumerate(
        [("Agree", "Strongly agree"), ("Disagree", "Neutral"), ("Strongly disagree", "Agree"), ("Neutral", "Agree")] * 3))
    p = parse_csv(csv.encode())
    assert p.delimiter == "\t"
    d = build_dictionary(p.df)
    q1 = next(v for v in d["variables"] if v["name"] == "q1")
    assert q1["is_likert"] and q1["value_map"]["Strongly disagree"] == 1 and q1["value_map"]["Agree"] == 4
    t = typed_frame(p.df, d)
    assert t["q1"].iloc[0] == 4.0


def test_unclear_structure_is_not_invented():
    # Full-sentence item names: no prefix pattern -> no dimensions are assumed
    rows = "\n".join(f"{1 + i % 5},{1 + (i + 1) % 5},{1 + (i + 2) % 5},{1 + (i + 3) % 5}" for i in range(15))
    p = parse_csv(("I like the service,Staff are friendly,The app is easy,Prices are fair\n" + rows).encode())
    d = build_dictionary(p.df)
    assert d["dimensions"] == [] and d["structure_confident"] is False and len(d["ungrouped_items"]) == 4


def test_cleaning_is_reviewable_and_original_untouched():
    csv = "id,g,A1,A2,A3,A4,A5\n" + "\n".join(f"{i},{'M' if i % 2 else 'F'},{1 + i % 5},{1 + (i + 1) % 5},{1 + (i + 2) % 5},{1 + i % 4},{2 + i % 3}" for i in range(40))
    csv += "\n40,M,9,3,3,3,3\n41,F,3,3,3,3,3\n41,F,3,3,3,3,3"
    p = parse_csv(csv.encode())
    d = build_dictionary(p.df)
    t = typed_frame(p.df, d)
    q = quality_report(p.df, t, d)
    assert q["out_of_range"] and q["duplicates"]["count"] == 1 and q["straightlining"]
    ops = propose_operations(q, d)
    assert all(o["status"] == "pending" for o in ops)
    clean, log = apply_operations(t, ops, d)  # nothing accepted -> nothing changes
    assert len(clean) == len(t) and log == []
    ops[0]["status"] = "accepted"
    clean, log = apply_operations(t, ops, d)
    assert log and p.df.shape == (43, 7)  # original raw frame unchanged


def test_reverse_coding_and_composites():
    df = pd.DataFrame({"X1": [1, 2, 5], "X2_r": [5, 4, 1], "X3": [1, 3, 5]})
    d = {"variables": [{"name": "X1", "dtype": "numeric", "is_likert": True}, {"name": "X2_r", "dtype": "numeric", "is_likert": True, "reverse": True},
                       {"name": "X3", "dtype": "numeric", "is_likert": True}],
         "dimensions": [{"name": "X", "items": ["X1", "X2_r", "X3"]}], "likert": {"min": 1, "max": 5}}
    out, _ = transform(df, d)
    assert out["X2_r"].tolist() == [1, 2, 5]
    assert out["X"].tolist() == [1, 7 / 3, 5]


def test_manual_operation_types():
    df = pd.DataFrame({"a": [1.0, None, 3.0, 100.0], "name": ["x", "y", "z", "w"]})
    ops = [new_op("impute", {"columns": ["a"], "method": "median"}, "", ""), new_op("pseudonymize", {"columns": ["name"]}, "", "")]
    for o in ops:
        o["status"] = "accepted"
    out, log = apply_operations(df, ops, {})
    assert out["a"].isna().sum() == 0 and out["name"].str.startswith("P-").all()
