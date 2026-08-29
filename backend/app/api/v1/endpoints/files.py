"""File upload and table/KPI extraction API endpoints."""
import json
import logging
import os
from typing import List, Optional

import openai
from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import FileResponse as FastAPIFileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.security import get_current_active_user, require_role, UserRole
from app.models.file import (
    UploadedFile, ExtractedKPI,
    FileResponse, ExtractedKPIResponse, ExtractedTableResponse,
    TablePreviewResponse, FileUploadResponse,
    DocumentSearchQuery, DocumentSearchResult,
)
from app.models.kpi import KPI
from app.models.user import User
from app.services.file_service import FileService
from app.services.embedding_service import EmbeddingService
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/", response_model=List[FileResponse])
async def get_files(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    organization_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    file_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get list of uploaded files."""
    query = select(UploadedFile).options(
        selectinload(UploadedFile.organization),
        selectinload(UploadedFile.uploaded_by_user)
    )

    # Filter by organization
    if organization_id:
        query = query.where(UploadedFile.organization_id == organization_id)
    else:
        # If no organization specified, show files from user's organizations
        # This is a simplified approach - in a real app you'd join with user_organizations
        pass

    # Filter by status
    if status:
        query = query.where(UploadedFile.status == status)

    # Filter by file type
    if file_type:
        query = query.where(UploadedFile.file_type == file_type)

    query = query.offset(skip).limit(limit)

    result = await db.execute(query)
    files = result.scalars().all()

    return files


@router.get("/{file_id}", response_model=FileResponse)
async def get_file(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get a specific file by ID."""
    result = await db.execute(
        select(UploadedFile).options(
            selectinload(UploadedFile.organization),
            selectinload(UploadedFile.uploaded_by_user),
            selectinload(UploadedFile.extracted_kpis)
        ).where(UploadedFile.id == file_id)
    )
    file = result.scalar_one_or_none()

    if not file:
        raise HTTPException(status_code=404, detail="File not found")

    return file


@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    organization_id: int = Form(...),
    description: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ANALYST))
):
    """Upload a file for KPI extraction."""
    # Validate file size
    if file.size and file.size > settings.MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size: {settings.MAX_FILE_SIZE} bytes"
        )

    # Initialize services (file-type validation happens inside save_uploaded_file)
    file_service = FileService()

    try:
        # Save file and create database record
        file_record = await file_service.save_uploaded_file(
            file, organization_id, current_user.id, description, db
        )

        # Run the extraction pipeline (tables + best-effort KPIs/embeddings)
        await file_service.process_file_async(file_record.id, db)
        await db.refresh(file_record)

        return FileUploadResponse(
            file=FileResponse.model_validate(file_record),
            message="File uploaded and processed successfully.",
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}") from e


@router.delete("/{file_id}")
async def delete_file(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Delete a file."""
    result = await db.execute(select(UploadedFile).where(UploadedFile.id == file_id))
    file = result.scalar_one_or_none()

    if not file:
        raise HTTPException(status_code=404, detail="File not found")

    # Check permissions: uploader or admin can delete
    if file.uploaded_by != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    # Delete physical file
    if file.file_path and os.path.exists(file.file_path):
        os.remove(file.file_path)

    # Delete from database
    await db.delete(file)
    await db.commit()

    return {"message": "File deleted successfully"}


@router.get("/{file_id}/extracted-kpis", response_model=List[ExtractedKPIResponse])
async def get_extracted_kpis(
    file_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get KPIs extracted from a specific file."""
    # Verify file exists
    result = await db.execute(select(UploadedFile).where(UploadedFile.id == file_id))
    file = result.scalar_one_or_none()

    if not file:
        raise HTTPException(status_code=404, detail="File not found")

    # Get extracted KPIs
    result = await db.execute(
        select(ExtractedKPI)
        .where(ExtractedKPI.file_id == file_id)
        .offset(skip)
        .limit(limit)
    )
    kpis = result.scalars().all()

    return kpis


@router.post("/{file_id}/reprocess")
async def reprocess_file(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ANALYST))
):
    """Reprocess a file for KPI extraction."""
    result = await db.execute(select(UploadedFile).where(UploadedFile.id == file_id))
    file = result.scalar_one_or_none()

    if not file:
        raise HTTPException(status_code=404, detail="File not found")

    # Check permissions: uploader or admin can reprocess
    if file.uploaded_by != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    # Initialize services
    file_service = FileService()

    try:
        # Reprocess file
        await file_service.process_file_async(file_id, db)

        return {"message": "File reprocessing started"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reprocessing failed: {str(e)}") from e


class AskRequest(BaseModel):
    """A natural-language question asked against uploaded documents."""

    question: str
    organization_id: int
    file_ids: Optional[List[int]] = None
    top_k: int = 5
    similarity_threshold: float = 0.05


class AskResponse(BaseModel):
    """An LLM answer grounded in retrieved document chunks."""

    answer: str
    sources: List[DocumentSearchResult] = []
    retrieval: str = "hybrid (vector + keyword, RRF-fused)"


def _rerank(question: str, candidates: List[dict], top_k: int) -> List[dict]:
    """Reorder retrieved chunks by relevance using the configured LLM.

    A cross-encoder (BGE, Cohere) is the textbook choice, but that means either
    a cloud call or a second local model. Reusing the chat model as a judge
    costs one extra request and captures most of the benefit. On any failure
    the original hybrid order is returned unchanged - reranking must never be
    able to break retrieval.
    """
    if len(candidates) <= top_k:
        return candidates

    listing = "\n\n".join(
        f"[{i}] {c['content_chunk'][:600]}" for i, c in enumerate(candidates)
    )
    client = openai.OpenAI(
        base_url=settings.LLM_BASE_URL,
        api_key=settings.LLM_API_KEY or settings.OPENAI_API_KEY or "local",
    )
    try:
        completion = client.chat.completions.create(
            model=settings.LLM_MODEL,
            temperature=0,
            max_tokens=200,
            messages=[
                {"role": "system", "content":
                 "You rank passages by how directly they answer a question. "
                 "Reply with ONLY a JSON array of passage indices, best first. "
                 "No prose."},
                {"role": "user", "content":
                 f"Question: {question}\n\nPassages:\n{listing}\n\n"
                 f"Return the {top_k} most useful indices as a JSON array."},
            ],
        )
        raw = (completion.choices[0].message.content or "").strip()
        order = json.loads(raw[raw.index("["): raw.rindex("]") + 1])
        picked = [candidates[i] for i in order
                  if isinstance(i, int) and 0 <= i < len(candidates)]
    except Exception as err:
        logger.warning("Rerank failed, keeping hybrid order: %s", err)
        return candidates[:top_k]

    # Backfill from the original order if the model returned too few.
    for cand in candidates:
        if len(picked) >= top_k:
            break
        if cand not in picked:
            picked.append(cand)
    return picked[:top_k]


@router.post("/ask", response_model=AskResponse)
async def ask_documents(
    body: AskRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Answer a question using retrieval over document embeddings (RAG).

    Retrieves the most similar stored chunks, then asks the configured LLM to
    answer using only that context. Returns the answer plus its sources so the
    caller can see exactly what the answer was grounded in.
    """
    embedding_service = EmbeddingService()
    try:
        # Retrieve wider than we need, then rerank down. Hybrid search is good
        # at surfacing candidates but poor at ordering them - the chunk that
        # answers the question is often not the one with the best cosine score.
        pool = max(body.top_k * 4, 12)
        candidates = await embedding_service.search_documents_hybrid(
            query=body.question,
            organization_id=body.organization_id,
            file_ids=body.file_ids,
            limit=pool,
            similarity_threshold=body.similarity_threshold,
            db=db,
        )
        chunks = _rerank(body.question, candidates, body.top_k)
    except Exception as err:
        raise HTTPException(status_code=500, detail=f"Retrieval failed: {err}") from err

    if not chunks:
        return AskResponse(
            answer="No relevant content found. Upload a document first, or "
                   "lower the similarity threshold.",
            sources=[],
        )

    def _label(c: dict) -> str:
        meta = c.get("chunk_metadata") or {}
        page = meta.get("page_number")
        return f"{c['filename']}" + (f", Page {page}" if page else "")

    context = "\n\n---\n\n".join(
        f"[Source: {_label(c)}]\n{c['content_chunk']}" for c in chunks
    )
    client = openai.OpenAI(
        base_url=settings.LLM_BASE_URL,
        api_key=settings.LLM_API_KEY or settings.OPENAI_API_KEY or "local",
    )
    try:
        completion = client.chat.completions.create(
            model=settings.LLM_MODEL,
            temperature=0.1,
            # Generous budget: the configured model is a reasoning model and
            # spends 1.5-2k tokens thinking before it emits an answer.
            max_tokens=4000,
            messages=[
                {"role": "system", "content":
                 "You answer strictly from the provided context.\n"
                 "- If the answer is not in the context, say \"That is not "
                 "stated in the provided documents.\" Do not guess.\n"
                 "- Never supply a year, quarter, fiscal period, currency, "
                 "scale or unit that is not written in the context. Column "
                 "headers are often separated from their figures - if a "
                 "period or unit is not shown, say it is not stated rather "
                 "than inferring it.\n"
                 "- Quote numbers exactly as they appear. Never rescale, "
                 "convert or compute new figures.\n"
                 "- If the question assumes something the documents do not "
                 "cover (for example a quarter when only annual figures are "
                 "present), say so before answering.\n"
                 "- Name the line item you are quoting, and be concise.\n"
                 "- CITE every figure inline using the bracketed source shown "
                 "above it, e.g. \"revenue grew 12% [Source: Report.pdf, "
                 "Page 14]\". A number without a citation is not acceptable."},
                {"role": "user", "content":
                 f"Context:\n{context}\n\nQuestion: {body.question}"},
            ] + ([{"role": "assistant", "content": settings.LLM_THINK_PREFILL}]
                 if settings.LLM_THINK_PREFILL else []),
        )
        answer = (completion.choices[0].message.content or "").strip()
        if not answer:
            answer = ("The model returned no answer (its reasoning consumed the "
                      "whole token budget). Try a narrower question.")
    except Exception as err:
        raise HTTPException(status_code=502, detail=f"LLM call failed: {err}") from err

    return AskResponse(answer=answer, sources=chunks)


@router.post("/search", response_model=List[DocumentSearchResult])
async def search_documents(
    search_query: DocumentSearchQuery,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Search documents using semantic search."""
    embedding_service = EmbeddingService()

    try:
        # Perform semantic search over document chunks.
        # NOTE: call search_documents directly with keyword args - semantic_search()
        # takes (query, organization_id, search_type, limit, db) and returns a dict,
        # which does not match this route's List[DocumentSearchResult] response model.
        results = await embedding_service.search_documents(
            query=search_query.query,
            organization_id=search_query.organization_id,
            file_ids=search_query.file_ids,
            limit=search_query.limit or 10,
            similarity_threshold=search_query.similarity_threshold,
            db=db,
        )

        return results

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}") from e


@router.get("/{file_id}/status")
async def get_file_status(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get the processing status of a file."""
    result = await db.execute(
        select(UploadedFile).where(UploadedFile.id == file_id)
    )
    file = result.scalar_one_or_none()

    if not file:
        raise HTTPException(status_code=404, detail="File not found")

    return {
        "file_id": file.id,
        "status": file.status,
        "processing_metadata": file.processing_metadata,
        "created_at": file.created_at,
        "updated_at": file.updated_at
    }


class PromoteResponse(BaseModel):
    """Result of promoting a file's extracted KPIs into the curated KPI table."""

    promoted: int
    skipped: int
    message: str


@router.post("/{file_id}/promote-kpis", response_model=PromoteResponse)
async def promote_extracted_kpis(
    file_id: int,
    min_confidence: float = Query(0.5, ge=0.0, le=1.0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ANALYST))
):
    """Copy a file's extracted KPIs into the curated `kpis` table.

    Extraction writes to `extracted_kpis`, which is a per-file staging area.
    Nothing else in the codebase moves those rows into `kpis`, so the curated
    KPI list stayed empty no matter how many documents were processed. This is
    that missing step: it is explicit (you choose when to promote) and
    idempotent (an existing KPI with the same name in the org is skipped).
    """
    result = await db.execute(select(UploadedFile).where(UploadedFile.id == file_id))
    file = result.scalar_one_or_none()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")

    rows = await db.execute(
        select(ExtractedKPI).where(ExtractedKPI.file_id == file_id)
    )
    extracted = list(rows.scalars().all())

    existing = await db.execute(
        select(KPI.name).where(KPI.organization_id == file.organization_id)
    )
    taken = {n for (n,) in existing.all()}

    promoted = 0
    skipped = 0
    for row in extracted:
        name = (row.kpi_name or "").strip()
        conf = float(row.confidence_score or 0)
        if not name or name in taken or conf < min_confidence:
            skipped += 1
            continue
        db.add(KPI(
            name=name[:255],
            description=f"Extracted from {file.original_filename}",
            unit=(row.kpi_unit or None),
            current_value=row.kpi_value,
            organization_id=file.organization_id,
            created_by=current_user.id,
        ))
        taken.add(name)
        promoted += 1

    await db.commit()
    return PromoteResponse(
        promoted=promoted, skipped=skipped,
        message=f"Promoted {promoted} KPI(s); skipped {skipped} "
                f"(duplicate, unnamed, or below confidence {min_confidence}).",
    )


@router.post("/{file_id}/extract-kpis")
async def extract_kpis_from_file(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ANALYST))
):
    """Manually trigger KPI extraction from a file."""
    result = await db.execute(select(UploadedFile).where(UploadedFile.id == file_id))
    file = result.scalar_one_or_none()

    if not file:
        raise HTTPException(status_code=404, detail="File not found")

    # Check permissions: uploader or admin can extract KPIs
    if file.uploaded_by != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    file_service = FileService()
    try:
        # Re-run the full extraction pipeline (tables + best-effort KPIs).
        result = await file_service.process_file_async(file_id, db)
        return {
            "message": "Extraction completed",
            "tables_extracted": result.get("tables", 0),
            "kpis_extracted": result.get("kpis", 0),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"KPI extraction failed: {str(e)}") from e


@router.get("/{file_id}/tables", response_model=List[ExtractedTableResponse])
async def get_extracted_tables(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Return the structured tables extracted from a file (rows/cols preserved)."""
    file_service = FileService()
    tables = await file_service.get_tables(file_id, db)
    return tables


@router.get("/{file_id}/tables/preview", response_model=TablePreviewResponse)
async def preview_extracted_tables(
    file_id: int,
    limit: int = Query(5, ge=1, le=50),
    rows: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Preview tables directly from the stored file without re-persisting."""
    result = await db.execute(select(UploadedFile).where(UploadedFile.id == file_id))
    file = result.scalar_one_or_none()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")

    file_service = FileService()
    return file_service.preview_tables(file.file_path, limit=limit, rows=rows)


@router.get("/{file_id}/tables/export")
async def export_extracted_tables(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Export a file's tables as a multi-sheet XLSX workbook."""
    file_service = FileService()
    tables = await file_service.get_tables(file_id, db)
    if not tables:
        raise HTTPException(status_code=404, detail="No tables extracted for this file")

    out = file_service.export_file_tables(tables)
    return FastAPIFileResponse(
        path=out["xlsx"],
        filename=f"tables_file_{file_id}.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("/{file_id}/download")
async def download_file(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Download a file."""
    result = await db.execute(select(UploadedFile).where(UploadedFile.id == file_id))
    file = result.scalar_one_or_none()

    if not file:
        raise HTTPException(status_code=404, detail="File not found")

    # Check if file exists on disk
    if not file.file_path or not os.path.exists(file.file_path):
        raise HTTPException(status_code=404, detail="File not found on disk")

    # Return file for download
    return FastAPIFileResponse(
        path=file.file_path,
        filename=file.original_filename,
        media_type=file.file_type
    )
