# Research Analytics AI

**منصة التحليل الإحصائي الذكي للاستبانات والبحوث العلمية** — AI-Powered Survey Analytics & Scientific Research Platform

This is a working web application, not a mock-up. A researcher uploads a questionnaire CSV and the platform runs the whole data-science lifecycle on that file: understanding, cleaning, transformation, EDA, modelling, evaluation and reporting. It shows the results in interactive dashboards and produces an APA 7 report in Arabic or English. Every number is computed by tested statistical libraries from the uploaded data. Nothing in the analysis code is hard-coded, and no number is produced by a language model.

> **Demo data:** "Demo project (synthetic data)" loads a simulated dataset (`backend/app/demo/synthetic.py`). The project name, a banner on every page and every exported report label it as **SYNTHETIC — not the results of a real study**. Uploading a real CSV to the project replaces it.

## Architecture

| Layer | Stack |
|---|---|
| Frontend | React 18, TypeScript, Tailwind CSS, Plotly (interactive charts, PNG/SVG export); full Arabic RTL and English LTR; light and dark themes; responsive |
| Backend | Python, FastAPI (REST), SQLAlchemy 2 (PostgreSQL via `DATABASE_URL`, SQLite by default) |
| Statistical engine | pandas, NumPy, SciPy, statsmodels, pingouin, factor_analyzer, semopy (CFA/SEM), scikit-learn |
| Reports | python-docx (Word), reportlab with Arabic shaping (PDF), openpyxl (Excel), HTML, CSV (zip) |
| Security | PBKDF2 password hashing, bearer sessions, per-user project isolation, Fernet encryption of uploaded files at rest, full audit log |

```
backend/app/
  engine/        ingest · dictionary · quality · pipeline (cleaning/transform) · descriptive · reliability
                 differences · regression · factor · advanced · text · recommender · interpret · runner
  reports/       builder (report document) · render (HTML/PDF/DOCX/XLSX/CSV)
  main.py        REST API      services.py  frames/KPIs/lifecycle      assistant.py  research assistant
frontend/src/    pages (16 menu modules) · components (spec-driven AnalysisRunner, ResultView, Chart)
```

## Running it

```bash
# backend (Python 3.11+)
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

```bash
# frontend (dev server proxies /api to :8000)
cd frontend
npm install
npm run dev
```

Open http://localhost:5173, create an account, then choose **Projects → Create demo project** or upload your own CSV.

To serve both from one process, run `npm run build` once. FastAPI then serves `frontend/dist` at http://localhost:8000.

**Docker with PostgreSQL:** set `RA_ENCRYPTION_KEY` (a Fernet key), then run `docker compose up --build`.

**semopy** sometimes fails to build from its source distribution on recent setuptools versions. If that happens, install `sympy numdifftools` and copy the pure-Python `semopy/` package folder into site-packages. CFA/SEM need semopy; every other analysis works without it.

Environment variables: `DATABASE_URL`, `RA_DATA_DIR`, `RA_ENCRYPTION_KEY`, `RA_ALLOW_REGISTRATION`, `RA_MAX_UPLOAD_MB`, `RA_CORS_ORIGINS`, `RA_PDF_FONT`.

## Usage scenario (steps 1–12)

1. Create a project.
2. Upload a CSV by drag and drop. Encoding is detected (UTF-8, UTF-8 BOM, Windows-1256, …) and so is the delimiter (`,` `;` tab `|`), and the file is previewed before import.
3. The structure is detected: IDs, demographics, Likert items (numeric, or text anchors in Arabic or English), dimensions inferred from item prefixes, reverse-keyed item suggestions (from the column name or a negative item-total r), open-ended questions, multi-select answers and response time.
4. The data dictionary is editable: type, measurement level, role, dimension/axis, reverse coding, Likert range and interpretation bands, and missing-value codes. When the structure is unclear, no dimensions are assumed and the researcher is asked to define them.
5. A quality report lists missing data, duplicates and duplicate IDs, out-of-range values, non-numeric entries, straight-lining, long-string answers, incomplete responses, speeders, univariate and multivariate (Mahalanobis) outliers, spelling variants and implausible values. It ends with a transparent quality index.
6. Cleaning is reviewable. Every operation is proposed as *pending* and the researcher accepts or rejects each one. The original file is immutable (encrypted, read-only, verified by SHA-256), and "Restore original" is always available. Outliers are flagged but never proposed for removal.
7. EDA.
8. The test advisor identifies the IV/DV, measurement levels and number of groups, checks normality and homogeneity of variance on the actual data, and recommends a test with its reasons and alternatives. The test runs only after approval.
9. Hypotheses are tested with α, direction and a Holm correction across the hypothesis family.
10. Results appear in the dashboard, with demographic filters and drill-down from a dimension to its items.
11. Interpretation in APA 7 (Arabic and English) is built only from computed values. The research assistant answers from the stored results, offline.
12. Reports come in five types: comprehensive, APA 7, executive, data quality and hypotheses. Each can be exported as PDF, Word, Excel, CSV or HTML.

## Analyses implemented

Descriptives (SPSS-compatible skewness/kurtosis and quartiles, CIs) · Likert analysis (any number of points, editable bands, item/dimension ranking) · Normality (Shapiro–Wilk, Lilliefors-corrected K–S, Anderson–Darling, Q-Q plots, sample-size-aware decision) · Reliability (α with Feldt CI, standardized α, McDonald's ω, item-total statistics, α-if-deleted, split-half) · Validity (CFA loadings, CR, AVE, Fornell–Larcker, HTMT, KMO, Bartlett) · t-tests (independent with Student/Welch, paired, one-sample), Mann–Whitney, Wilcoxon, one-way/Welch ANOVA (Tukey, Games–Howell, Bonferroni), two-way ANOVA (Type III), repeated-measures ANOVA (Mauchly, Greenhouse–Geisser), Kruskal–Wallis (Dunn), Friedman · Pearson/Spearman/Kendall with CIs and multiplicity correction · Simple, multiple, polynomial and hierarchical regression (VIF, Durbin–Watson, Breusch–Pagan, Cook's D, residual plots), binary logistic (OR, Nagelkerke, Hosmer–Lemeshow, classification), ordinal logistic · EFA (parallel analysis, rotations), PCA, CFA on a pre-specified model (χ², df, CFI, TLI, RMSEA, SRMR), SEM, multi-group (configural) · Mediation (bootstrap), moderation (simple slopes), MANOVA (Box's M), k-means/Ward clustering, LDA, χ², Fisher's exact, McNemar, Kaplan–Meier with log-rank · Open-ended text (PII redaction, keywords, NMF topics, indicative lexicon sentiment, supporting quotes).

## Scientific safeguards

- Each test reports its assumption checks, effect size and CI, and labels whether it is exploratory or confirmatory.
- Statistical significance and practical importance are reported separately.
- A non-significant result is never described as proof of the null hypothesis.
- Correlation is never described as causation.
- α is never presented as evidence of unidimensionality.
- CFA is never inferred from EFA or PCA output.
- Missing-data handling, composite-score rules and sampling limits are written into the report.
- Reproducibility: a manifest records the data hash, dictionary, accepted operations, analyses and library versions, and one click re-runs every analysis and verifies the results are identical.

## Validation

```bash
cd backend
python -m pytest tests -q
```

The suite has 23 tests. `tests/test_validation.py` checks results against reference outputs from R (which match SPSS for these procedures), including:

- Welch and Student t on R's `sleep` data
- paired t
- Mann–Whitney
- one-way and Welch ANOVA, Kruskal–Wallis, Pearson r with its CI, simple regression, Shapiro–Wilk and SPSS skewness/kurtosis on `iris`
- χ² and Fisher's exact on R's documentation examples
- Friedman on `RoundingTimes`
- McNemar and Cronbach's α checked against their formulas

The other tests cover ingestion (encodings, delimiters, Arabic digits, text Likert scales, unclear structure), the reviewable cleaning pipeline, and the full API scenario including project isolation.

## Privacy and governance

- Research data never leaves the server. The research assistant is deterministic and makes no calls to external AI services.
- Projects are isolated per user.
- Uploaded files are encrypted at rest.
- Every action (upload, dictionary edit, cleaning decision, analysis, export) is written to the audit log.
- Identifiers can be pseudonymized and variables dropped through logged operations.
- Deleting a project removes its database rows and its files.
- The platform runs on-premise or self-hosted (Docker).
