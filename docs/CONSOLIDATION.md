# Consolidation history

This codebase merges several earlier prototypes (now under the repo-external `Old Code/`
folder) into one product. This note records what came from where and what changed.

## What was merged in

| Source prototype | What it contributed | Status |
|------------------|--------------------|--------|
| `KPIExtractionPlatform-release-nprd` | Platform shell: Next.js frontend, FastAPI backend, auth, orgs, dashboards, Docker, Postgres/pgvector schema | **Base** — kept as the shell |
| `Self_KPI_Extraction/kpi-backend` | pdfplumber dual-strategy table extraction + XLSX/CSV export | Ported into `table_extraction/pdf_tables.py` + `engine.py` |
| `text_bbox.py` | PyMuPDF render + Tesseract OCR with word boxes | Extended into `table_extraction/ocr_tables.py` (now reconstructs rows **and** columns into a grid) |
| (new) | Excel/CSV/DOCX with structure preserved | `table_extraction/office_tables.py` |

## What was archived (not shipped)

| Prototype | Reason |
|-----------|--------|
| `genai-multiagent-rag-fastapi` (+ `-openrouter`, `-hf-offline`) | General RAG chatbots — out of scope for table extraction |
| `Document_Specific_ChatBot_V1` | Chroma + OpenAI chatbot notebook prototype |
| `KPI Extraction/` (nested duplicate) | Duplicate/alias of the platform shell |
| `PDFCompressor_BBOX` | Useful PDF size-reduction utility; optional pre-processing, not core |
| `LLM_Serve` | Local LLM inference server; optional, skeleton stage |

## Key changes during consolidation

1. **Real table extraction replaces text flattening.** The legacy platform read PDFs with
   PyPDF2 and Excel via `df.to_string()`, destroying structure. That path is replaced by the
   unified engine that preserves rows/columns and emits a common `ExtractedTable`.
2. **SQL injection removed.** The legacy `file_service.py` built queries with f-strings
   (e.g. `WHERE id = {file_id}`). The rewrite uses SQLAlchemy ORM throughout.
3. **Endpoint/service mismatches fixed.** The shipped `files.py` referenced methods and
   model fields that didn't exist (`process_file_async`, `uploader_id`, `content_type`);
   these are now coherent with the model (`uploaded_by`, `file_type`) and service.
4. **New persistence.** Added the `extracted_tables` table (model + `init.sql`) and the
   `/files/{id}/tables`, `/tables/preview`, `/tables/export` endpoints.
5. **Graceful degradation.** OCR and AI/embeddings are now optional and isolated so a
   missing binary or API key can't fail the extraction pipeline.
6. **New surfaces.** Added the standalone CLI (`scripts/extract_tables_cli.py`) and the
   `TableViewer` React component.

## Verified

- pdfplumber path: extracted 11 tables from the sample PDF.
- office path: clean 4×3 from a CSV.
- export: multi-sheet XLSX + per-table CSVs written.
- package imports cleanly under the `app.services.table_extraction` namespace.

OCR path (PyMuPDF + Tesseract) is implemented but requires the system Tesseract binary to
exercise end-to-end.
