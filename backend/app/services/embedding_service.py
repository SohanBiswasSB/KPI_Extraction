"""Embedding generation and vector-similarity search for documents and KPIs."""

import asyncio
import logging
import re
from typing import List, Dict, Any, Optional

import openai
from sqlalchemy import select, text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.file import DocumentEmbedding, UploadedFile
from app.services import bm25, windowing
from app.services.context_service import ContextService, content_hash
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
            # to_thread: the openai client is synchronous, and calling it
            # directly from an async handler blocks uvicorn's event loop, so
            # the whole API stops answering while a document is processed.
            response = await asyncio.to_thread(
                self.client.embeddings.create,
                model=self.embedding_model,
                input=text,
            )
            return response.data[0].embedding
        except Exception as err:
            # Never fall back to a zero vector. pgvector's cosine distance
            # against a zero vector is NaN, Postgres orders NaN as LARGER than
            # every real number, so corrupt rows survive the similarity
            # threshold and sort to the TOP of every search - and the NaN then
            # fails JSON serialisation, surfacing as an opaque HTTP 500.
            # Failing here instead keeps the index honest.
            logger.error("Error generating embedding: %s", err)
            raise RuntimeError(f"Embedding generation failed: {err}") from err

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

    # Figures get broken the same way words do ("4,0\t57", "$7\t3.6", "2\t2%"),
    # but the single-tab test that works for words is not safe for digits: two
    # adjacent year headers are written "2025\t2024" with one tab and must stay
    # apart. These decide the question on numeric well-formedness instead.
    _NUMBER_PAIR = re.compile(r"(\d[\d,]*)(\t+)(\d[\d,]*)")
    _GROUPED_NUMBER = re.compile(r"^\d{1,3}(,\d{3})*$")
    _SPLIT_GROUP = re.compile(r"(?<![\d,])(\d{1,2})\t+(\d{1,3}(?:,\d{3})+)(?![\d,])")

    @classmethod
    def _rejoin_split_group(cls, line: str) -> str:
        """Rejoin a figure whose leading digits fell into their own column.

        Two guards, both needed. Measured over the Apple 10-K the shape alone
        fires eight times, and three of those are genuine adjacent columns in
        the marketable-securities tables: joining them produces "9422,910" and
        "2616,027", which are not numbers, and "281,038", which is - on a row
        whose other figures are four digits long.

        So the join must produce a properly grouped number, AND one the same
        length as another figure already on the line. A statement row reports
        the same quantity across years, so its figures agree in magnitude;
        pasting two unrelated columns together almost never lands there.
        """
        if not cls._SPLIT_GROUP.search(line):
            return line
        widths = {len(cell.strip().replace(",", ""))
                  for cell in line.split("\t")
                  if cls._GROUPED_NUMBER.match(cell.strip())}

        def merge(match):
            joined = match.group(1) + match.group(2)
            if not cls._GROUPED_NUMBER.match(joined):
                return match.group(0)
            if len(joined.replace(",", "")) not in widths:
                return match.group(0)
            return joined

        return cls._SPLIT_GROUP.sub(merge, line)
    _YEARISH = re.compile(r"^(\d{4})[,.]?$")

    @classmethod
    def _rejoin_number(cls, match: "re.Match") -> str:
        """Fuse a number split across a tab, or leave a column break alone."""
        left, tabs, right = match.group(1), match.group(2), match.group(3)

        # "December 31, 2025" is two tokens, not one number: keep them apart
        # but drop the tab, so the date reads normally.
        year = cls._YEARISH.match(right)
        if left.endswith(",") and year and 1900 <= int(year.group(1)) <= 2100:
            return f"{left} {right}"

        joined = left + right
        core = joined.rstrip(",.")
        if "," in core:
            # Fuse only when the result is correctly thousand-grouped. This is
            # what rejects a genuine column break like "219,024" + "100", whose
            # concatenation "219,024100" is not a valid figure.
            return joined if cls._GROUPED_NUMBER.match(core) else match.group(0)
        if len(tabs) > 1:
            return match.group(0)      # a run of tabs is a column boundary
        # Nothing to validate against without a comma, so allow only short
        # results. This is what keeps the year headers "2025" and "2024" apart.
        return joined if len(core) <= 4 else match.group(0)

    @classmethod
    def clean_text(cls, text: str) -> str:
        """Repair pdfplumber artefacts without destroying column structure."""
        # Rejoin words broken by a single tab ("ne\tt sales" -> "net sales").
        # Applied twice: some words are split more than once.
        for _ in range(2):
            text = cls._SPLIT_WORD.sub(r"\1\2", text)
        # Repeated: one pass fuses "2" + "025", a second reaches "2025" + ",".
        # Must run before the tab runs collapse, since the run length is part
        # of how a column break is told from a split figure.
        for _ in range(3):
            repaired = cls._NUMBER_PAIR.sub(cls._rejoin_number, text)
            if repaired == text:
                break
            text = repaired
        # A leading digit group separated from the rest of its own number by a
        # column break: "118,254" arrives as "1<tab>18,254". _NUMBER_PAIR
        # cannot reach these - scanning left to right it tests the PRECEDING
        # figure against the fragment ("111,482" + "1"), rejects that join,
        # and consumes the fragment with it, so the pairing that would have
        # worked is never considered. Anchored on a fragment of one or two
        # digits followed by a properly grouped number, which is not a shape
        # a real pair of adjacent columns takes in a financial statement.
        text = "\n".join(cls._rejoin_split_group(line)
                         for line in text.split("\n"))
        text = cls._TAB_RUN.sub("\t", text)      # keep ONE tab as a column break
        text = cls._SPACE_RUN.sub(" ", text)
        text = cls._BLANK_RUN.sub("\n\n", text)
        return text

    # Lines at the top of a table block that identify it: title, units
    # ("In millions"), "Years ended", and the column headers. These must ride
    # along with every chunk of that table.
    HEADER_LINES = 12

    # A block needs at least this many genuine data rows before it is treated
    # as a table. Below it, the block is prose that pdfplumber happened to
    # return from extract_tables().
    MIN_NUMERIC_ROWS = 3

    # ...and those rows must be this share of every multi-cell row in the
    # block. The absolute floor alone is not enough: pdfplumber returns whole
    # pages of MD&A and risk-factor prose from extract_tables(), and once its
    # glyph positioning has scattered tabs through a sentence, any three lines
    # holding a year and a figure satisfy the floor. Measured over the Apple
    # 10-K, that misclassified 10 of 26 blocks. Numeric rows as a fraction of
    # multi-cell rows separates them cleanly: the prose blocks run 0.11-0.23
    # and the real statements 0.29-0.82.
    MIN_NUMERIC_ROW_RATIO = 0.25

    _CID_ARTEFACT = re.compile(r"\(cid:\d+\)")
    # A cell holding only a number, allowing the accounting decorations that
    # surround figures in financial statements: $ , . % and ( ) for negatives.
    _NUMERIC_CELL = re.compile(r"^[\s$(]*[\d,]+(?:\.\d+)?\)?[%]?$")

    @classmethod
    def _is_garbage(cls, body: str) -> bool:
        """True when a block is font-decode noise rather than text.

        pdfplumber emits runs of "(cid:NN)" when a PDF embeds a font with no
        ToUnicode map, so the glyphs cannot be resolved to characters. The
        result is not text in any language; embedding it only produces vectors
        that compete for top-k slots in every subsequent search.
        """
        hits = cls._CID_ARTEFACT.findall(body)
        if not hits:
            return False
        return sum(len(h) for h in hits) / max(len(body), 1) > 0.20

    @classmethod
    def _is_tabular(cls, body: str) -> bool:
        """True when a block is a real data table, not tab-broken prose.

        A digit ratio is not enough: financial tables are routinely introduced
        by a sentence or two, which dilutes it below any workable threshold.
        Counting rows that hold two or more purely numeric cells tests the
        structure instead, which is what actually distinguishes the two, and
        requiring them to be a minimum share of the block's multi-cell rows
        keeps tab-mangled prose from clearing the bar on three stray lines.
        """
        rows = 0
        multi_cell = 0
        for line in body.split("\n"):
            cells = [c.strip() for c in line.split("\t") if c.strip()]
            if len(cells) < 2:
                continue
            multi_cell += 1
            if sum(1 for c in cells if cls._NUMERIC_CELL.match(c)) >= 2:
                rows += 1
        if rows < cls.MIN_NUMERIC_ROWS or not multi_cell:
            return False
        return rows / multi_cell >= cls.MIN_NUMERIC_ROW_RATIO

    # The repeated header may take at most this share of a chunk. Past it,
    # the chunk is mostly a copy of its neighbours and the unique text it was
    # cut to carry is the minority of what gets embedded.
    HEADER_BUDGET = 0.33

    # However the fixed costs fall, at least this share of a chunk must be
    # the body text it was cut to carry. Header and prefix are both bounded,
    # but a small chunk plus a long prefix can still leave a body budget of a
    # few dozen characters, and a window that advances a few dozen characters
    # at a time turns one page into thousands of near-identical chunks.
    BODY_FLOOR = 0.5

    @classmethod
    def _trim_header(cls, header: str, cap: int) -> str:
        """Cut the repeated header down to ``cap`` characters.

        Truncation is on a line boundary: a header is a title, a units note
        and column labels, and half a column label repeated on every chunk is
        worse than none.
        """
        if cap <= 0:
            return ""
        if len(header) <= cap:
            return header
        kept: List[str] = []
        used = 0
        for line in header.split("\n"):
            if used + len(line) + 1 > cap:
                break
            kept.append(line)
            used += len(line) + 1
        return "\n".join(kept)

    @classmethod
    def _window(cls, body: str, header: str, chunk_size: int,
                overlap: int, reserve: int = 0) -> List[str]:
        """Slide a window over body, repeating header on each piece.

        ``chunk_size`` is a hard ceiling on the returned text, and ``reserve``
        holds back room for a prefix the caller adds afterwards. The header is
        charged against the budget rather than added on top of it: the earlier
        version floored the budget at half the chunk and then prepended the
        header whole, so a long header produced chunks twice the configured
        size of which three quarters was text duplicated from its neighbours.
        """
        if not body.strip():
            return []
        floor = max(int(chunk_size * cls.BODY_FLOOR), 1)
        available = chunk_size - reserve
        header = cls._trim_header(
            header, min(int(chunk_size * cls.HEADER_BUDGET),
                        available - floor))
        budget = available - (len(header) + 1 if header else 0)
        if budget < floor:
            # The prefix alone has eaten the chunk. Keeping the body text is
            # the point of the exercise, so the header goes first.
            header, budget = "", available
        if budget <= 0:
            logger.warning(
                "Chunk prefix (%d chars) does not fit a %d-char chunk; "
                "body text will be minimal", reserve, chunk_size)
            budget = max(chunk_size // 4, 1)
        # Cap the overlap at half the body: clamping it to budget - 1 keeps
        # the loop finite but advances the window one character at a time.
        overlap = min(overlap, budget // 2)
        pieces: List[str] = []
        start = 0
        while start < len(body):
            piece = body[start : start + budget]
            pieces.append(f"{header}\n{piece}" if header else piece)
            nxt = start + budget - overlap
            if nxt <= start:
                break
            start = nxt
        return pieces

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

    # Canonical statement titles, matched against the block's text. The
    # heading field cannot serve this: _heading_of returns the first
    # substantial line, which on a statement page is the units note
    # ("(In millions, except number of shares...)") or a stray sentence.
    # Measured over the Apple 10-K, "income statement", "balance sheet" and
    # "cash flow" each matched 0 of 427 headings while the real titles sit in
    # the text of the block, so a section filter has to read the text.
    _SECTIONS = (
        ("income statement", r"consolidated statements? of operations"),
        ("comprehensive income",
         r"consolidated statements? of comprehensive income"),
        ("balance sheet", r"consolidated balance sheets?"),
        ("equity", r"consolidated statements? of shareholders.{0,3} equity"),
        ("cash flow", r"consolidated statements? of cash flows?"),
    )
    # Anchored to a whole line. Searching the block's text as one string also
    # matched every prose mention of a statement - "at their gross fair values
    # in the Consolidated Balance Sheets" in a revenue note, the index entry,
    # the auditor's opinion - which put the section label on five pages that
    # are not the statement.
    _SECTION_RX = tuple(
        (name, re.compile(rf"^\W*{pattern}\W*$", re.I | re.M))
        for name, pattern in _SECTIONS
    )

    # Not every statement page carries its title into the extracted table:
    # pdfplumber's region for Apple's balance sheet begins at the units note,
    # so the page holding "Total assets" has no title to match. These are the
    # line items that identify a statement by what it reports. Both must be
    # present, because either alone appears in the discussion of it too.
    # Matched as patterns, not substrings: clean_text rejoins words that
    # pdfplumber split across a tab, and it closes the gap without a space,
    # so the balance sheet's own total reads "Totalassets".
    _SECTION_SIGNATURES = tuple(
        (name, tuple(re.compile(term, re.I) for term in terms))
        for name, terms in (
            ("balance sheet", (r"total\s*assets", r"total\s*liabilities")),
            ("income statement",
             (r"total\s*net\s*sales", r"total\s*cost\s*of\s*sales")),
            ("cash flow",
             (r"operating\s*activities", r"investing\s*activities")),
        )
    )

    @classmethod
    def _section_of(cls, block: str) -> Optional[str]:
        """Name the financial statement a block belongs to, if it is one.

        Returns a stable slug ("balance sheet") rather than the title as
        printed, so a question can be matched against it without the caller
        having to reproduce the filing's exact capitalisation and wording.
        """
        lines = [re.sub(r"[\t ]+", " ", line).strip()
                 for line in block.split("\n")]
        flat = "\n".join(lines)
        for name, rx in cls._SECTION_RX:
            if rx.search(flat):
                return name
        for name, signature in cls._SECTION_SIGNATURES:
            if all(term.search(flat) for term in signature):
                return name
        return None

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
        table_chunk_size: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Chunk the document and carry per-chunk provenance alongside the text.

        Every chunk records the page, table, parser and nearest heading it came
        from, so retrieval can filter on them and the UI can tell the reader
        which page of the PDF an answer is grounded in.
        """
        if chunk_size is None:
            chunk_size = settings.CHUNK_SIZE
        # Tables are measured separately: the same 512 tokens is about 2,900
        # characters of prose and about 700 of financial rows, so one size
        # either overflows the tables or starves the prose.
        if table_chunk_size is None:
            table_chunk_size = chunk_size
        if overlap is None:
            # Hold the configured overlap ratio rather than the raw character
            # count: the chunk size is now measured per document, and 200
            # characters is a fifth of a table chunk but a twelfth of a prose
            # one, which is not the same amount of continuity.
            overlap = round(chunk_size * settings.CHUNK_OVERLAP
                            / max(settings.CHUNK_SIZE, 1))
        # compose_chunk() prepends provenance after the text is cut, so the
        # room it takes has to come out of the budget here or the finished
        # chunk is over the size it was sized against.
        #
        # The generated context line has to be reserved on the tabular shape,
        # which is the expensive one: there the line is appended alongside the
        # "Section:" label rather than replacing it, so both are present at
        # once. Reserving the worst case costs prose chunks a little body text
        # and keeps one number describing every chunk.
        probe = {"page_number": 9999, "heading": "x" * 120, "tabular": True}
        context = ("x" * settings.CONTEXT_MAX_OUTPUT_CHARS
                   if settings.CONTEXTUAL_CHUNKS else None)
        reserve = len(self.compose_chunk("", source_file, probe, context))

        out: List[Dict[str, Any]] = []
        for block in self._split_blocks(self.clean_text(text)):
            lines = block.split("\n")
            rest = "\n".join(lines[1:])          # everything after the marker

            if self._is_garbage(rest):
                continue

            meta = self._block_meta(block)
            meta["heading"] = self._heading_of(block)
            meta["section"] = self._section_of(block)

            # Repeating the leading lines on every chunk is what keeps a
            # table's title, units and column headers attached to its numeric
            # rows. That is only correct for real tables: extract_tables() also
            # returns plain paragraphs, and there the same trick duplicates
            # body text onto every chunk, filling the index with near-identical
            # neighbours that crowd each other out of the top-k.
            header, body = "", rest
            meta["tabular"] = self._is_tabular(rest)
            if meta["tabular"]:
                header = "\n".join(lines[: self.HEADER_LINES]).strip()
                body = "\n".join(lines[self.HEADER_LINES :])
                if not body.strip():   # table shorter than the header window
                    header, body = "", rest

            size = table_chunk_size if meta["tabular"] else chunk_size
            pieces = self._window(body, header, size,
                                  round(size * settings.CHUNK_OVERLAP
                                        / max(settings.CHUNK_SIZE, 1)),
                                  reserve=reserve)
            if not pieces:
                continue

            # The contextual prefix is composed by compose_chunk() rather than
            # here, so a generated context line can take the place of the
            # mechanical heading before the text is indexed.
            for piece in pieces:
                if piece.strip():
                    out.append({"text": piece, **meta})
        return out

    @staticmethod
    def compose_chunk(piece: str, source_file: Optional[str],
                      meta: Dict[str, Any],
                      context: Optional[str] = None) -> str:
        """Prepend provenance to a chunk before it is embedded and indexed.

        A chunk separated from its document loses the only clues about what it
        describes, so stating the source and page up front costs a few tokens
        and lets the model cite them.

        Which label follows depends on the block. For a table, the first line
        really is the table's title and is worth keeping. For prose it is just
        the opening words of a paragraph, so a generated context line replaces
        it outright rather than sitting alongside it.
        """
        bits = []
        if source_file:
            bits.append(f"Document: {source_file}")
        if meta.get("page_number") is not None:
            bits.append(f"Page {meta['page_number']}")
        if context and not meta.get("tabular"):
            bits.append(f"Context: {context}")
        else:
            if meta.get("heading"):
                bits.append(f"Section: {meta['heading']}")
            if context:
                bits.append(f"Context: {context}")
        prefix = f"[{' | '.join(bits)}]\n" if bits else ""
        return prefix + piece

    @classmethod
    def _density_samples(cls, text: str) -> tuple:
        """Prose and table text from this document, sampled separately.

        One ratio per document is wrong in a filing: measured against
        EmbeddingGemma, narrative runs 5.77 chars/token and financial rows
        1.40 - a 4.1x spread INSIDE one 10-K. Sizing everything from the
        blended figure cuts prose chunks to a third of what they could safely
        hold, and it is the prose that most needs the room.
        """
        prose, tables = [], []
        for block in cls._split_blocks(cls.clean_text(text)):
            body = "\n".join(block.split("\n")[1:])
            if not body.strip() or cls._is_garbage(body):
                continue
            (tables if cls._is_tabular(body) else prose).append(body)
        cap = 6000
        return ("\n".join(prose)[:cap], "\n".join(tables)[:cap])

    async def create_document_embeddings(
        self, file_id: int, text: str, db: AsyncSession,
        progress_cb=None,
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

        # Size the chunk in tokens against the embedding model's own
        # tokenizer, then convert to characters for the windowing. A fixed
        # character size means something different for a table than for a
        # paragraph, and only one of the two can be right.
        prose_sample, table_sample = self._density_samples(text)
        sizing = await asyncio.to_thread(
            windowing.chunk_chars, settings.LLM_BASE_URL,
            self.embedding_model, prose_sample or text,
            settings.EMBEDDING_CHUNK_TOKENS,
        )
        table_sizing = sizing
        if table_sample:
            table_sizing = await asyncio.to_thread(
                windowing.chunk_chars, settings.LLM_BASE_URL,
                self.embedding_model, table_sample,
                settings.EMBEDDING_CHUNK_TOKENS,
            )
        logger.info(
            "Chunking prose at %d chars (%.2f chars/token) and tables at "
            "%d chars (%.2f chars/token), %d tokens of a %d-token window",
            sizing.chars, sizing.ratio, table_sizing.chars,
            table_sizing.ratio, sizing.tokens, sizing.context_tokens,
        )

        # Chunk with provenance so each row records its page / table / heading.
        pieces = await self.chunk_document(
            text, chunk_size=sizing.chars, source_file=source_file,
            table_chunk_size=table_sizing.chars)

        # Optional contextual retrieval pass. Generation is minutes of local
        # inference, so it runs only when explicitly enabled, and a failure
        # here degrades findability rather than failing the upload.
        contexts: Dict[str, str] = {}
        if settings.CONTEXTUAL_CHUNKS:
            async def _ctx_progress(done: int, total: int) -> None:
                if progress_cb:
                    await progress_cb("contextualizing", done, total)
            try:
                contexts = await ContextService().contextualize(
                    [p["text"] for p in pieces],
                    source_file or f"file {file_id}", db,
                    progress_cb=_ctx_progress,
                )
            except Exception as err:
                logger.warning("Contextualization skipped: %s", err)

        chunks = [
            self.compose_chunk(p["text"], source_file, p,
                               contexts.get(content_hash(p["text"])))
            for p in pieces
        ]
        # A single ratio per document, applied to a document whose own
        # density spans 3.2x, is the one way the sizing above can be wrong in
        # the unsafe direction: calibrate on prose at 4.9 chars/token and a
        # dense table chunk of the same character length is three times the
        # tokens. Reading the longest chunk at the pessimistic ratio says
        # whether even that case still fits, at no cost. Warn rather than
        # truncate - a silently shortened chunk is a vector that misrepresents
        # its own text, which is worse than an oversized one the log names.
        if chunks:
            widest = max(len(c) for c in chunks)
            ceiling = sizing.context_tokens * windowing.FALLBACK_CHARS_PER_TOKEN
            if widest > ceiling:
                logger.warning(
                    "Longest chunk is %d chars; read at the pessimistic %.1f "
                    "chars/token that exceeds the %d-token window. Lower "
                    "EMBEDDING_CHUNK_TOKENS.",
                    widest, windowing.FALLBACK_CHARS_PER_TOKEN,
                    sizing.context_tokens)

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
            if progress_cb:
                await progress_cb("embedding",
                                  min(start + batch_size, len(chunks)),
                                  len(chunks))

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
                    "section": pieces[i].get("section"),
                    "tabular": pieces[i].get("tabular"),
                    "context": contexts.get(content_hash(pieces[i]["text"])),
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
        keyword_hits = await self.search_documents_bm25(
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

    async def search_documents_bm25(
        self,
        query: str,
        organization_id: int,
        file_ids: Optional[List[int]] = None,
        limit: int = 10,
        db: Optional[AsyncSession] = None,
    ) -> List[Dict[str, Any]]:
        """Lexical search over chunks, ranked by Okapi BM25.

        Replaces the ts_rank implementation kept commented out below. See
        app/services/bm25.py for why: ts_rank has no IDF, websearch_to_tsquery
        requires every term to be present, and the english configuration
        splits figures on their thousands separators.
        """
        if db is None:
            return []
        try:
            index = await bm25.get_index(db)
            positions = index.search(query, organization_id, file_ids, limit)
        except Exception as err:  # lexical search must never kill retrieval
            logger.warning("BM25 search failed: %s", err)
            return []

        results: List[Dict[str, Any]] = []
        for rank, doc in enumerate(positions):
            chunk, file_id, _org, filename, chunk_index, meta = index.rows[doc]
            results.append({
                "content_chunk": chunk,
                "file_id": file_id,
                "filename": filename,
                "chunk_index": chunk_index,
                "chunk_metadata": meta,
                "similarity_score": 0.0,
                "keyword_rank": float(len(positions) - rank),
            })
        return results

    # Superseded by search_documents_bm25. Retained because the switch was made
    # on measured behaviour rather than preference, and this is what to restore
    # if the BM25 index ever has to come out.
    #
    # async def search_documents_keyword(
    #     self,
    #     query: str,
    #     organization_id: int,
    #     file_ids: Optional[List[int]] = None,
    #     limit: int = 10,
    #     db: Optional[AsyncSession] = None,
    # ) -> List[Dict[str, Any]]:
    #     """Full-text (keyword) search over chunks, ranked by ts_rank."""
    #     sql = """
    #     SELECT
    #         de.content_chunk,
    #         de.file_id,
    #         uf.original_filename,
    #         de.chunk_index,
    #         de.chunk_metadata,
    #         ts_rank(to_tsvector('english', de.content_chunk),
    #                 websearch_to_tsquery('english', :q)) AS rank
    #     FROM document_embeddings de
    #     JOIN uploaded_files uf ON de.file_id = uf.id
    #     WHERE uf.organization_id = :org_id
    #       AND to_tsvector('english', de.content_chunk)
    #           @@ websearch_to_tsquery('english', :q)
    #     """
    #     params: Dict[str, Any] = {"q": query, "org_id": organization_id,
    #                               "limit": limit}
    #     if file_ids:
    #         sql += " AND de.file_id = ANY(:file_ids)"
    #         params["file_ids"] = list(file_ids)
    #     sql += " ORDER BY rank DESC LIMIT :limit"
    #
    #     try:
    #         result = await db.execute(sql_text(sql), params)
    #         rows = result.fetchall()
    #     except Exception as err:  # a malformed query should not kill retrieval
    #         logger.warning("Keyword search failed: %s", err)
    #         return []
    #
    #     return [{
    #         "content_chunk": row[0],
    #         "file_id": row[1],
    #         "filename": row[2],
    #         "chunk_index": row[3],
    #         "chunk_metadata": row[4],
    #         "similarity_score": 0.0,
    #         "keyword_rank": float(row[5]),
    #     } for row in rows]

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

        # The NOT ... = 'NaN' guard drops degenerate (zero) stored vectors.
        # Cosine distance to a zero vector is NaN, and Postgres orders NaN above
        # every real number, so without this they pass the threshold and rank
        # first. Belt-and-braces: ingest no longer writes them, but any row
        # written before that fix must not be able to poison a search.
        search_query += """
        AND NOT ((de.embedding <=> CAST(:vec AS vector))::text = 'NaN')
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
        AND NOT ((ke.embedding <=> CAST(:vec AS vector))::text = 'NaN')
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
            response = await asyncio.to_thread(
                self.client.embeddings.create,
                model=self.embedding_model,
                input=texts,
            )
            return [data.embedding for data in response.data]
        except Exception as err:
            # See generate_embedding: zero vectors poison retrieval rather than
            # degrade it, so a failed batch must abort the ingest.
            logger.error("Error in batch embedding generation: %s", err)
            raise RuntimeError(f"Batch embedding generation failed: {err}") from err

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
        WHERE NOT ((ke.embedding <=> CAST(:vec AS vector))::text = 'NaN')
        AND 1 - (ke.embedding <=> CAST(:vec AS vector)) >= :threshold
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
