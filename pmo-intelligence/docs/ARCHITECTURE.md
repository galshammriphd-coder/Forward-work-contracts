# PMO INTELLIGENCE — Architecture, data model and assumptions

## 1. Layers

```
frontend/  React 18 + TypeScript + Vite. Arabic RTL / English LTR, light / dark. No UI kit: tokens in index.css.
   src/lib/core.tsx     API client, language/theme/user context, number-date-currency formatting
   src/lib/ui.tsx       Register (generic list + add + edit + delete), forms, tables, modals
   src/lib/charts.tsx   Bars, paired bars, segments, lines, risk matrix (SVG/HTML, hover tooltips)
   src/pages/           19 menu modules + Project Command Center + initiation wizard

backend/app/
   models.py            56 tables (SQLAlchemy 2). PostgreSQL in production, SQLite for zero-setup trials
   security.py          PBKDF2, JWT, TOTP, RBAC, project scope, document clearance, audit()
   engines/             PURE calculation code, no database, no AI
      scheduling.py        CPM: forward/backward pass, FS/SS/FF/SF, lead/lag, calendars, summaries, delay impact
      evm.py               PV EV AC SV CV SPI CPI EAC ETC VAC + S-curve
      risk.py              score, bands, 5×5 matrix, shared-risk de-duplication
      alerts.py            21 early-warning rules
   rag/
      parsers.py           PDF, DOCX, XLSX, PPTX, TXT/MD (+ DOC/XLS via LibreOffice, scanned PDF via Tesseract)
      text.py              Arabic normalisation, stemming, bilingual concept map, injection patterns
      index.py             chunking, EmbeddingProvider, VectorStore, indexing
      retrieval.py         permission filter → BM25 + vector → RRF → rerank
      answer.py            grounded answers + citations, LLMProvider abstraction, summaries, extraction, version diff
      compare.py           document comparison and conflict detection
      facts.py             labelled-fact extraction shared by charter analysis and comparison
   ai/
      charter.py           charter → profile with provenance, missing data, internal conflicts
      generators.py        WBS, schedule (through the engine), risks, 19 document drafts
   services/            database-bound orchestration
      core.py              settings, schedule recalculation, metrics, early-warning sync, dashboard
      knowledge.py         uploads, versions, project chat
      initiation.py        wizard sessions and activation
      automation.py        workflow engine, automation rules, scheduler jobs, retention
      copilot.py           portfolio-level assistant
      reports.py           report model + XLSX / DOCX / PDF renderers
   api_crud.py          one permission-checked CRUD path for 28 registers
   api.py               domain endpoints
   seed.py              reference data + fictional demo data
```

Design rule: **numbers never come from a language model.** Dates, float, critical path, EVM, risk scores and alert decisions are computed by `engines/`, which are plain functions with hand-checked tests. AI-labelled output is limited to *proposals* (WBS structure, risk suggestions, document drafts) that stay in a draft until a person approves each section.

## 2. Data model

Every project-owned table carries `project_id` as a foreign key with `ON DELETE CASCADE`.

```mermaid
erDiagram
  ORGANIZATION ||--o{ DEPARTMENT : has
  ROLE ||--o{ USER : assigned
  ROLE }o--o{ PERMISSION : grants
  STRATEGIC_OBJECTIVE ||--o{ PORTFOLIO : guides
  PORTFOLIO ||--o{ PROGRAM : contains
  PROGRAM ||--o{ PROJECT : groups
  PORTFOLIO ||--o{ PROJECT : funds
  PROJECT ||--o{ PROJECT_MEMBER : scope
  USER ||--o{ PROJECT_MEMBER : member
  PROJECT ||--|| PROJECT_CHARTER : approved
  PROJECT ||--o{ PROJECT_PHASE : phases
  PROJECT ||--o{ WBS_ELEMENT : wbs
  PROJECT ||--o{ ACTIVITY : activities
  ACTIVITY ||--o{ ACTIVITY : subtasks
  ACTIVITY ||--o{ DEPENDENCY : predecessor
  PROJECT ||--o{ MILESTONE : milestones
  PROJECT ||--o{ BASELINE : baselines
  PROJECT ||--o{ DELIVERABLE : deliverables
  PROJECT ||--o{ RISK : risks
  RISK ||--o{ RISK_RESPONSE : responses
  RISK }o--o{ ACTIVITY : affects
  RISK }o--o{ DELIVERABLE : affects
  PROJECT ||--o{ ISSUE : issues
  PROJECT ||--o{ CHANGE_REQUEST : changes
  PROJECT ||--o{ DECISION : decisions
  PROJECT ||--o{ BUDGET : budgets
  PROJECT ||--o{ COST : costs
  RESOURCE ||--o{ RESOURCE_ASSIGNMENT : assigned
  PROJECT ||--o{ RESOURCE_ASSIGNMENT : uses
  PROJECT ||--o{ STAKEHOLDER : stakeholders
  ACTIVITY ||--o{ RACI_ASSIGNMENT : raci
  PROJECT ||--o{ KPI : kpis
  PROJECT ||--o{ BENEFIT : benefits
  PROJECT ||--o{ LESSON_LEARNED : lessons
  PROJECT ||--o{ DOCUMENT : documents
  DOCUMENT ||--o{ DOCUMENT_VERSION : versions
  DOCUMENT ||--o{ DOCUMENT_CHUNK : chunks
  DOCUMENT_CHUNK ||--|| EMBEDDING : vector
  PROJECT ||--o{ DOCUMENT_CONFLICT : conflicts
  PROJECT ||--o{ PROJECT_CONVERSATION : chats
  PROJECT_CONVERSATION ||--o{ CONVERSATION_MESSAGE : messages
  WORKFLOW_DEFINITION ||--o{ WORKFLOW_INSTANCE : runs
  WORKFLOW_INSTANCE ||--o{ APPROVAL : steps
  PROJECT ||--o{ ALERT : alerts
  ALERT_RULE ||--o{ ALERT : raises
  AUTOMATION_RULE ||--o{ AUTOMATION_RUN : log
  USER ||--o{ NOTIFICATION : receives
  USER ||--o{ AUDIT_LOG : acts
```

Also: `initiation_sessions` (wizard drafts), `risk_snapshots` (daily counts for the trend chart), `governance_items`, `report_schedules`, `settings`.

## 3. RAG pipeline

```
upload ─ validate type + signature + size
       ─ parse (pages, sections, tables; OCR for scanned PDF pages)
       ─ chunk (≈900 chars, sentence overlap, tables kept whole with their header)
       ─ flag instruction-like passages (prompt-injection patterns, Arabic + English)
       ─ embed (contextual prefix "document › section" + text)
       ─ store chunk + vector with project_id, document_id, version, page, section

question ─ authorise: documents of THIS project that THIS user may read (role clearance, role list, uploader)
         ─ filter: selected documents, date range, version (current | all | n)
         ─ retrieve: BM25 + cosine, fused by reciprocal rank
         ─ rerank: idf-weighted query coverage; approved and (for "current" questions) newest documents first
         ─ evidence test: coverage below 0.5 → "no documented information found"
         ─ answer: supporting lines with [n] citations (file, version, page, section, excerpt, document date)
         ─ label each block: documented / inferred / system data / calculated / generated analysis
         ─ audit: user, question, documents used
```

Isolation is enforced three times: the router checks project access, the retriever builds its candidate set from an authorised document list, and every chunk/vector query filters by `project_id`. `tests/test_rag.py::test_isolation_is_enforced_inside_the_retriever` calls the retriever directly, bypassing the HTTP layer.

"Latest" is decided by the document's own date and approval status, not by upload order.

## 4. Access model

| Level | Mechanism |
|---|---|
| Platform | 22 permissions grouped into 12 roles; editable matrix in Administration |
| Portfolio / programme | `portfolio.read/write`; programme managers see their programmes' projects |
| Project | `Role.all_projects`, else membership, project manager, or programme manager |
| Document | confidentiality 0–3 against role clearance; optional explicit role list; uploader always |
| Operation | read/write permission per register; approvals bound to the step's approver role |

A project outside the user's scope answers `404`, the same as a project that does not exist.

## 5. Assumptions (all changeable)

| Assumption | Where to change |
|---|---|
| Working week Sunday–Thursday | Administration → Platform settings → Working calendar |
| Risk bands 1–4 / 5–9 / 10–14 / 15–25 | Administration → Risk rating limits |
| Currency SAR, Western digits, Gregorian dates | Administration → Organisation and display |
| Early-warning thresholds (SPI/CPI 0.9, stalled approval 5 days, …) | Workflow & Automation → Early-warning rules |
| EVM weighting: explicit weight → cost → duration → equal | `engines/evm.py::weights` |
| Planned value is linear between an activity's start and end | `engines/evm.py::planned_fraction` |
| Project "delayed" = late activity, SPI < 0.9, or forecast past baseline | `services/core.py::project_metrics` |
| Health: red/amber/green from SPI, CPI, overrun, critical risks, late critical work | same function |
| Portfolio score = 40% on-target, 30% mean SPI, 30% mean CPI | `services/core.py::dashboard` |
| Generated WBS: five phases with 10/20/50/13/7% of working time | `ai/generators.py::PHASES` |
| Retention: notifications 180 days, run log and resolved alerts 365 days; audit trail kept | Administration → Data retention |
| Sessions last 8 hours | `PMO_TOKEN_TTL_MINUTES` |

## 6. Extending

- **Neural embeddings**: set `ai.embedding_model` to a sentence-transformers model available locally, then re-index.
- **pgvector / Qdrant**: implement `upsert` and `search` of `rag/index.py::SqlVectorStore` against the new store.
- **Language model**: Administration → AI → OpenAI-compatible endpoint. The model only rewrites already-retrieved evidence; refusal and citations stay with the retriever.
- **New register**: add the model, then one line in `api_crud.py::REG` and a `<Register>` in the frontend.
- **New alert rule**: add it to `engines/alerts.py::RULES` and `evaluate`; it appears in the rules screen after restart.
- **Integrations**: outbound through the automation `webhook` action; inbound through the REST API with a bearer token.

## 7. Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | SQLite file in `backend/data` | e.g. `postgresql+psycopg://user:pass@host:5432/pmo` |
| `PMO_SECRET_KEY` | development key (a warning is printed) | signs sessions; must be set in any real deployment |
| `PMO_DATA_DIR` | `backend/data` | database file (SQLite) and document store |
| `PMO_SEED_DEMO` | `1` | `0` starts with reference data only |
| `PMO_SCHEDULER` | `1` | background jobs: scheduled rules, report schedules, risk snapshots, retention |
| `PMO_MAX_UPLOAD_MB` | `40` | upload size limit |
| `PMO_TOKEN_TTL_MINUTES` | `480` | session length |
| `PMO_LLM_API_KEY` | empty | key for the optional LLM endpoint |
| `PMO_PDF_FONT` | DejaVu Sans if found | TTF with Arabic glyphs for PDF reports |
