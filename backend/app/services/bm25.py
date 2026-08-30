"""In-process BM25 index over stored document chunks.

Postgres full-text search is the obvious lexical half of a hybrid retriever,
but ts_rank is not BM25 and the gap is not cosmetic:

  * ts_rank carries no corpus statistics, so it has no IDF. A rare, highly
    discriminating token is weighted exactly like a common one, and queries
    made of a single figure come back as a block of identically scored rows
    whose order is arbitrary.
  * websearch_to_tsquery is AND semantics. A chunk must contain every query
    term to match at all, so "diluted EPS" matched one chunk in a 612-chunk
    document while the pages actually carrying the EPS figures never entered
    the candidate list.
  * The 'english' configuration splits numbers on commas: "219,024" is indexed
    as "219" and "024". Exact figure lookup, which is most of what anyone asks
    a financial document, cannot work through it.

This module fixes all three. Tokenisation keeps figures whole, stemming is
limited to the noun plurals that dominate financial prose, and scoring is
standard Okapi BM25 with OR semantics over the query terms.
"""

import asyncio
import heapq
import logging
import math
import re
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

K1 = 1.5
B = 0.75

# Keep commas, dots and hyphens inside a token so "219,024", "1.5" and
# "volume-based" survive as single terms rather than being shredded.
_TOKEN = re.compile(r"[a-z0-9][a-z0-9,.\-']*")


def _stem(word: str) -> str:
    """Fold the noun plurals that matter in financial text.

    A full Porter stemmer would be a dependency and most of its rules address
    verb morphology this corpus barely uses. The ordering matters: "losses"
    must reach "loss" and "liabilities" must reach "liability", while
    "expenses" must still reach "expense" and "business" must not move.
    """
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith(("sses", "xes", "ches", "shes")):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith(
            ("ss", "us", "is")):
        return word[:-1]
    return word


def tokenize(text: str) -> List[str]:
    """Split text into BM25 terms, preserving figures."""
    out: List[str] = []
    for raw in _TOKEN.findall(text.lower()):
        token = raw.strip(".,-'")
        if not token:
            continue
        if token[0].isdigit():
            out.append(token)
            # Index the separator-free form too, so a question written
            # "219024" still reaches a chunk that says "219,024".
            bare = token.replace(",", "")
            if bare != token:
                out.append(bare)
            continue
        out.append(_stem(token))
    return out


class Bm25Index:
    """Okapi BM25 over a fixed set of chunks.

    Built once and reused. Postings are term -> [(doc, term frequency)], so a
    query touches only the documents that contain one of its terms.
    """

    def __init__(self, rows: Sequence[Tuple[Any, ...]]) -> None:
        # rows: (content_chunk, file_id, organization_id, filename,
        #        chunk_index, chunk_metadata)
        self.rows = list(rows)
        self.lengths: List[int] = []
        self.postings: Dict[str, List[Tuple[int, int]]] = defaultdict(list)

        for doc, row in enumerate(self.rows):
            terms = Counter(tokenize(row[0] or ""))
            self.lengths.append(sum(terms.values()) or 1)
            for term, freq in terms.items():
                self.postings[term].append((doc, freq))

        self.total = len(self.rows)
        self.avg_length = (sum(self.lengths) / self.total) if self.total else 1.0

    def _idf(self, term: str) -> float:
        docs_with_term = len(self.postings.get(term, ()))
        return math.log(
            1 + (self.total - docs_with_term + 0.5) / (docs_with_term + 0.5)
        )

    def search(self, query: str, organization_id: Optional[int],
               file_ids: Optional[List[int]], limit: int) -> List[int]:
        """Return document positions, best first."""
        scores: Dict[int, float] = defaultdict(float)
        allowed = set(file_ids) if file_ids else None

        for term in set(tokenize(query)):
            postings = self.postings.get(term)
            if not postings:
                continue
            idf = self._idf(term)
            for doc, freq in postings:
                row = self.rows[doc]
                # Same scoping the SQL applied: an organization only ever sees
                # its own files.
                if row[2] != organization_id:
                    continue
                if allowed is not None and row[1] not in allowed:
                    continue
                norm = 1 - B + B * self.lengths[doc] / self.avg_length
                scores[doc] += idf * freq * (K1 + 1) / (freq + K1 * norm)

        return [doc for doc, _ in heapq.nlargest(
            limit, scores.items(), key=lambda kv: kv[1])]


class _Cache:
    """Process-wide index plus the fingerprint it was built from."""

    index: Optional[Bm25Index] = None
    fingerprint: Optional[Tuple[int, int]] = None
    lock = asyncio.Lock()


_FINGERPRINT_SQL = "SELECT count(*), coalesce(max(id), 0) FROM document_embeddings"

_ROWS_SQL = """
SELECT de.content_chunk, de.file_id, uf.organization_id,
       uf.original_filename, de.chunk_index, de.chunk_metadata
FROM document_embeddings de
JOIN uploaded_files uf ON de.file_id = uf.id
ORDER BY de.id
"""


async def get_index(db: AsyncSession) -> Bm25Index:
    """Return the current index, rebuilding it if the chunk table changed.

    The fingerprint is (row count, max id). Ingest deletes a file's chunks and
    reinserts them, which moves max id, and any add or removal moves the count.
    Checking it on every search costs one trivial query and means a document
    becomes lexically searchable the moment it is written - including when the
    write happened in another worker, which a TTL or an explicit invalidation
    call from the ingest path would both miss.
    """
    fingerprint = tuple((await db.execute(sql_text(_FINGERPRINT_SQL))).one())

    async with _Cache.lock:
        if _Cache.index is None or _Cache.fingerprint != fingerprint:
            rows = (await db.execute(sql_text(_ROWS_SQL))).all()
            # Tokenising the whole corpus is CPU-bound; off the event loop it
            # cannot stall unrelated requests.
            _Cache.index = await asyncio.to_thread(Bm25Index, rows)
            _Cache.fingerprint = fingerprint
            logger.info("BM25 index built: %d chunks", _Cache.index.total)
        return _Cache.index
