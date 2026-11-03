"""Numerical validation against reference outputs of R (stats package), whose results
match SPSS for these procedures. Reference values are quoted from R's documented
examples / standard datasets (sleep, iris, RoundingTimes, Job satisfaction tables)."""
import numpy as np
import pandas as pd
import pytest
from sklearn.datasets import load_iris

from app.engine.descriptive import describe, normality
from app.engine.reliability import cronbach_alpha
from app.engine.runner import run_analysis

SLEEP_1 = [0.7, -1.6, -0.2, -1.2, -0.1, 3.4, 3.7, 0.8, 0.0, 2.0]
SLEEP_2 = [1.9, 0.8, 1.1, 0.1, -0.1, 4.4, 5.5, 1.6, 4.6, 3.4]


def _dict(df, levels=None):
    levels = levels or {}
    return {"variables": [{"name": c, "label": c, "dtype": "numeric" if pd.api.types.is_numeric_dtype(df[c]) else "categorical",
                           "level": levels.get(c, "ratio" if pd.api.types.is_numeric_dtype(df[c]) else "nominal"), "role": "other"} for c in df.columns],
            "dimensions": [], "likert": {"min": 1, "max": 5, "interpretation": []}}


@pytest.fixture
def sleep():
    return pd.DataFrame({"extra": SLEEP_1 + SLEEP_2, "group": ["1"] * 10 + ["2"] * 10})


@pytest.fixture
def iris():
    d = load_iris(as_frame=True)
    df = d.frame.rename(columns={"sepal length (cm)": "SL", "sepal width (cm)": "SW", "petal length (cm)": "PL", "petal width (cm)": "PW"})
    df["species"] = d.target_names[d.target]
    return df.drop(columns="target")


def test_independent_t_welch_and_student(sleep):
    r = run_analysis("ttest_ind", sleep, _dict(sleep), {"dv": "extra", "group": "group"})
    rows = {row["test_en"].split()[0]: row for row in r["tables"][1]["rows"]}
    # R: t.test(extra ~ group, data = sleep)  -> t = -1.8608, df = 17.776, p-value = 0.07939
    assert rows["Welch's"]["t"] == pytest.approx(-1.8608, abs=1e-4)
    assert rows["Welch's"]["df"] == pytest.approx(17.776, abs=1e-3)
    assert rows["Welch's"]["p"] == pytest.approx(0.07939, abs=1e-5)
    assert rows["Welch's"]["ci_low"] == pytest.approx(-3.3654832, abs=1e-6)
    # R: t.test(..., var.equal = TRUE) -> df = 18, p-value = 0.07919
    assert rows["Student's"]["df"] == 18
    assert rows["Student's"]["p"] == pytest.approx(0.07919, abs=1e-5)


def test_paired_t(sleep):
    df = pd.DataFrame({"a": SLEEP_1, "b": SLEEP_2})
    r = run_analysis("ttest_paired", df, _dict(df), {"var1": "a", "var2": "b"})
    s = r["stats"]
    # R: t.test(sleep$extra[1:10], sleep$extra[11:20], paired = TRUE) -> t = -4.0621, df = 9, p-value = 0.002833
    assert s["t"] == pytest.approx(-4.0621, abs=1e-4)
    assert s["df"] == 9
    assert s["p"] == pytest.approx(0.002833, abs=1e-6)
    assert s["ci_low"] == pytest.approx(-2.4598858, abs=1e-6) and s["ci_high"] == pytest.approx(-0.7001142, abs=1e-6)


def test_mann_whitney(sleep):
    r = run_analysis("mannwhitney", sleep, _dict(sleep), {"dv": "extra", "group": "group"})
    # R: wilcox.test(extra ~ group, data = sleep, exact = FALSE) -> W = 25.5, p-value = 0.06933
    assert r["stats"]["U"] == pytest.approx(25.5)
    assert r["stats"]["p"] == pytest.approx(0.06933, abs=1e-5)


def test_one_way_anova_and_welch(iris):
    r = run_analysis("anova", iris, _dict(iris), {"dv": "SL", "group": "species"})
    s = r["stats"]
    # R: summary(aov(Sepal.Length ~ Species, iris)) -> F = 119.3 on 2 and 147 df; SS = 63.21, 38.96
    assert s["F"] == pytest.approx(119.26, abs=0.01)
    assert (s["df1"], s["df2"]) == (2, 147)
    assert r["tables"][1]["rows"][0]["ss"] == pytest.approx(63.21, abs=0.01)
    # R: oneway.test(Sepal.Length ~ Species, iris) -> F = 138.91, num df = 2, denom df = 92.211
    assert s["welch_F"] == pytest.approx(138.91, abs=0.01)
    assert s["welch_df2"] == pytest.approx(92.211, abs=1e-3)
    assert s["eta2"] == pytest.approx(63.2121 / (63.2121 + 38.9562), abs=1e-4)


def test_kruskal(iris):
    r = run_analysis("kruskal", iris, _dict(iris), {"dv": "SL", "group": "species"})
    # R: kruskal.test(Sepal.Length ~ Species, iris) -> chi-squared = 96.937, df = 2
    assert r["stats"]["H"] == pytest.approx(96.937, abs=1e-3)
    assert r["stats"]["df"] == 2


def test_pearson_correlation(iris):
    r = run_analysis("correlation", iris, _dict(iris), {"variables": ["SL", "PL"], "method": "pearson"})
    p = r["stats"]["pairs"][0]
    # R: cor.test(iris$Sepal.Length, iris$Petal.Length) -> r = 0.8717538, 95% CI 0.8270363 0.9055080
    assert p["r"] == pytest.approx(0.8717538, abs=1e-7)
    assert p["ci_low"] == pytest.approx(0.8270363, abs=1e-6)
    assert p["ci_high"] == pytest.approx(0.9055080, abs=1e-6)


def test_spearman_kendall_match_scipy(iris):
    from scipy import stats
    for m, fn in [("spearman", stats.spearmanr), ("kendall", stats.kendalltau)]:
        r = run_analysis("correlation", iris, _dict(iris), {"variables": ["SL", "SW"], "method": m})
        assert r["stats"]["pairs"][0]["r"] == pytest.approx(fn(iris["SW"], iris["SL"])[0], abs=1e-12)


def test_simple_regression(iris):
    r = run_analysis("linear", iris, _dict(iris), {"dv": "PW", "ivs": ["PL"]})
    co = {c["term"]: c for c in r["stats"]["coefficients"]}
    # R: lm(Petal.Width ~ Petal.Length, iris) -> (Intercept) -0.363076, slope 0.415755, R2 0.9271
    assert co["(Intercept)"]["B"] == pytest.approx(-0.363076, abs=1e-6)
    assert co["PL"]["B"] == pytest.approx(0.415755, abs=1e-6)
    assert r["stats"]["r2"] == pytest.approx(0.9271, abs=1e-4)


def test_shapiro_and_descriptives(iris):
    n = normality(iris["SL"])
    # R: shapiro.test(iris$Sepal.Length) -> W = 0.97609, p-value = 0.01018
    assert n["shapiro_w"] == pytest.approx(0.97609, abs=1e-5)
    assert n["shapiro_p"] == pytest.approx(0.01018, abs=1e-5)
    d = describe(iris["SL"])
    # SPSS / e1071::skewness(type = 2): 0.3149110 ; kurtosis(type = 2): -0.5520640
    assert d["skewness"] == pytest.approx(0.3149110, abs=1e-6)
    assert d["kurtosis"] == pytest.approx(-0.5520640, abs=1e-6)
    assert d["mean"] == pytest.approx(5.843333, abs=1e-6) and d["sd"] == pytest.approx(0.8280661, abs=1e-7)


def test_chisquare_r_example():
    # R ?chisq.test: M <- as.table(rbind(c(762, 327, 468), c(484, 239, 477))) -> X-squared = 30.07, df = 2, p = 2.954e-07
    rows = []
    for g, counts in [("F", [762, 327, 468]), ("M", [484, 239, 477])]:
        for party, c in zip(["Democrat", "Independent", "Republican"], counts):
            rows += [{"gender": g, "party": party}] * c
    df = pd.DataFrame(rows)
    r = run_analysis("chisquare", df, _dict(df), {"var1": "gender", "var2": "party"})
    assert r["stats"]["chi2"] == pytest.approx(30.0701, abs=1e-3)
    assert r["stats"]["df"] == 2
    assert r["stats"]["p"] == pytest.approx(2.954e-07, rel=1e-3)


def test_fisher_tea_tasting():
    # R ?fisher.test TeaTasting matrix(c(3, 1, 1, 3)) -> p-value = 0.4857
    df = pd.DataFrame([{"a": "Milk", "b": "Milk"}] * 3 + [{"a": "Milk", "b": "Tea"}] + [{"a": "Tea", "b": "Milk"}] + [{"a": "Tea", "b": "Tea"}] * 3)
    r = run_analysis("fisher", df, _dict(df), {"var1": "a", "var2": "b"})
    assert r["stats"]["fisher_p"] == pytest.approx(0.4857, abs=1e-4)


def test_mcnemar_continuity_corrected():
    # b = 150, c = 86 discordant pairs (R ?mcnemar.test "Performance" table): Edwards-corrected
    # chi2 = (|b - c| - 1)^2 / (b + c) = 63^2 / 236 = 16.8178, df = 1
    from scipy import stats
    rows = [{"s1": "Approve", "s2": "Approve"}] * 794 + [{"s1": "Disapprove", "s2": "Approve"}] * 86 + \
           [{"s1": "Approve", "s2": "Disapprove"}] * 150 + [{"s1": "Disapprove", "s2": "Disapprove"}] * 570
    df = pd.DataFrame(rows)
    r = run_analysis("mcnemar", df, _dict(df), {"var1": "s1", "var2": "s2"})
    assert r["stats"]["statistic"] == pytest.approx(63 ** 2 / 236, abs=1e-9)
    assert r["stats"]["p"] == pytest.approx(stats.chi2.sf(63 ** 2 / 236, 1), rel=1e-9)


def test_friedman_rounding_times():
    # R ?friedman.test RoundingTimes -> Friedman chi-squared = 11.143, df = 2, p-value = 0.003805
    v = [5.40, 5.50, 5.55, 5.85, 5.70, 5.75, 5.20, 5.60, 5.50, 5.55, 5.50, 5.40, 5.90, 5.85, 5.70, 5.45, 5.55, 5.60, 5.40, 5.40, 5.35, 5.45, 5.50, 5.35,
         5.25, 5.15, 5.00, 5.85, 5.80, 5.70, 5.25, 5.20, 5.10, 5.65, 5.55, 5.45, 5.60, 5.35, 5.45, 5.05, 5.00, 4.95, 5.50, 5.50, 5.40, 5.45, 5.55, 5.50,
         5.55, 5.55, 5.35, 5.45, 5.50, 5.55, 5.50, 5.45, 5.25, 5.65, 5.60, 5.40, 5.70, 5.65, 5.55, 6.30, 6.30, 6.25]
    df = pd.DataFrame(np.array(v).reshape(22, 3), columns=["round", "narrow", "wide"])
    r = run_analysis("friedman", df, _dict(df), {"variables": ["round", "narrow", "wide"]})
    assert r["stats"]["chi2"] == pytest.approx(11.143, abs=1e-3)
    assert r["stats"]["p"] == pytest.approx(0.003805, abs=1e-6)


def test_cronbach_alpha_formula():
    rng = np.random.default_rng(0)
    f = rng.normal(size=500)
    block = pd.DataFrame({f"i{k}": f + rng.normal(scale=1.0, size=500) for k in range(5)})
    k = 5
    manual = k / (k - 1) * (1 - block.var(ddof=1).sum() / block.sum(axis=1).var(ddof=1))
    assert cronbach_alpha(block) == pytest.approx(manual, abs=1e-12)
    import pingouin as pg
    assert cronbach_alpha(block) == pytest.approx(pg.cronbach_alpha(block)[0], abs=1e-10)
    # population value for 5 parallel items with reliability .5 each: 5*.5/(1+4*.5) = .833
    assert cronbach_alpha(block) == pytest.approx(0.833, abs=0.03)
