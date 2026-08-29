"""File ingestion + structured table extraction.

Rewritten for the consolidated platform:
  * Uses the unified `table_extraction` engine (pdfplumber / OCR / office) so tables
    keep their row/column structure instead of being flattened to text.
  * Persists every table as an `ExtractedTable` row.
  * Uses SQLAlchemy ORM throughout (the legacy version built raw f-string SQL and
    was vulnerable to SQL injection).
  * AI KPI extraction and embeddings are best-effort: a missing OpenAI key or model
    no longer fails the whole pipeline.
"""
from __future__ import annotations

import os
import uuid
import logging
from typing import Any, Dict, List, Optional

import aiofiles
from fastapi import UploadFile, HTTPException
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.file import (
    UploadedFile, FileStatus, ExtractedTable, ExtractedKPI, DocumentEmbedding,
)
from app.services.ai_service import AIService
from app.services.embedding_service import EmbeddingService
from app.services.table_extraction import (
    extract_tables, export_tables, SUPPORTED_EXTENSIONS,
)
from app.services.table_extraction.models import ExtractedTable as DomainTable

logger = logging.getLogger(__name__)


class FileService:
    """Saves uploads, runs the table-extraction pipeline, and serves results."""

    def __init__(self):
        self.ai_service = AIService()
        self.embedding_service = EmbeddingService()
        self.upload_dir = settings.UPLOAD_DIR

    # ------------------------------------------------------------------ #
    # Upload
    # ------------------------------------------------------------------ #
    async def save_uploaded_file(
        self,
        file: UploadFile,
        organization_id: int,
        user_id: int,
        description: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> UploadedFile:
        """Persist the uploaded file to disk + DB and return the committed record."""
        ext = os.path.splitext(file.filename or "")[1].lower()
        if ext not in SUPPORTED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type '{ext}'. Supported: {sorted(SUPPORTED_EXTENSIONS)}",
            )

        os.makedirs(self.upload_dir, exist_ok=True)
        unique_filename = f"{uuid.uuid4().hex}{ext}"
        file_path = os.path.join(self.upload_dir, unique_filename)

        try:
            async with aiofiles.open(file_path, "wb") as f:
                content = await file.read()
                await f.write(content)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to save file: {exc}") from exc

        record = UploadedFile(
            filename=unique_filename,
            original_filename=file.filename,
            file_path=file_path,
            file_size=len(content),
            file_type=file.content_type or ext,
            organization_id=organization_id,
            uploaded_by=user_id,
            status=FileStatus.UPLOADED,
            processing_metadata={"description": description} if description else None,
        )
        if db is not None:
            db.add(record)
            await db.commit()
            await db.refresh(record)
        return record

    # ------------------------------------------------------------------ #
    # Processing pipeline
    # ------------------------------------------------------------------ #
    @staticmethod
    async def _set_stage(record, db: AsyncSession, stage: str, **extra) -> None:
        """Publish the current pipeline stage so clients can poll real progress.

        Committed immediately: the upload request is still in flight, so this is
        the only way a polling UI can see which step is running.
        """
        record.processing_metadata = {
            **(record.processing_metadata or {}),
            "stage": stage,
            **extra,
        }
        flag_modified(record, "processing_metadata")
        await db.commit()

    async def process_file_async(self, file_id: int, db: AsyncSession) -> Dict[str, Any]:
        """Extract tables (+ best-effort KPIs/embeddings) for a stored file."""
        record = await self._get_file(file_id, db)

        record.status = FileStatus.PROCESSING
        await db.commit()

        try:
            # 1. Structured table extraction (the core of the platform).
            await self._set_stage(record, db, "extracting_tables")
            tables = await self._extract_and_store_tables(record, db)
            await self._set_stage(record, db, "tables_done",
                                  tables_extracted=len(tables))

            # 2. Best-effort KPI extraction from a flattened text view of the tables.
            text_view = self._tables_to_text(tables)
            # Clear any KPIs from a previous run so reprocessing replaces rather
            # than appends (mirrors _extract_and_store_tables).
            previous = await db.execute(
                select(ExtractedKPI).where(ExtractedKPI.file_id == file_id)
            )
            for stale in previous.scalars().all():
                await db.delete(stale)

            kpi_count = 0
            await self._set_stage(record, db, "extracting_kpis",
                                  kpi_windows_done=0, kpi_windows_total=None)

            async def _kpi_progress(done: int, total: int) -> None:
                await self._set_stage(record, db, "extracting_kpis",
                                      kpi_windows_done=done,
                                      kpi_windows_total=total)

            try:
                kpis = await self.ai_service.extract_kpis_from_text(
                    text_view, file_id, db, progress_cb=_kpi_progress
                )
                for kpi in kpis:
                    db.add(kpi)
                kpi_count = len(kpis)
            except Exception as exc:  # AI is optional - never fail the pipeline on it
                logger.warning("KPI extraction skipped for file %s: %s", file_id, exc)

            # 3. Best-effort embeddings for semantic search.
            # Clear prior embeddings first: without this, every reprocess appends
            # a fresh copy of every chunk and the same text wins several of the
            # top-k slots in semantic search.
            stale_embeddings = await db.execute(
                select(DocumentEmbedding).where(DocumentEmbedding.file_id == file_id)
            )
            for stale in stale_embeddings.scalars().all():
                await db.delete(stale)

            await self._set_stage(record, db, "embedding",
                                  kpis_extracted=kpi_count)
            embedding_count = 0
            try:
                embeddings = await self.embedding_service.create_document_embeddings(
                    file_id, text_view, db
                )
                for emb in embeddings:
                    db.add(emb)
                embedding_count = len(embeddings)
            except Exception as exc:
                logger.warning("Embeddings skipped for file %s: %s", file_id, exc)

            record.status = FileStatus.COMPLETED
            record.processing_metadata = {
                **(record.processing_metadata or {}),
                "stage": "done",
                "tables_extracted": len(tables),
                "kpis_extracted": kpi_count,
                "embeddings_created": embedding_count,
            }
            await db.commit()
            return {
                "file_id": file_id,
                "status": "completed",
                "tables": len(tables),
                "kpis": kpi_count,
            }

        except Exception as exc:
            await db.rollback()
            record = await self._get_file(file_id, db)
            record.status = FileStatus.FAILED
            record.processing_metadata = {**(record.processing_metadata or {}), "error": str(exc)}
            await db.commit()
            raise HTTPException(status_code=500, detail=f"File processing failed: {exc}") from exc

    async def _extract_and_store_tables(
        self, record: UploadedFile, db: AsyncSession
    ) -> List[ExtractedTable]:
        """Run the engine and persist results, replacing any prior tables."""
        # clear previous extraction (idempotent reprocessing)
        existing = await db.execute(
            select(ExtractedTable).where(ExtractedTable.file_id == record.id)
        )
        for row in existing.scalars().all():
            await db.delete(row)

        tables = extract_tables(record.file_path, **self._engine_opts())
        stored: List[ExtractedTable] = []
        for t in tables:
            row = ExtractedTable(
                file_id=record.id,
                page=t.page,
                table_index=t.index,
                source=t.source,
                sheet_name=t.sheet_name,
                caption=t.caption,
                n_rows=t.n_rows,
                n_cols=t.n_cols,
                confidence=t.confidence,
                rows=t.rows,
                bbox=t.bbox,
            )
            db.add(row)
            stored.append(row)
        await db.commit()
        return stored

    # ------------------------------------------------------------------ #
    # Reads / helpers
    # ------------------------------------------------------------------ #
    async def get_tables(self, file_id: int, db: AsyncSession) -> List[ExtractedTable]:
        """Return a file's stored tables ordered by page then table index."""
        await self._get_file(file_id, db)
        result = await db.execute(
            select(ExtractedTable)
            .where(ExtractedTable.file_id == file_id)
            .order_by(ExtractedTable.page, ExtractedTable.table_index)
        )
        return list(result.scalars().all())

    def preview_tables(self, file_path: str, limit: int = 5, rows: int = 10) -> Dict[str, Any]:
        """Stateless preview straight off disk (no DB write)."""
        tables = extract_tables(file_path, **self._engine_opts())
        previews = [t.preview(max_rows=rows) for t in tables[:limit]]
        return {"tables_found": len(tables), "tables": previews}

    @staticmethod
    def _engine_opts() -> Dict[str, Any]:
        """Shared extraction-engine options derived from settings."""
        return {
            "ocr_dpi": settings.OCR_DPI,
            "ocr_lang": settings.OCR_LANG,
            "allow_ocr": settings.ENABLE_OCR,
            "allow_vlm": settings.ENABLE_VLM,
            "vlm_model": settings.LLM_VISION_MODEL,
            "vlm_base_url": settings.LLM_BASE_URL,
            "vlm_api_key": settings.LLM_API_KEY or settings.OPENAI_API_KEY,
            "vlm_max_pages": settings.VLM_MAX_PAGES,
        }

    def export_file_tables(self, tables: List[ExtractedTable]) -> Dict[str, Any]:
        """Write ExtractedTable rows to XLSX + per-table CSV."""
        domain = [
            DomainTable(
                page=t.page, index=t.table_index, rows=t.rows, source=t.source or "",
                sheet_name=t.sheet_name, confidence=float(t.confidence or 1.0),
            )
            for t in tables
        ]
        return export_tables(domain, self.upload_dir)

    @staticmethod
    def _tables_to_text(tables: List[ExtractedTable]) -> str:
        """Flatten stored tables into text for AI/embeddings."""
        chunks: List[str] = []
        for t in tables:
            chunks.append(f"[page {t.page} table {t.table_index} via {t.source}]")
            for row in (t.rows or []):
                chunks.append("\t".join("" if c is None else str(c) for c in row))
        return "\n".join(chunks)

    async def _get_file(self, file_id: int, db: AsyncSession) -> UploadedFile:
        result = await db.execute(select(UploadedFile).where(UploadedFile.id == file_id))
        record = result.scalar_one_or_none()
        if not record:
            raise HTTPException(status_code=404, detail="File not found")
        return record

    async def delete_file(self, file_id: int, db: AsyncSession) -> bool:
        """Delete a file's DB record (cascades to tables/KPIs) and its file on disk."""
        record = await self._get_file(file_id, db)
        if record.file_path and os.path.exists(record.file_path):
            os.remove(record.file_path)
        await db.delete(record)
        await db.commit()
        return True
