"""File upload and table/KPI extraction API endpoints."""
import asyncio
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
from app.models.kpi import KPI, KPICategory
from app.models.user import User
from app.services.file_service import FileService
from app.services.ai_service import AIService
from app.services.embedding_service import EmbeddingService
from app.services.self_query import SelfQuery, apply_metadata_filter
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


def _infer_category(name: str) -> KPICategory:
    """Bucket a KPI by name using the extraction service's keyword lists.

    Everything previously landed in `other` because nothing ever set this.
    """
    low = name.lower()
    for category, terms in AIService().kpi_patterns.items():
        if any(term in low for term in terms):
            try:
                return KPICategory(category)
            except ValueError:
                break
    return KPICategory.OTHER


def _label(c: dict) -> str:
    """Human-readable citation for a chunk: filename and page."""
    meta = c.get("chunk_metadata") or {}
    page = meta.get("page_number")
    return f"{c['filename']}" + (f", Page {page}" if page else "")


def _source_key(chunk: dict) -> tuple:
    """Identity of the document region a chunk came from.

    Windows cut from the same table overlap by CHUNK_OVERLAP characters, so
    neighbours are near-duplicates that rank almost identically and would
    otherwise occupy several of the few slots an answer gets to see.
    """
    meta = chunk.get("chunk_metadata") or {}
    page, table = meta.get("page_number"), meta.get("table_index")
    if page is None and table is None:
        # No provenance to group on - keep the chunk distinct rather than
        # collapsing every unmarked chunk of a file into one.
        return ("chunk", chunk.get("file_id"), chunk.get("chunk_index"))
    return ("region", chunk.get("file_id"), page, table)


# How many chunks one document region may contribute to a single answer.
# Collapsing a region to one chunk was correct while a repeated header made
# neighbours 75% identical; with the header now charged against the chunk
# budget they overlap by only the configured overlap, and the parts of a long
# statement are genuinely different content. Apple's cash flow statement is
# three chunks - operating, investing, financing - so keeping one made the
# operating figures unreachable whenever another slice outranked them, and the
# answer correctly reported that it could not see them. The cap still stops a
# single table from taking every slot.
MAX_PER_REGION = 3


def _dedupe_by_source(candidates: List[dict]) -> List[dict]:
    """Limit how many chunks each document region contributes.

    Input is already ordered best-first by the hybrid search, so the chunks
    kept for a region are the ones most similar to the question.
    """
    kept: dict = {}
    out: List[dict] = []
    for cand in candidates:
        key = _source_key(cand)
        if kept.get(key, 0) >= MAX_PER_REGION:
            continue
        kept[key] = kept.get(key, 0) + 1
        out.append(cand)
    return out


def _passage_text(chunk: dict, budget: int) -> str:
    """Chunk text prepared for the judge: provenance stripped, then truncated.

    Each stored chunk starts with a contextual prefix and, for tables, the
    extractor's marker line. Repeating those across every passage spends the
    judge's budget on boilerplate it already gets from the label, leaving too
    little room for the figures that decide the ranking.
    """
    lines = chunk["content_chunk"].split("\n")
    while lines and lines[0].lstrip().startswith("["):
        lines.pop(0)
    body = "\n".join(lines).strip() or chunk["content_chunk"]
    return body[:budget]


async def _rerank(question: str, candidates: List[dict], top_k: int) -> List[dict]:
    """Reorder retrieved chunks by relevance using the configured LLM.

    A cross-encoder (BGE, Cohere) is the textbook choice, but that means either
    a cloud call or a second local model. Reusing the chat model as a judge
    costs one extra request and captures most of the benefit. On any failure
    the original hybrid order is returned unchanged - reranking must never be
    able to break retrieval.
    """
    if len(candidates) <= top_k:
        return candidates

    # Fewer, distinct candidates means each one can afford more characters,
    # which matters because the deciding detail is usually a figure partway
    # into the passage rather than its opening line.
    budget = 1400 if len(candidates) <= 12 else 900
    listing = "\n\n".join(
        f"[{i}] {_label(c)}\n{_passage_text(c, budget)}"
        for i, c in enumerate(candidates)
    )
    client = openai.OpenAI(
        base_url=settings.LLM_BASE_URL,
        api_key=settings.LLM_API_KEY or settings.OPENAI_API_KEY or "local",
    )
    try:
        # to_thread: the openai client is synchronous. Called directly from an
        # async handler it blocks uvicorn's event loop for the whole rerank, so
        # every other request stalls behind it.
        completion = await asyncio.to_thread(
            client.chat.completions.create,
            model=settings.LLM_MODEL,
            temperature=0,
            max_tokens=200,
            messages=[
                {"role": "system", "content":
                 "You rank passages by how directly they answer a question.\n"
                 "Rank higher: passages stating the exact line item asked "
                 "about, with its figures and the period they belong to.\n"
                 "Rank lower: passages that merely mention the topic, discuss "
                 "a related but different line item, or give only narrative "
                 "with no figures.\n"
                 "A primary financial statement outranks a supporting note "
                 "when both contain the figure.\n"
                 "Reply with ONLY a JSON array of passage indices, best "
                 "first. No prose."},
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


async def _retrieve_candidates(body, db: AsyncSession) -> List[dict]:
    """Everything /ask does before reranking, as one path both routes share.

    /retrieve exists to measure this, so it has to BE this. Kept as one
    function rather than two similar blocks: the moment they drift, the
    ranking metrics describe a pipeline that no longer answers anything.
    """
    embedding_service = EmbeddingService()
    # Retrieve wider than we need, then rerank down. Hybrid search is good
    # at surfacing candidates but poor at ordering them - the chunk that
    # answers the question is often not the one with the best cosine score.
    pool = max(body.top_k * 4, 12)

    # Split the question into what to search for and what to filter on.
    # The catalogue is passed in so the planner picks files by id from
    # what this organisation actually holds rather than naming one.
    catalogue = [
        {"id": row[0], "original_filename": row[1]}
        for row in (await db.execute(
            select(UploadedFile.id, UploadedFile.original_filename)
            .where(UploadedFile.organization_id == body.organization_id)
        )).all()
    ]
    plan = await SelfQuery().plan(body.question, catalogue)
    # An explicit file_ids on the request is access scoping and wins. The
    # planner may only narrow inside what the caller already allowed.
    file_ids = body.file_ids or (plan["file_ids"] or None)

    candidates = await embedding_service.search_documents_hybrid(
        # Search on the stripped query: "in the 2024 10-K" describes where
        # to look, and leaving it in the embedded text pulls the match
        # toward chunks that discuss filings rather than the figure asked
        # for. Reranking and answering still see the whole question.
        query=plan["query"],
        organization_id=body.organization_id,
        file_ids=file_ids,
        limit=pool,
        similarity_threshold=body.similarity_threshold,
        db=db,
    )
    candidates = apply_metadata_filter(
        candidates, plan["page_min"], plan["page_max"], plan["section"])
    # Cap how much of one table can fill the answer, so the judge chooses
    # between distinct regions rather than near-copies of one passage.
    return _dedupe_by_source(candidates)


def _slim(chunk: dict) -> dict:
    """The ranking-relevant fields of a chunk, without its text."""
    meta = chunk.get("chunk_metadata") or {}
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except ValueError:
            meta = {}
    return {
        "file_id": chunk.get("file_id"),
        "page_number": meta.get("page_number"),
        "section": meta.get("section"),
        "chunk_index": chunk.get("chunk_index"),
        "similarity_score": chunk.get("similarity_score"),
        "rrf_score": chunk.get("rrf_score"),
        "matched_by": chunk.get("matched_by"),
    }


@router.post("/retrieve")
async def retrieve_ranked(
    body: AskRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Return the ranked chunks before and after reranking, with no answer.

    For evaluation. /ask returns only the chunks that survived reranking, so
    the ordering the reranker was given cannot be recovered from it, and the
    question "did reranking help" has no observable answer. Exposing both
    orderings makes MRR before and after computable in one request.
    """
    try:
        candidates = await _retrieve_candidates(body, db)
        reranked = await _rerank(body.question, candidates, body.top_k)
    except Exception as err:
        raise HTTPException(status_code=500,
                            detail=f"Retrieval failed: {err}") from err
    return {
        "before_rerank": [_slim(c) for c in candidates],
        "after_rerank": [_slim(c) for c in reranked],
    }


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
    try:
        candidates = await _retrieve_candidates(body, db)
        chunks = await _rerank(body.question, candidates, body.top_k)
    except Exception as err:
        raise HTTPException(status_code=500, detail=f"Retrieval failed: {err}") from err

    if not chunks:
        return AskResponse(
            answer="No relevant content found. Upload a document first, or "
                   "lower the similarity threshold.",
            sources=[],
        )

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
                 "- Quote numbers exactly as they appear. Do NOT invent, "
                 "rescale or convert figures.\n"
                 "- If the context states the basis a table is presented on - "
                 "\"(In millions)\", \"in thousands\", \"assumes $100 was "
                 "invested\", \"per share\" - say so alongside the figures. A "
                 "number is not usable without knowing what it counts, and a "
                 "reader who has seen other tables in the same document will "
                 "assume the wrong basis if you omit it.\n"
                 "- Arithmetic is allowed ONLY when the question asks for it "
                 "(total, sum, combined, average, difference, growth). When it "
                 "does: list each component on its own line with its value and "
                 "citation, then show the arithmetic, then the result, and "
                 "label the result as computed. Example:\n"
                 "    2023: $96,995M [Source: f.pdf, Page 39]\n"
                 "    2024: $93,736M [Source: f.pdf, Page 39]\n"
                 "    Total (computed): 96,995 + 93,736 = $190,731M\n"
                 "- If the question asks for figures per period, per year or "
                 "'respectively', list them separately and do NOT sum them.\n"
                 "- Never compute a figure the question did not ask for.\n"
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
    # Why rows were skipped, so an empty curated list is diagnosable from the
    # response instead of requiring a look at the staging table.
    reasons: dict = {}
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
    reasons = {"unnamed": 0, "duplicate": 0, "low_confidence": 0, "no_value": 0}
    for row in extracted:
        name = (row.kpi_name or "").strip()
        conf = float(row.confidence_score or 0)
        # A KPI without a number is not a metric. The model also returns
        # narrative items ("Potential for stock price volatility"); those
        # belong in the staging table, never in the curated list.
        # Reasons are counted separately: "skipped 24" gives no way to tell a
        # confidence threshold that is set too high from rows that genuinely
        # carry no figure.
        if not name:
            reasons["unnamed"] += 1
            continue
        if name in taken:
            reasons["duplicate"] += 1
            continue
        if row.kpi_value is None:
            reasons["no_value"] += 1
            continue
        if conf < min_confidence:
            reasons["low_confidence"] += 1
            continue
        db.add(KPI(
            name=name[:255],
            description=f"Extracted from {file.original_filename}",
            category=_infer_category(name),
            unit=(row.kpi_unit or None),
            current_value=row.kpi_value,
            organization_id=file.organization_id,
            created_by=current_user.id,
        ))
        taken.add(name)
        promoted += 1

    await db.commit()

    skipped = sum(reasons.values())
    if not extracted:
        message = ("Nothing to promote: this file has no extracted KPIs yet. "
                   "Run Extract KPIs first.")
    elif promoted:
        message = f"Promoted {promoted} KPI(s); skipped {skipped}."
    else:
        detail = ", ".join(f"{n} {k.replace('_', ' ')}"
                           for k, n in reasons.items() if n)
        message = (f"Promoted nothing from {len(extracted)} extracted row(s): "
                   f"{detail}.")
        if reasons["low_confidence"]:
            message += (f" The threshold is {min_confidence}; pattern-matched "
                        "rows are scored 0.3 and need a lower one to promote.")
    return PromoteResponse(promoted=promoted, skipped=skipped,
                           reasons=reasons, message=message)


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
