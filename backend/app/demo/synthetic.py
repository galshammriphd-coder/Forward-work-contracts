"""Generator for a clearly-labelled SYNTHETIC questionnaire dataset.

The data are simulated from a known latent model purely to demonstrate the platform.
They are NOT results of any real study. Quality problems (duplicates, out-of-range
values, missing answers, straight-lining, speeders, spelling variants) are injected on
purpose so that every cleaning step can be demonstrated.
"""
from __future__ import annotations

import io

import numpy as np
import pandas as pd

SYNTHETIC_NOTICE_EN = "SYNTHETIC DEMO DATA — simulated for demonstration only; not the results of a real study."
SYNTHETIC_NOTICE_AR = "بيانات تجريبية اصطناعية — مولَّدة لأغراض العرض فقط، وليست نتائج دراسة فعلية."

COMMENTS_POS = ["The staff were very helpful and professional", "Fast service and clear procedures", "الخدمة ممتازة والموظفون متعاونون",
                "Easy to use online system, very satisfied", "إجراءات واضحة وسريعة وأنا راض جدا", "Great experience, I like the new app"]
COMMENTS_NEG = ["Long waiting time and slow response", "النظام بطيء وهناك تأخير في الرد", "Procedures are difficult and confusing",
                "Poor communication, I had problems with my request", "الموظفون غير متعاونين والخدمة سيئة", "Too expensive and slow"]
COMMENTS_MIX = ["Service is ok but parking is a problem", "التطبيق جيد لكن يحتاج تحسين", "Please contact me at someone@example.com about my request",
                "Average experience overall", "أحيانا سريع وأحيانا بطيء"]


def generate(n: int = 320, seed: int = 20240501) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    gender = rng.choice(["Male", "Female"], size=n, p=[0.48, 0.52])
    education = rng.choice(["Diploma", "Bachelor", "Master", "PhD"], size=n, p=[0.15, 0.5, 0.25, 0.10])
    department = rng.choice(["Finance", "IT", "HR", "Operations"], size=n)
    age = np.clip(np.round(rng.normal(36, 9, n)), 20, 64)
    exp_years = np.clip(np.round((age - 22) * rng.uniform(0.3, 0.9, n)), 0, 40)
    # latent structure: SQ -> TR -> SAT -> LOY
    sq = rng.normal(0, 1, n) + 0.25 * (education == "PhD")
    tr = 0.55 * sq + rng.normal(0, 0.85, n)
    sat = 0.40 * sq + 0.35 * tr + 0.25 * (gender == "Female") + rng.normal(0, 0.75, n)
    loy = 0.60 * sat + rng.normal(0, 0.8, n)

    def items(latent, k, prefix, loadings, reverse=()):
        out = {}
        for j in range(k):
            raw = 3.3 + 0.95 * loadings[j] * latent + rng.normal(0, 0.62, n)
            if (j + 1) in reverse:
                raw = 6 - raw
            name = f"{prefix}{j + 1}" + ("_r" if (j + 1) in reverse else "")
            out[name] = np.clip(np.round(raw), 1, 5).astype(int)
        return out

    data = {"respondent_id": np.arange(1001, 1001 + n), "gender": gender, "age": age.astype(int), "education": education,
            "department": department, "experience_years": exp_years.astype(int)}
    data.update(items(sq, 5, "SQ", [0.85, 0.8, 0.75, 0.8, 0.7]))
    data.update(items(tr, 4, "TR", [0.8, 0.85, 0.7, 0.75], reverse=(3,)))
    data.update(items(sat, 4, "SAT", [0.85, 0.85, 0.8, 0.75]))
    data.update(items(loy, 3, "LOY", [0.8, 0.85, 0.75]))
    duration = np.round(rng.lognormal(np.log(420), 0.35, n)).astype(int)
    data["duration_sec"] = duration
    comm = []
    for i in range(n):
        if rng.random() < 0.45:
            pool = COMMENTS_POS if sat[i] > 0.5 else COMMENTS_NEG if sat[i] < -0.5 else COMMENTS_MIX
            comm.append(pool[rng.integers(len(pool))])
        else:
            comm.append("")
    data["comments"] = comm
    df = pd.DataFrame(data)
    item_cols = [c for c in df.columns if c[:2] in ("SQ", "TR", "SA", "LO")]
    df = df.astype({c: object for c in item_cols + ["age"]})
    # --- injected data-quality issues (documented) ---
    miss_idx = rng.choice(n, size=int(0.02 * n * len(item_cols)), replace=True)
    miss_col = rng.choice(item_cols, size=len(miss_idx))
    for i, c in zip(miss_idx, miss_col):
        df.at[i, c] = ""
    df.at[5, "SQ2"] = 6           # out of range
    df.at[17, "SAT3"] = 0         # out of range
    df.at[40, "age"] = 150        # implausible
    for i in (60, 61, 62, 63):    # straight-liners
        for c in item_cols:
            df.at[i, c] = 3 if not c.endswith("_r") else 3
    for i in (80, 81, 82):        # speeders
        df.at[i, "duration_sec"] = int(rng.integers(35, 70))
    df.at[90, "gender"] = "male "
    df.at[91, "gender"] = "Femal"
    df.at[92, "gender"] = "female"
    dups = df.iloc[[100, 101, 102]].copy()
    dups["respondent_id"] = dups["respondent_id"]  # exact copies incl. id
    df = pd.concat([df, dups], ignore_index=True)
    return df


def demo_csv_bytes(n: int = 320, seed: int = 20240501) -> bytes:
    buf = io.StringIO()
    generate(n, seed).to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8-sig")


if __name__ == "__main__":  # pragma: no cover
    import sys
    sys.stdout.write(demo_csv_bytes().decode("utf-8-sig"))
