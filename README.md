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

Upload a document → the **unified extraction engine** detects and extracts every table,
preserving real rows and columns → tables are stored, previewed in the UI, and exportable
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
├── backend/                       # FastAPI + SQLAlchemy (async) + Postgres/pgvector
│   ├── app/
│   │   ├── services/
│   │   │   ├── table_extraction/   # ⭐ the unified engine
│   │   │   │   ├── engine.py        #   format router + OCR fallback + XLSX/CSV export
│   │   │   │   ├── pdf_tables.py    #   pdfplumber (born-digital PDFs)
│   │   │   │   ├── ocr_tables.py    #   PyMuPDF + Tesseract (scanned PDFs/images)
│   │   │   │   ├── office_tables.py #   Excel / CSV / DOCX
│   │   │   │   └── models.py        #   common ExtractedTable dataclass
│   │   │   ├── file_service.py      # ingestion pipeline (ORM-only, no SQL injection)
│   │   │   ├── ai_service.py        # best-effort KPI extraction (OpenAI)
│   │   │   └── embedding_service.py # best-effort embeddings (pgvector)
│   │   ├── api/v1/endpoints/files.py# upload + /tables, /tables/preview, /tables/export
│   │   ├── models/file.py           # UploadedFile, ExtractedKPI, ExtractedTable
│   │   └── core/config.py           # OCR + file-type settings
│   ├── scripts/extract_tables_cli.py# ⭐ standalone CLI — extract without DB/server
│   └── init.sql                     # schema incl. extracted_tables
├── frontend/                        # Next.js 14 + Tailwind
│   └── src/components/dashboard/TableViewer.tsx  # ⭐ renders + exports extracted tables
└── docker-compose.yml
```

---

## Quick start

### Option A — standalone CLI (fastest; no DB, no server)

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install pdfplumber pandas openpyxl python-docx        # core
pip install PyMuPDF pytesseract                            # + OCR (needs `tesseract` binary)

python scripts/extract_tables_cli.py path/to/report.pdf
python scripts/extract_tables_cli.py data.xlsx --json
python scripts/extract_tables_cli.py scanned.pdf --export ./out   # writes XLSX + CSVs
```

OCR also needs the system Tesseract binary:
`brew install tesseract` (macOS) / `apt-get install tesseract-ocr` (Debian/Ubuntu).

### Option B — full platform (Docker)

```bash
docker-compose up -d            # Postgres (+pgvector), Redis, backend, frontend
# backend  → http://localhost:8000  (Swagger at /docs)
# frontend → http://localhost:3000
```

### Option C — backend only

```bash
cd backend
pip install -r requirements.txt
export DATABASE_URL=postgresql+asyncpg://kpi_user:kpi_password@localhost:5432/kpi_platform
uvicorn main:app --reload
```

---

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

The LLM steps default to a **local OpenAI-compatible server** (Ollama), so no API key is
needed. Configure via `LLM_BASE_URL` / `LLM_MODEL` / `LLM_VISION_MODEL` / `LLM_EMBEDDING_MODEL`.

```bash
ollama serve
ollama pull qwen2.5:7b-instruct     # KPI structuring (text)
ollama pull qwen2.5vl:7b            # scanned-page tables (vision) — needs ENABLE_VLM=true
ollama pull nomic-embed-text        # embeddings (768-dim; matches init.sql)
```

Set `ENABLE_VLM=true` to send scanned pages to the vision model before OCR. Leaving it off
keeps scanned-doc extraction fully deterministic/offline (Tesseract only). Try the vision
path from the CLI: `python scripts/extract_tables_cli.py scanned.pdf --vlm`.

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

See [`docs/CONSOLIDATION.md`](docs/CONSOLIDATION.md) for migration history and what was archived.
