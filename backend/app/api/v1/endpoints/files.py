"""File upload and table/KPI extraction API endpoints."""
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
from app.models.user import User
from app.services.file_service import FileService
from app.services.embedding_service import EmbeddingService
from app.core.config import settings

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
        chunks = await embedding_service.search_documents(
            query=body.question,
            organization_id=body.organization_id,
            file_ids=body.file_ids,
            limit=body.top_k,
            similarity_threshold=body.similarity_threshold,
            db=db,
        )
    except Exception as err:
        raise HTTPException(status_code=500, detail=f"Retrieval failed: {err}") from err

    if not chunks:
        return AskResponse(
            answer="No relevant content found. Upload a document first, or "
                   "lower the similarity threshold.",
            sources=[],
        )

    context = "\n\n---\n\n".join(
        f"[source: {c['filename']}]\n{c['content_chunk']}" for c in chunks
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
                 "Answer strictly from the provided context. If the context does "
                 "not contain the answer, say so plainly. Be concise."},
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
        # NOTE: call search_documents directly with keyword args — semantic_search()
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
