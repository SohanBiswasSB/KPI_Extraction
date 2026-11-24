# KPI Extraction Platform

> Consolidated, AI-assisted platform for **extracting structured tables from documents**
> (PDF, scanned/image PDF, Excel, CSV, Word) and turning them into reviewable, exportable data.

Repository: https://github.com/SohanBiswasSB/KPI_Extraction

This repo is the **single consolidated codebase**. It merges several earlier prototypes
(a full Next.js/FastAPI platform shell, a pdfplumber table backend, an OCR bounding-box
script, and assorted RAG experiments) into one product. See [`docs/PRD.md`](docs/PRD.md)
for the product requirements and [`docs/CONSOLIDATION.md`](docs/CONSOLIDATION.md) for what
came from where.

---

## What it does

Upload a document -> the **unified extraction engine** detects and extracts every table,
preserving real rows and columns -> tables are stored, previewed in the UI, and exportable
to a multi-sheet XLSX / per-table CSV. Best-effort KPI extraction and semantic search run
on top when an OpenAI key is configured.

### Supported inputs

| Input | Backend | Notes |
|-------|---------|-------|
| Born-digital PDF | `pdfplumber` (dual line/text strategy) | Picks whichever strategy yields more cells |
| Scanned / image PDF | Vision-LLM (Qwen2.5-VL) **or** PyMuPDF + Tesseract OCR | VLM used first when `ENABLE_VLM=true`; OCR otherwise |
| Images (PNG/JPG/TIFF) | Vision-LLM or Tesseract OCR | Same fallback chain as scanned PDFs |
| Excel (`.xlsx`, `.xls`) | pandas | One table per sheet, structure preserved |
| CSV | pandas | Header + rows preserved |
| Word (`.docx`) | python-docx | Every `<w:tbl>` becomes a table |

Everything returns the same `ExtractedTable` shape, so storage, export, and the UI are
format-agnostic.

---

## Architecture

```
KPI EXTRACTION/
+-- backend/                       # FastAPI + SQLAlchemy (async) + Postgres/pgvector
|   +-- app/
|   |   +-- services/
|   |   |   +-- table_extraction/   #  the unified engine
|   |   |   |   +-- engine.py        #   format router + OCR fallback + XLSX/CSV export
|   |   |   |   +-- pdf_tables.py    #   pdfplumber (born-digital PDFs)
|   |   |   |   +-- ocr_tables.py    #   PyMuPDF + Tesseract (scanned PDFs/images)
|   |   |   |   +-- office_tables.py #   Excel / CSV / DOCX
|   |   |   |   +-- models.py        #   common ExtractedTable dataclass
|   |   |   +-- file_service.py      # ingestion pipeline (ORM-only, no SQL injection)
|   |   |   +-- ai_service.py        # best-effort KPI extraction (OpenAI)
|   |   |   +-- embedding_service.py # best-effort embeddings (pgvector)
|   |   +-- api/v1/endpoints/files.py# upload + /tables, /tables/preview, /tables/export
|   |   +-- models/file.py           # UploadedFile, ExtractedKPI, ExtractedTable
|   |   +-- core/config.py           # OCR + file-type settings
|   +-- scripts/extract_tables_cli.py#  standalone CLI - extract without DB/server
|   +-- init.sql                     # schema incl. extracted_tables
+-- frontend/                        # Next.js 14 + Tailwind
|   +-- src/components/dashboard/TableViewer.tsx  #  renders + exports extracted tables
+-- docker-compose.yml
```

---

## Quick start

### Option A - admin console (recommended)

A single-page admin UI is served by the backend itself at **`/admin/`** - same origin,
so there is no CORS setup and no separate frontend build.

```bash
conda activate KPI_Extraction          # or your venv
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8001
```

Then open **http://127.0.0.1:8001/admin/** and sign in. The console covers upload
(drag & drop), live pipeline progress, extracted tables, KPIs, RAG Q&A, users and
organizations.

Requires a running Postgres with pgvector, Redis, and an OpenAI-compatible LLM server
(see [Local LLM](#local-llm-no-api-keys)). One-time database setup:

```sql
CREATE ROLE kpi_user LOGIN PASSWORD 'kpi_password';
CREATE DATABASE kpi_platform OWNER kpi_user;
\c kpi_platform
CREATE EXTENSION IF NOT EXISTS vector;
\i backend/init.sql
```

### Option B - standalone CLI (no DB, no server)

```bash
cd backend
python scripts/extract_tables_cli.py path/to/report.pdf
python scripts/extract_tables_cli.py data.xlsx --json
python scripts/extract_tables_cli.py scanned.pdf --export ./out   # writes XLSX + CSVs
```

OCR also needs the system Tesseract binary:
`brew install tesseract` (macOS) / `apt-get install tesseract-ocr` (Debian/Ubuntu).

### Option C - full platform (Docker)

```bash
docker-compose up -d            # Postgres (+pgvector), Redis, backend, frontend
```

> **Note:** the Next.js frontend in `frontend/` is **not currently buildable** - it imports
> `@/lib/api`, which has never been committed to this repository. Use the `/admin/`
> console instead.

---

## Retrieval pipeline (RAG)

```
PDF --> pdfplumber / OCR --> ExtractedTable rows (jsonb)
                                    |
                          _tables_to_text()
                                    |
              +---------------------+---------------------+
              v                                           v
   LLM windows (24k chars)                    chunks (1k chars, 200 overlap)
   -> KPI extraction                           -> embeddings -> pgvector
```

**Chunking.** Text is split on table boundaries, and each table's header block
(title, `(In millions)`, the year columns) is **repeated into every chunk of that
table**. Without this, a retrieved chunk arrives as unlabelled columns and the model
invents the period and units. Chunks are cleaned first - pdfplumber splits words
across tabs (`Total ne\tt sales`), which is repaired while column breaks are preserved.

**Metadata.** Every chunk stores `source_file`, `page_number`, `table_index`, `parser`
and the nearest `heading`, so answers can be traced back to a page of the PDF.

**Hybrid retrieval.** Queries run against **both** pgvector cosine similarity **and**
Postgres full-text search (`websearch_to_tsquery`, GIN-indexed), fused with Reciprocal
Rank Fusion. Vector search alone misses exact tokens (identifiers, statement line
names); keyword search alone misses paraphrase.

**Grounding.** The answer prompt forbids supplying any period, currency, scale or unit
not present in the retrieved context, and requires figures to be quoted verbatim.

## Key API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/v1/files/upload` | Upload a document; runs the extraction pipeline |
| `GET`  | `/api/v1/files/{id}/tables` | Structured tables (rows/cols) for a file |
| `GET`  | `/api/v1/files/{id}/tables/preview` | Stateless preview straight off disk |
| `GET`  | `/api/v1/files/{id}/tables/export` | Download tables as multi-sheet XLSX |
| `POST` | `/api/v1/files/{id}/reprocess` | Re-run extraction |

---

## Local LLM (no API keys)

Everything runs against a **local OpenAI-compatible server** - no data leaves the machine
and no API key is needed. Defaults target **LM Studio** on port 1234:

| Setting | Default | Notes |
|---|---|---|
| `LLM_BASE_URL` | `http://localhost:1234/v1` | LM Studio; use `:11434/v1` for Ollama |
| `LLM_MODEL` | `qwen2.5-7b-instruct-1m` | ~5s per call, non-reasoning |
| `LLM_EMBEDDING_MODEL` | `text-embedding-embeddinggemma-300m-qat` | **768-dim** |
| `VECTOR_DIMENSION` | `768` | must match the model *and* `vector(768)` in `init.sql` |
| `LLM_THINK_PREFILL` | `""` | see below |

Load both models in LM Studio and start its server. Give the chat model a **32k context**
- extraction sends 24k-char windows, and the default 8k will reject them.

### Reasoning models

Reasoning models (Qwen3, Gemma-4) can spend their entire token budget "thinking" and
return an empty message. Neither `chat_template_kwargs {"enable_thinking": false}` nor a
`/no_think` suffix reliably prevents this through LM Studio. What does work is seeding the
assistant turn with an already-closed think block:

```python
LLM_THINK_PREFILL = "<think>\n\n</think>\n\n"    # 59s/empty -> 7s/correct JSON
```

Leave it as `""` for a plain instruct model such as `qwen2.5-7b-instruct`.

### Changing the embedding model

`VECTOR_DIMENSION`, the model's output size, and `vector(N)` in `backend/init.sql` must
all agree. Switching to a 1024- or 4096-dim embedder means altering both embedding tables,
rebuilding the ivfflat indexes, and re-embedding every document.

### KPI extraction cost

Extraction scans the **whole** document in windows (`KPI_WINDOW_CHARS`,
`KPI_MAX_WINDOWS`), sized automatically from the model's live context. A ~300k-char 10-K
is ~15 windows ~ 6 minutes on a local 7B. Lower `KPI_MAX_WINDOWS` to trade coverage for
speed - skipped windows are logged, never silent.

## Notes & limitations

- **OCR is optional.** If `PyMuPDF`/`pytesseract`/Tesseract aren't installed, born-digital
  PDFs and office formats still work; scanned PDFs simply return no tables (logged, not fatal).
- **The vision path makes scanned-doc extraction depend on the LLM.** It is gated behind
  `ENABLE_VLM` precisely so digital docs and the OCR fallback stay LLM-free.
- **AI is optional.** Without a reachable LLM server, table extraction is unaffected; only
  the KPI-naming and embedding steps are skipped.
- OCR table reconstruction is heuristic (row clustering + column-band assignment) and is
  marked with lower `confidence`; verify low-confidence tables before relying on them.
- The whitespace (`text`) pdfplumber strategy can over-split cells on complex layouts; ruled
  tables (`lines`) are preferred automatically when available.
- **Extracted vs curated KPIs are different tables.** Extraction writes to
  `extracted_kpis` (per-file staging). Nothing lands in `kpis` until you promote it -
  `POST /api/v1/files/{id}/promote-kpis`, or **-> Curated** in the admin console.
  Promotion is idempotent and skips duplicates by name within an organization.
- **Re-extraction replaces, it does not append.** Tables, KPIs and embeddings for a file
  are cleared before a re-run, so a run where the model returns nothing will leave you
  with nothing. Check the log before re-extracting good data.
- **The `frontend/` Next.js app does not build** - `@/lib/api` was never committed. The
  `/admin/` console is the working UI.
- Defaults in `app/core/config.py` (`SECRET_KEY`, `kpi_password`) are development
  placeholders and must be changed before any non-local deployment.

See [`docs/CONSOLIDATION.md`](docs/CONSOLIDATION.md) for migration history and what was archived.
