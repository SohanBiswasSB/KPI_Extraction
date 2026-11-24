"""Generate a one-line context for each chunk before it is indexed.

A chunk pulled out of a document loses the only clues about what it describes.
The chunker already prepends a mechanical label - filename, page, and the first
substantial line of the block used as a heading - but on this corpus that first
line is a real heading only about a third of the time; the rest are the opening
words of a paragraph, truncated mid-sentence, which add noise to both the
vector and the lexical index.

Asking a small instruct model to state what the excerpt reports produces a
sentence that names the subject and period, introducing terms that do not
appear in the chunk itself. That helps the embedding and the BM25 index alike.

Two properties matter more than the generation itself:

  * Nothing invented. A context line that names the wrong year gets embedded
    and indexed, and then pulls wrong-year matches - exactly the failure this
    project has spent the most effort eliminating. Any generated line naming a
    year absent from its chunk is discarded rather than trusted.
  * Nothing regenerated needlessly. The cache is keyed on a hash of the chunk
    text, so re-chunking only pays for chunks whose text actually changed.
"""

import asyncio
import hashlib
import logging
import re
import time
from typing import Awaitable, Callable, Dict, List, Optional, Sequence

import openai
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.file import ChunkContext

logger = logging.getLogger(__name__)

_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")

_SYSTEM = (
    "You situate an excerpt within its source document so it can be found by "
    "search. Reply with ONE sentence, under 30 words, naming what the excerpt "
    "reports and the period it covers if stated. Do not state any figure or "
    "period that is not written in the excerpt. No preamble."
)

ProgressCb = Callable[[int, int], Awaitable[None]]


def content_hash(text: str) -> str:
    """Stable key for a chunk's text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _accept(generated: str, chunk: str) -> Optional[str]:
    """Return the line if it is safe to index, otherwise None.

    The check is deliberately deterministic. A model that scored clean on a
    sample can still invent a period on the chunk that matters, and a wrong
    year in the indexed text is worse than no context at all.
    """
    line = " ".join(generated.split()).strip().strip('"')
    if not line or len(line) > settings.CONTEXT_MAX_OUTPUT_CHARS:
        return None
    invented = {m.group(0) for m in _YEAR.finditer(line)} - {
        m.group(0) for m in _YEAR.finditer(chunk)
    }
    return None if invented else line


class ContextService:
    """Generates and caches per-chunk context lines."""

    def __init__(self) -> None:
        self.model = settings.CONTEXT_MODEL or settings.LLM_MODEL
        self.client = openai.OpenAI(
            base_url=settings.LLM_BASE_URL,
            api_key=settings.LLM_API_KEY or settings.OPENAI_API_KEY or "local",
        )

    def _generate(self, document: str, chunk: str) -> str:
        completion = self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            max_tokens=80,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content":
                 f"Document: {document}\n\nExcerpt:\n"
                 f"{chunk[:settings.CONTEXT_MAX_CHARS]}\n\nOne sentence:"},
            ],
        )
        return (completion.choices[0].message.content or "").strip()

    async def contextualize(
        self,
        chunks: Sequence[str],
        document: str,
        db: AsyncSession,
        progress_cb: Optional[ProgressCb] = None,
    ) -> Dict[str, str]:
        """Return {content_hash: context} for the given chunks.

        Cached hashes are never regenerated. Failures are skipped rather than
        raised: a chunk without a context line is merely less findable, which
        must not be allowed to fail an upload.
        """
        wanted = {content_hash(c): c for c in chunks}
        cached = await self._load_cached(list(wanted), self.model, db)
        pending = [(h, c) for h, c in wanted.items() if h not in cached]

        logger.info(
            "Contextualizing %s: %d chunk(s), %d cached, %d to generate "
            "(model %s, concurrency %d)",
            document, len(wanted), len(cached), len(pending),
            self.model, settings.CONTEXT_CONCURRENCY,
        )
        if not pending:
            if progress_cb:
                await progress_cb(len(wanted), len(wanted))
            return cached

        results: Dict[str, str] = dict(cached)
        done = len(cached)
        total = len(wanted)
        semaphore = asyncio.Semaphore(max(settings.CONTEXT_CONCURRENCY, 1))
        lock = asyncio.Lock()
        started = time.monotonic()

        async def one(chunk_hash: str, chunk: str) -> None:
            nonlocal done
            line: Optional[str] = None
            async with semaphore:
                try:
                    # to_thread: the openai client is synchronous and would
                    # otherwise block the event loop for the whole run.
                    raw = await asyncio.to_thread(self._generate, document, chunk)
                    line = _accept(raw, chunk)
                except Exception as err:
                    logger.warning("Context generation failed: %s", err)
            async with lock:
                if line:
                    results[chunk_hash] = line
                    db.add(ChunkContext(content_hash=chunk_hash, context=line,
                                        model=self.model))
                done += 1
                if progress_cb:
                    await progress_cb(done, total)

        await asyncio.gather(*(one(h, c) for h, c in pending))
        await db.commit()

        elapsed = time.monotonic() - started
        logger.info(
            "Contextualized %s: %d generated, %d rejected or failed, %.0fs "
            "(%.2fs/chunk)",
            document, len(results) - len(cached),
            len(pending) - (len(results) - len(cached)), elapsed,
            elapsed / max(len(pending), 1),
        )
        return results

    @staticmethod
    async def _load_cached(hashes: List[str], model: str,
                           db: AsyncSession) -> Dict[str, str]:
        """Fetch already-generated contexts, in batches Postgres will accept."""
        found: Dict[str, str] = {}
        for start in range(0, len(hashes), 1000):
            rows = await db.execute(
                select(ChunkContext.content_hash, ChunkContext.context)
                .where(ChunkContext.content_hash.in_(hashes[start:start + 1000]))
                .where(ChunkContext.model == model)
            )
            found.update(dict(rows.all()))
        return found
