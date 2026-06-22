# Product Requirements Document — KPI Extraction Platform

| | |
|---|---|
| **Product** | KPI Extraction Platform |
| **Repository** | https://github.com/SohanBiswasSB/KPI_Extraction |
| **Status** | Consolidated MVP — table-extraction engine complete, platform shell reused |
| **Last updated** | 2026-06-23 |
| **Owner** | Sohan Biswas |

---

## 1. Summary

The KPI Extraction Platform ingests business documents and extracts the **tables**
inside them as structured, machine-readable data. Users upload PDFs (digital or
scanned), spreadsheets, and Word documents; the platform detects every table,
preserves its rows and columns, lets users review the result, and exports it to
Excel/CSV. On top of this, optional AI services name KPIs and enable semantic search.

This document defines the requirements for the **consolidated** product, which unifies
four earlier prototypes into one codebase.

## 2. Problem & motivation

- Critical business data (financials, operational metrics, KPIs) is trapped inside
  documents as tables that are tedious and error-prone to re-key by hand.
- Generic "PDF-to-text" tools flatten tables, destroying the row/column structure that
  makes the data usable.
- Prior internal prototypes each solved one slice (a UI, a PDF table parser, an OCR
  script, a RAG chatbot) but none was a single, coherent, end-to-end product.

**Goal:** one platform that reliably converts document tables — across all common
formats, including scanned pages — into clean structured data with minimal manual effort.

## 3. Goals & non-goals

### Goals
1. Extract structured tables (rows × columns preserved) from PDF, scanned/image PDF,
   Excel, CSV, and Word.
2. Automatically fall back to OCR for scanned/image documents.
3. Provide review (preview in-app) and export (XLSX + CSV) of extracted tables.
4. Reuse the existing platform shell (auth, organizations, dashboards, file management).
5. Run without hard dependencies on paid AI — extraction must work offline/keyless.

### Non-goals (this phase)
- Full document Q&A / chatbot (the RAG prototypes are archived, not shipped).
- Editing/correcting cells in-app (export-then-edit for now).
- Non-tabular data extraction (paragraph entity extraction, signatures, stamps).
- Real-time collaborative editing.

## 4. Users & use cases

| Persona | Need |
|---------|------|
| **Analyst** | Upload a quarterly report PDF and get the financial tables as Excel without retyping. |
| **Operations manager** | Batch-ingest scanned vendor docs and recover the line-item tables via OCR. |
| **Admin** | Manage org members and see what's been processed across the team. |
| **Viewer** | Browse and download already-extracted tables. |

## 5. Functional requirements

### 5.1 Ingestion & extraction (core)
- **FR-1** Accept upload of `.pdf, .xlsx, .xls, .csv, .docx, .png, .jpg, .jpeg, .tif, .tiff`.
- **FR-2** For born-digital PDFs, run pdfplumber with both a ruled (`lines`) and a
  whitespace (`text`) strategy and keep whichever recovers more cells.
- **FR-3** For PDFs/images with no native tables, automatically render and run Tesseract
  OCR, then reconstruct rows (vertical clustering) and columns (x-band assignment).
- **FR-4** For Excel/CSV/DOCX, preserve native table structure (no text flattening).
- **FR-5** Represent every result in one common `ExtractedTable` shape carrying page,
  index, source backend, sheet name, confidence, and the full grid.
- **FR-6** Persist extracted tables (`extracted_tables`) linked to the source file;
  reprocessing replaces prior results idempotently.

### 5.2 Review & export
- **FR-7** `GET /files/{id}/tables` returns stored tables; `/tables/preview` previews
  straight off disk without persisting.
- **FR-8** `GET /files/{id}/tables/export` returns a multi-sheet XLSX (one sheet per
  table) plus per-table CSVs.
- **FR-9** The UI renders each table as an HTML table, labels its source and confidence,
  flags low-confidence (OCR) tables, and offers one-click XLSX export.

### 5.3 Platform (reused shell)
- **FR-10** JWT auth, role-based access (Admin/Manager/Analyst/Viewer), multi-tenant orgs.
- **FR-11** File listing, status, download, delete.
- **FR-12** Optional: AI KPI naming and pgvector semantic search when `OPENAI_API_KEY` set.

### 5.4 Tooling
- **FR-13** A standalone CLI (`scripts/extract_tables_cli.py`) runs the engine with no DB
  or server, for verification and scripting.

## 6. Non-functional requirements
- **Resilience:** missing OCR or AI dependencies must degrade gracefully, never crash the
  pipeline. AI/embedding failures are logged and skipped.
- **Security:** all DB access via SQLAlchemy ORM/parameterized queries (the legacy
  f-string SQL — an injection risk — has been removed); uploaded-file type validation.
- **Portability:** core extraction depends only on pdfplumber/pandas/openpyxl/python-docx;
  OCR deps are additive.
- **Observability:** per-file processing metadata records table/KPI counts and errors.

## 7. Success metrics
- ≥ 90% of tables in a born-digital test PDF recovered with correct column count.
- Scanned-PDF fallback produces a usable grid (manually verifiable) for standard layouts.
- Zero pipeline crashes when OCR/AI dependencies or keys are absent.
- Round-trip: upload → view → export XLSX works for all six input categories.

## 8. Architecture (high level)
- **Frontend:** Next.js 14 + Tailwind. `TableViewer` component fetches and renders tables.
- **Backend:** FastAPI (async) + SQLAlchemy + Postgres/pgvector + Redis.
- **Engine:** `app/services/table_extraction/` — format router with OCR fallback and
  XLSX/CSV export; format backends for PDF, OCR, and office files.
- **Data:** `uploaded_files`, `extracted_tables`, `extracted_kpis`, `document_embeddings`.

## 9. Open questions / future work
- In-app cell correction & re-export.
- Table-region detection model (layout-aware) to improve OCR column inference.
- Confidence-driven human-in-the-loop review queue.
- Re-introduce document Q&A by pointing the archived RAG pipeline at extracted tables.
- Background job processing (Celery) for large batches.

## 10. Out-of-scope archived assets
The three RAG/chatbot prototypes and the duplicate platform copy are retained under the
top-level `Old Code/` directory for reference only; they are not part of the shipped
product. See [`CONSOLIDATION.md`](CONSOLIDATION.md).
