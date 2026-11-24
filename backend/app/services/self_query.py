"""Turn a natural-language question into a structured metadata filter.

Retrieval accepts file scoping and returns per-chunk provenance - page,
section, heading, parser - but a reader writes the filter in prose: "net sales
in the 2024 annual report", "the cash flow statement", "page 57". Nothing
currently carries that intent from the question to the search, so the filter
words instead go into the embedding, where they dilute the match rather than
narrow it.

A small model splits the question into the part to search for and the part to
filter on. Every decision it makes is checked against real data before use -
file ids against the organisation's own list, sections against the fixed
vocabulary the chunker assigns - so a hallucinated id or an invented section
name cannot reach the query. Any failure at any point returns the raw question
with no filter: a question that retrieves slightly worse is recoverable, and
one that retrieves nothing is not.
"""

import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional, Sequence

import openai

from app.core.config import settings

logger = logging.getLogger(__name__)

# The vocabulary the chunker assigns to _SECTIONS. The planner may only choose
# from this list, so "section" is a match against a known slug rather than a
# substring guess at a heading.
SECTIONS = ("income statement", "comprehensive income", "balance sheet",
            "equity", "cash flow")

# A filter that leaves fewer candidates than this is discarded rather than
# applied. The answer prompt refuses when it cannot ground a figure, so an
# over-narrow filter does not degrade to a worse answer - it degrades to a
# confident "not found", which is the most expensive output this system has.
MIN_CANDIDATES = 5

_SYSTEM = (
    "Convert a question about uploaded financial documents into a JSON plan.\n"
    '  "query": the text to search for, with wording about which file, page '
    "or section to look in removed.\n"
    '  "file_ids": ids to restrict to, chosen ONLY from the provided list by '
    "matching the wording to a filename. [] if the question names no file.\n"
    '  "page_min" / "page_max": integers if a page or page range is named, '
    "otherwise null.\n"
    '  "section": one of the listed section names if the question names a '
    "financial statement, otherwise null.\n"
    "Return ONLY the JSON object. Invent no id, page or section name."
)


def _as_page(value: Any) -> Optional[int]:
    """A page number the model supplied, or None if it is not usable.

    ``isinstance(True, int)`` is true in Python, so a model that answers with
    a boolean would otherwise set page_min to 1 and silently restrict the
    search to the first page of the document.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value > 0 else None


def _grounded_query(rewritten: Any, question: str) -> str:
    """The rewritten search string, or the question when the rewrite drifted.

    The rewrite is only meant to drop wording about where to look. A reply
    that shares no words with the question is not a narrower version of it,
    it is a different question - asked "hi", the planner returned "financial
    documents", which would search for something the reader never mentioned.
    """
    candidate = (rewritten or "").strip() if isinstance(rewritten, str) else ""
    if not candidate:
        return question
    asked = set(re.findall(r"\w+", question.lower()))
    if not asked & set(re.findall(r"\w+", candidate.lower())):
        logger.info("Self-query rewrote %r as %r; keeping the question",
                    question, candidate)
        return question
    return candidate


class SelfQuery:
    """Plans a filtered retrieval from a natural-language question."""

    def __init__(self) -> None:
        # The small context model, not the answering model. This call sits in
        # front of every question, and the generation model's context is
        # shared across in-flight requests on a local server - putting a
        # second large request there costs latency on the answer itself.
        self.model = settings.CONTEXT_MODEL or settings.LLM_MODEL
        self.client = openai.OpenAI(
            base_url=settings.LLM_BASE_URL,
            api_key=settings.LLM_API_KEY or settings.OPENAI_API_KEY or "local",
        )

    def _generate(self, question: str, files: Sequence[Dict[str, Any]]) -> str:
        catalogue = "\n".join(
            f"  {f['id']}: {f['original_filename']}" for f in files)
        completion = self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            max_tokens=200,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content":
                 f"Documents:\n{catalogue}\n\n"
                 f"Section names: {', '.join(SECTIONS)}\n\n"
                 f"Question: {question}\n\nJSON:"},
            ],
        )
        return (completion.choices[0].message.content or "").strip()

    async def plan(self, question: str,
                   files: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        """Split a question into a search string and a metadata filter."""
        default = {"query": question, "file_ids": [], "page_min": None,
                   "page_max": None, "section": None}
        # With a single document there is nothing for file scoping to choose
        # between, and the other fields do not justify a round trip on their
        # own. Planning starts paying once the organisation has a library.
        if len(files) < 2:
            return default
        try:
            raw = await asyncio.to_thread(self._generate, question, files)
            plan = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
            if not isinstance(plan, dict):
                raise ValueError("plan is not an object")
        except Exception as err:  # pylint: disable=broad-exception-caught
            # Fail-open by design: an unreachable model, a non-JSON reply or a
            # malformed plan must all cost ranking quality, never an answer.
            logger.warning("Self-query failed, using raw question: %s", err)
            return default

        known = {f["id"] for f in files}
        section = plan.get("section")
        query = _grounded_query(plan.get("query"), question)
        return {
            "query": query,
            "file_ids": [i for i in (plan.get("file_ids") or [])
                         if isinstance(i, int) and not isinstance(i, bool)
                         and i in known],
            "page_min": _as_page(plan.get("page_min")),
            "page_max": _as_page(plan.get("page_max")),
            "section": section if section in SECTIONS else None,
        }


def _matches(candidate: Dict[str, Any], page_min: Optional[int],
             page_max: Optional[int], section: Optional[str]) -> bool:
    meta = candidate.get("chunk_metadata") or {}
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except ValueError:
            return True
    page = meta.get("page_number")
    if page_min is not None and (page is None or page < page_min):
        return False
    if page_max is not None and (page is None or page > page_max):
        return False
    if section and meta.get("section") != section:
        return False
    return True


def apply_metadata_filter(candidates: List[Dict[str, Any]],
                          page_min: Optional[int] = None,
                          page_max: Optional[int] = None,
                          section: Optional[str] = None
                          ) -> List[Dict[str, Any]]:
    """Narrow retrieved chunks on page range and section, if it is safe to.

    Applied after retrieval, so no SQL changes and no schema migration - but
    that also bounds what it can do. A post-filter can only narrow what the
    search already surfaced; it cannot reach further down the ranking to find
    chunks the filter would have admitted. File scoping is the filter that
    genuinely searches a narrower corpus, because it reaches the SQL.

    The filter is a preference, not a gate. Dropping below MIN_CANDIDATES
    discards it and keeps the unfiltered list, because the planner's page and
    section calls are guesses about a document it has not read.
    """
    if not candidates or (page_min is None and page_max is None
                          and section is None):
        return candidates
    kept = [c for c in candidates
            if _matches(c, page_min, page_max, section)]
    if len(kept) < min(MIN_CANDIDATES, len(candidates)):
        logger.info(
            "Metadata filter (page %s-%s, section %s) left %d of %d "
            "candidates; ignoring it", page_min, page_max, section,
            len(kept), len(candidates))
        return candidates
    return kept
