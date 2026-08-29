"""Embedding generation and vector-similarity search for documents and KPIs."""

import logging
import re
from typing import List, Dict, Any, Optional

import openai
from sqlalchemy import select, text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.file import DocumentEmbedding, UploadedFile
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

    # pdfplumber positions glyphs, not words: column gaps become runs of tabs
    # and words get split mid-token ("Total ne\tt sales", "Sept\tember 27").
    # Cleaning this before embedding removes noise the model would otherwise
    # have to see through, and makes retrieved chunks readable in the UI.
    _TAB_RUN = re.compile(r"\t{2,}")
    _SPACE_RUN = re.compile(r"[ ]{3,}")
    # A SINGLE tab between letters is pdfplumber splitting one word; a column
    # boundary shows up as a run of two or more tabs. That distinction is what
    # makes rejoining safe - "Total ne\tt sales" merges, "Products\t\t$" does not.
    _SPLIT_WORD = re.compile(r"([A-Za-z])\t([A-Za-z]{1,8})(?=[\s\t]|$)")
    _BLANK_RUN = re.compile(r"\n{3,}")

    @classmethod
    def clean_text(cls, text: str) -> str:
        """Repair pdfplumber artefacts without destroying column structure."""
        # Rejoin words broken by a single tab ("ne\tt sales" -> "net sales").
        # Applied twice: some words are split more than once.
        for _ in range(2):
            text = cls._SPLIT_WORD.sub(r"\1\2", text)
        text = cls._TAB_RUN.sub("\t", text)      # keep ONE tab as a column break
        text = cls._SPACE_RUN.sub(" ", text)
        text = cls._BLANK_RUN.sub("\n\n", text)
        return text

    # Lines at the top of a table block that identify it: title, units
    # ("In millions"), "Years ended", and the column headers. These must ride
    # along with every chunk of that table.
    HEADER_LINES = 12

    _MARKER = re.compile(
        r"^\[page (?P<page>\d+) table (?P<table>\d+)(?: via (?P<source>[^\]]+))?\]"
    )

    @classmethod
    def _block_meta(cls, block: str) -> Dict[str, Any]:
        """Pull page / table / source out of a block's leading marker."""
        m = cls._MARKER.match(block.strip())
        if not m:
            return {}
        return {
            "page_number": int(m.group("page")),
            "table_index": int(m.group("table")),
            "parser": (m.group("source") or "").strip() or None,
        }

    @staticmethod
    def _heading_of(block: str) -> Optional[str]:
        """Best-effort section heading: the first substantial text line."""
        for line in block.split("\n")[1:8]:
            candidate = re.sub(r"[\t ]+", " ", line).strip()
            if len(candidate) >= 8 and not re.fullmatch(r"[\d\s.,()$%-]+", candidate):
                return candidate[:120]
        return None

    @staticmethod
    def _split_blocks(text: str) -> List[str]:
        """Split flattened text into per-table blocks on the [page N table M] marker."""
        blocks: List[str] = []
        current: List[str] = []
        for line in text.split("\n"):
            if line.startswith("[page ") and current:
                blocks.append("\n".join(current))
                current = [line]
            else:
                current.append(line)
        if current:
            blocks.append("\n".join(current))
        return [b for b in blocks if b.strip()]

    async def chunk_document(
        self, text: str, chunk_size: Optional[int] = None,
        overlap: Optional[int] = None, source_file: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Chunk the document and carry per-chunk provenance alongside the text.

        Every chunk records the page, table, parser and nearest heading it came
        from, so retrieval can filter on them and the UI can tell the reader
        which page of the PDF an answer is grounded in.
        """
        if chunk_size is None:
            chunk_size = settings.CHUNK_SIZE
        if overlap is None:
            overlap = settings.CHUNK_OVERLAP

        out: List[Dict[str, Any]] = []
        for block in self._split_blocks(self.clean_text(text)):
            meta = self._block_meta(block)
            meta["heading"] = self._heading_of(block)
            lines = block.split("\n")
            header = "\n".join(lines[: self.HEADER_LINES]).strip()
            body = "\n".join(lines[self.HEADER_LINES :])

            pieces: List[str] = []
            if not body.strip():
                pieces.append(block[:chunk_size])
            else:
                budget = max(chunk_size - len(header) - 1, chunk_size // 2)
                start = 0
                while start < len(body):
                    piece = body[start : start + budget]
                    pieces.append(f"{header}\n{piece}" if header else piece)
                    nxt = start + budget - overlap
                    if nxt <= start:
                        break
                    start = nxt

            # Contextual prefix: a chunk separated from its document loses the
            # only clues about what it describes. Stating the source, page and
            # section up front costs a few tokens and lets the model cite them.
            bits = []
            if source_file:
                bits.append(f"Document: {source_file}")
            if meta.get("page_number") is not None:
                bits.append(f"Page {meta['page_number']}")
            if meta.get("heading"):
                bits.append(f"Section: {meta['heading']}")
            prefix = f"[{' | '.join(bits)}]\n" if bits else ""

            for piece in pieces:
                if piece.strip():
                    out.append({"text": prefix + piece, **meta})
        return out

    async def chunk_text(self, text: str, chunk_size: Optional[int] = None,
                         overlap: Optional[int] = None) -> List[str]:
        """Split text into chunks, keeping each table's header with its rows.

        A plain character-window split orphans the header block (table title,
        "(In millions)", and the year columns) from the numeric rows, so a
        retrieved chunk arrives with unlabelled columns and the model guesses
        the period and units. Every chunk therefore repeats its table's header.
        """
        if chunk_size is None:
            chunk_size = settings.CHUNK_SIZE
        if overlap is None:
            overlap = settings.CHUNK_OVERLAP

        chunks: List[str] = []
        for block in self._split_blocks(text):
            lines = block.split("\n")
            header = "\n".join(lines[: self.HEADER_LINES]).strip()
            body = "\n".join(lines[self.HEADER_LINES :])

            if not body.strip():
                chunks.append(block[:chunk_size])
                continue

            budget = max(chunk_size - len(header) - 1, chunk_size // 2)
            start = 0
            while start < len(body):
                piece = body[start : start + budget]
                chunks.append(f"{header}\n{piece}" if header else piece)
                nxt = start + budget - overlap
                if nxt <= start:
                    break
                start = nxt

        return [c for c in chunks if c.strip()]

    async def create_document_embeddings(
        self, file_id: int, text: str, db: AsyncSession
    ) -> List[DocumentEmbedding]:
        """Create embeddings for document chunks."""
        source_file = None
        if db is not None:
            try:
                source_file = (await db.execute(
                    select(UploadedFile.original_filename)
                    .where(UploadedFile.id == file_id)
                )).scalar_one_or_none()
            except Exception:  # provenance is nice-to-have, never fatal
                source_file = None

        # Chunk with provenance so each row records its page / table / heading.
        pieces = await self.chunk_document(text, source_file=source_file)
        chunks = [p["text"] for p in pieces]
        embeddings = []

        # Embed in batches rather than one HTTP round-trip per chunk. A large
        # PDF produces hundreds of chunks; sequentially that is hundreds of
        # sequential requests and dominates upload time.
        batch_size = 64
        vectors: List[List[float]] = []
        for start in range(0, len(chunks), batch_size):
            vectors.extend(
                await self.batch_create_embeddings(chunks[start:start + batch_size])
            )

        for i, chunk in enumerate(chunks):
            embedding_vector = vectors[i]

            # Create document embedding record
            doc_embedding = DocumentEmbedding(
                file_id=file_id,
                content_chunk=chunk,
                embedding=embedding_vector,
                chunk_index=i,
                chunk_metadata={
                    "chunk_size": len(chunk),
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                    "source_file": source_file,
                    "page_number": pieces[i].get("page_number"),
                    "table_index": pieces[i].get("table_index"),
                    "parser": pieces[i].get("parser"),
                    "heading": pieces[i].get("heading"),
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

    async def search_documents_hybrid(
        self,
        query: str,
        organization_id: int,
        file_ids: Optional[List[int]] = None,
        limit: int = 10,
        similarity_threshold: float = 0.05,
        db: Optional[AsyncSession] = None,
        candidates: int = 30,
        rrf_k: int = 60,
    ) -> List[Dict[str, Any]]:
        """Retrieve chunks using BOTH vector similarity and keyword search.

        Pure vector search misses exact tokens - identifiers, statement line
        names, specific figures - because an embedding blurs them into meaning.
        Pure keyword search misses paraphrase. Running both and fusing the two
        rankings with Reciprocal Rank Fusion keeps each one's strengths without
        having to tune a weight between two incomparable score scales.

        RRF score for a chunk = sum over lists of 1 / (rrf_k + rank_in_list).
        """
        vector_hits = await self.search_documents(
            query=query, organization_id=organization_id, file_ids=file_ids,
            limit=candidates, similarity_threshold=similarity_threshold, db=db,
        )
        keyword_hits = await self.search_documents_keyword(
            query=query, organization_id=organization_id, file_ids=file_ids,
            limit=candidates, db=db,
        )

        fused: Dict[tuple, Dict[str, Any]] = {}
        for source, hits in (("vector", vector_hits), ("keyword", keyword_hits)):
            for rank, hit in enumerate(hits):
                key = (hit["file_id"], hit.get("chunk_index"))
                entry = fused.setdefault(key, {**hit, "rrf_score": 0.0,
                                                "matched_by": []})
                entry["rrf_score"] += 1.0 / (rrf_k + rank + 1)
                entry["matched_by"].append(source)
                # Keep the real cosine score when the vector list supplied it.
                if source == "vector":
                    entry["similarity_score"] = hit["similarity_score"]

        ranked = sorted(fused.values(), key=lambda h: h["rrf_score"], reverse=True)
        return ranked[:limit]

    async def search_documents_keyword(
        self,
        query: str,
        organization_id: int,
        file_ids: Optional[List[int]] = None,
        limit: int = 10,
        db: Optional[AsyncSession] = None,
    ) -> List[Dict[str, Any]]:
        """Full-text (keyword) search over chunks, ranked by ts_rank."""
        sql = """
        SELECT
            de.content_chunk,
            de.file_id,
            uf.original_filename,
            de.chunk_index,
            de.chunk_metadata,
            ts_rank(to_tsvector('english', de.content_chunk),
                    websearch_to_tsquery('english', :q)) AS rank
        FROM document_embeddings de
        JOIN uploaded_files uf ON de.file_id = uf.id
        WHERE uf.organization_id = :org_id
          AND to_tsvector('english', de.content_chunk)
              @@ websearch_to_tsquery('english', :q)
        """
        params: Dict[str, Any] = {"q": query, "org_id": organization_id,
                                  "limit": limit}
        if file_ids:
            sql += " AND de.file_id = ANY(:file_ids)"
            params["file_ids"] = list(file_ids)
        sql += " ORDER BY rank DESC LIMIT :limit"

        try:
            result = await db.execute(sql_text(sql), params)
            rows = result.fetchall()
        except Exception as err:  # a malformed query should not kill retrieval
            logger.warning("Keyword search failed: %s", err)
            return []

        return [{
            "content_chunk": row[0],
            "file_id": row[1],
            "filename": row[2],
            "chunk_index": row[3],
            "chunk_metadata": row[4],
            "similarity_score": 0.0,
            "keyword_rank": float(row[5]),
        } for row in rows]

    async def search_documents(
        self,
        query: str,
        organization_id: int,
        file_ids: Optional[List[int]] = None,
        limit: int = 10,
        similarity_threshold: float = 0.7,
        db: Optional[AsyncSession] = None
    ) -> List[Dict[str, Any]]:
        """Search documents using vector similarity."""
        # Generate embedding for query
        query_embedding = await self.generate_embedding(query)

        # Build search query.
        # NOTE: this runs through SQLAlchemy text(), so it uses :named bind params
        # and a dict - not asyncpg's $1 positional style. The query vector is bound
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
        db: Optional[AsyncSession] = None
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
        db: Optional[AsyncSession] = None
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
        # NOTE: only columns that actually exist are selected - kpi_embeddings has
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
