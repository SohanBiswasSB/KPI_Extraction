"""Embedding generation and vector-similarity search for documents and KPIs."""

import logging
from typing import List, Dict, Any, Optional

import openai
from sqlalchemy import select, text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.file import DocumentEmbedding
from app.models.kpi import KPIEmbedding, KPI

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Generate embeddings and run semantic search over documents and KPIs."""

    def __init__(self):
        # Local-first: OpenAI-compatible embeddings server
        # (LM Studio: `text-embedding-nomic-embed-text-v1.5`, 768-dim).
        self.client = openai.OpenAI(
            base_url=settings.LLM_BASE_URL,
            api_key=settings.LLM_API_KEY or settings.OPENAI_API_KEY or "local",
        )
        self.embedding_model = settings.LLM_EMBEDDING_MODEL
        self.vector_dimension = settings.VECTOR_DIMENSION

    async def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for a text using OpenAI."""
        try:
            response = self.client.embeddings.create(
                model=self.embedding_model,
                input=text
            )
            return response.data[0].embedding
        except Exception as err:
            logger.error("Error generating embedding: %s", err)
            # Return zero vector as fallback
            return [0.0] * self.vector_dimension

    async def chunk_text(self, text: str, chunk_size: int = None, overlap: int = None) -> List[str]:
        """Split text into chunks for embedding."""
        if chunk_size is None:
            chunk_size = settings.CHUNK_SIZE
        if overlap is None:
            overlap = settings.CHUNK_OVERLAP

        chunks = []
        start = 0

        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]
            chunks.append(chunk)

            # Move start position with overlap
            start = end - overlap
            if start >= len(text):
                break

        return chunks

    async def create_document_embeddings(
        self, file_id: int, text: str, db: AsyncSession
    ) -> List[DocumentEmbedding]:
        """Create embeddings for document chunks."""
        # Split text into chunks
        chunks = await self.chunk_text(text)
        embeddings = []

        for i, chunk in enumerate(chunks):
            # Generate embedding
            embedding_vector = await self.generate_embedding(chunk)

            # Create document embedding record
            doc_embedding = DocumentEmbedding(
                file_id=file_id,
                content_chunk=chunk,
                embedding=embedding_vector,
                chunk_index=i,
                chunk_metadata={
                    "chunk_size": len(chunk),
                    "chunk_index": i,
                    "total_chunks": len(chunks)
                }
            )
            embeddings.append(doc_embedding)

        return embeddings

    async def create_kpi_embedding(
        self, kpi_id: int, kpi_text: str, db: AsyncSession
    ) -> KPIEmbedding:
        """Create embedding for a KPI."""
        embedding_vector = await self.generate_embedding(kpi_text)

        kpi_embedding = KPIEmbedding(
            kpi_id=kpi_id,
            embedding=embedding_vector
        )

        return kpi_embedding

    async def search_documents(
        self,
        query: str,
        organization_id: int,
        file_ids: Optional[List[int]] = None,
        limit: int = 10,
        similarity_threshold: float = 0.7,
        db: AsyncSession = None
    ) -> List[Dict[str, Any]]:
        """Search documents using vector similarity."""
        # Generate embedding for query
        query_embedding = await self.generate_embedding(query)

        # Build search query.
        # NOTE: this runs through SQLAlchemy text(), so it uses :named bind params
        # and a dict — not asyncpg's $1 positional style. The query vector is bound
        # as its pgvector literal form and cast, since it is not an ORM column here.
        vec = "[" + ",".join(str(float(x)) for x in query_embedding) + "]"

        search_query = """
        SELECT
            de.content_chunk,
            de.file_id,
            uf.original_filename,
            de.chunk_index,
            de.chunk_metadata,
            1 - (de.embedding <=> CAST(:vec AS vector)) AS similarity_score
        FROM document_embeddings de
        JOIN uploaded_files uf ON de.file_id = uf.id
        WHERE uf.organization_id = :org_id
        """

        params = {
            "vec": vec,
            "org_id": organization_id,
            "threshold": similarity_threshold,
            "limit": limit,
        }

        if file_ids:
            search_query += " AND de.file_id = ANY(:file_ids)"
            params["file_ids"] = list(file_ids)

        search_query += """
        AND 1 - (de.embedding <=> CAST(:vec AS vector)) > :threshold
        ORDER BY similarity_score DESC
        LIMIT :limit
        """

        # Execute search
        result = await db.execute(sql_text(search_query), params)
        rows = result.fetchall()

        # Format results
        search_results = []
        for row in rows:
            search_results.append({
                "content_chunk": row[0],
                "file_id": row[1],
                "filename": row[2],
                "chunk_index": row[3],
                "chunk_metadata": row[4],
                "similarity_score": float(row[5])
            })

        return search_results

    async def search_kpis(
        self,
        query: str,
        organization_id: int,
        limit: int = 10,
        similarity_threshold: float = 0.7,
        db: AsyncSession = None
    ) -> List[Dict[str, Any]]:
        """Search KPIs using vector similarity."""
        # Generate embedding for query
        query_embedding = await self.generate_embedding(query)

        # Build search query.
        # Same binding rules as search_documents(): SQLAlchemy text() needs
        # :named params and a dict, and the query vector must be cast to vector.
        vec = "[" + ",".join(str(float(x)) for x in query_embedding) + "]"

        search_query = """
        SELECT
            k.name,
            k.description,
            k.category,
            k.unit,
            k.current_value,
            k.target_value,
            ke.kpi_id,
            1 - (ke.embedding <=> CAST(:vec AS vector)) AS similarity_score
        FROM kpi_embeddings ke
        JOIN kpis k ON ke.kpi_id = k.id
        WHERE k.organization_id = :org_id
        AND 1 - (ke.embedding <=> CAST(:vec AS vector)) > :threshold
        ORDER BY similarity_score DESC
        LIMIT :limit
        """

        # Execute search
        result = await db.execute(
            sql_text(search_query),
            {
                "vec": vec,
                "org_id": organization_id,
                "threshold": similarity_threshold,
                "limit": limit,
            },
        )
        rows = result.fetchall()

        # Format results
        search_results = []
        for row in rows:
            search_results.append({
                "kpi_name": row[0],
                "description": row[1],
                "category": row[2],
                "unit": row[3],
                "current_value": float(row[4]) if row[4] else None,
                "target_value": float(row[5]) if row[5] else None,
                "kpi_id": row[6],
                "similarity_score": float(row[7])
            })

        return search_results

    async def semantic_search(
        self,
        query: str,
        organization_id: int,
        search_type: str = "both",  # "documents", "kpis", "both"
        limit: int = 10,
        db: AsyncSession = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Perform semantic search across documents and KPIs."""
        results = {}

        if search_type in ["documents", "both"]:
            doc_results = await self.search_documents(
                query=query,
                organization_id=organization_id,
                limit=limit,
                db=db
            )
            results["documents"] = doc_results

        if search_type in ["kpis", "both"]:
            kpi_results = await self.search_kpis(
                query=query,
                organization_id=organization_id,
                limit=limit,
                db=db
            )
            results["kpis"] = kpi_results

        return results

    async def update_kpi_embeddings(self, kpi_id: int, db: AsyncSession) -> None:
        """Update embeddings for a KPI when it's modified."""
        # Get KPI data
        result = await db.execute(
            select(KPI).where(KPI.id == kpi_id)
        )
        kpi = result.scalar_one_or_none()

        if not kpi:
            return

        # Create text representation for embedding
        kpi_text = f"{kpi.name} {kpi.description or ''} {kpi.category.value} {kpi.unit or ''}"

        # Check if embedding exists
        result = await db.execute(
            select(KPIEmbedding).where(KPIEmbedding.kpi_id == kpi_id)
        )
        existing_embedding = result.scalar_one_or_none()

        # Generate new embedding
        new_embedding_vector = await self.generate_embedding(kpi_text)

        if existing_embedding:
            # Update existing embedding
            existing_embedding.embedding = new_embedding_vector
        else:
            # Create new embedding
            new_embedding = KPIEmbedding(
                kpi_id=kpi_id,
                embedding=new_embedding_vector
            )
            db.add(new_embedding)

        await db.commit()

    async def batch_create_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Create embeddings for multiple texts in batch."""
        try:
            response = self.client.embeddings.create(
                model=self.embedding_model,
                input=texts
            )
            return [data.embedding for data in response.data]
        except Exception as err:
            logger.error("Error in batch embedding generation: %s", err)
            # Return zero vectors as fallback
            return [[0.0] * self.vector_dimension for _ in texts]

    async def get_embedding_statistics(
        self, organization_id: int, db: AsyncSession
    ) -> Dict[str, Any]:
        """Get statistics about embeddings for an organization."""
        # Count document embeddings
        doc_count_query = """
        SELECT COUNT(*) as count
        FROM document_embeddings de
        JOIN uploaded_files uf ON de.file_id = uf.id
        WHERE uf.organization_id = :org_id
        """
        result = await db.execute(sql_text(doc_count_query), {"org_id": organization_id})
        doc_count = result.scalar()

        # Count KPI embeddings
        kpi_count_query = """
        SELECT COUNT(*) as count
        FROM kpi_embeddings ke
        JOIN kpis k ON ke.kpi_id = k.id
        WHERE k.organization_id = :org_id
        """
        result = await db.execute(sql_text(kpi_count_query), {"org_id": organization_id})
        kpi_count = result.scalar()

        return {
            "document_embeddings": doc_count,
            "kpi_embeddings": kpi_count,
            "total_embeddings": doc_count + kpi_count
        }

    async def search_similar_kpis(
        self,
        query_embedding: List[float],
        db: AsyncSession,
        organization_id: Optional[int] = None,
        limit: int = 10,
        similarity_threshold: float = 0.7
    ) -> List[Dict[str, Any]]:
        """Search for KPIs similar to the query embedding using vector similarity."""

        # Build search query.
        # NOTE: only columns that actually exist are selected — kpi_embeddings has
        # no `content`, and kpis has no frequency/calculation_method/data_source.
        # Binding follows SQLAlchemy text() rules (:named + dict), not asyncpg $N.
        vec = "[" + ",".join(str(float(x)) for x in query_embedding) + "]"

        search_query = """
        SELECT
            k.id,
            k.name,
            k.description,
            k.category,
            k.unit,
            k.target_value,
            k.current_value,
            1 - (ke.embedding <=> CAST(:vec AS vector)) AS similarity_score
        FROM kpi_embeddings ke
        JOIN kpis k ON ke.kpi_id = k.id
        WHERE 1 - (ke.embedding <=> CAST(:vec AS vector)) >= :threshold
        """

        params = {"vec": vec, "threshold": similarity_threshold}

        # Add organization filter if provided
        if organization_id:
            search_query += " AND k.organization_id = :org_id"
            params["org_id"] = organization_id

        # Add ordering and limit
        search_query += " ORDER BY similarity_score DESC"

        if limit:
            search_query += " LIMIT :limit"
            params["limit"] = limit

        # Execute query
        result = await db.execute(sql_text(search_query), params)
        rows = result.fetchall()

        # Format results
        kpis = []
        for row in rows:
            kpi_data = {
                "id": row.id,
                "name": row.name,
                "description": row.description,
                "category": row.category,
                "unit": row.unit,
                "target_value": float(row.target_value) if row.target_value else None,
                "current_value": float(row.current_value) if row.current_value else None,
                "similarity_score": float(row.similarity_score)
            }
            kpis.append(kpi_data)

        return kpis
