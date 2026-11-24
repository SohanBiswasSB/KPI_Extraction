"""Sizing the text windows a document is fed to the model in.

One character-to-token constant cannot describe a filing. Measured against a
loaded Qwen2.5, cleaned financial table rows run 1.54 chars/token while
narrative prose runs 4.93 - a 3.2x spread inside a single document. A fixed
ratio therefore overflows the context on table-dense windows and wastes about
two thirds of it on prose ones, and the number of windows is what drives the
slowest stage in the pipeline. These helpers measure the ratio per document
instead of assuming one.
"""

import json
import logging
import urllib.request
from typing import List, NamedTuple, Optional

import openai

from app.core.config import settings

logger = logging.getLogger(__name__)

PROMPT_OVERHEAD_TOKENS = 800
WINDOW_SAFETY = 0.85
# Used only when calibration cannot run. Deliberately pessimistic - it has to
# hold for the densest content in the corpus.
FALLBACK_CHARS_PER_TOKEN = 1.5


def measure_chars_per_token(base_url: str, model: str, text: str) -> Optional[float]:
    """Measure this document's real character-to-token ratio.

    A single constant cannot describe a filing. Measured against the loaded
    model, cleaned financial table rows run 1.54 chars/token while narrative
    prose runs 4.93 - a 3.2x spread inside one document. A fixed 1.8 therefore
    overflows on table-dense windows and wastes about two thirds of the context
    on prose ones, and window count drives the slowest stage in the pipeline.

    Sampling the head, middle and tail keeps the estimate representative of the
    document rather than of whichever section happens to come first. Costs one
    request with max_tokens=1.
    """
    if not text:
        return None
    span = 1500
    parts = [text[:span]]
    if len(text) > span * 3:
        middle = len(text) // 2
        parts.append(text[middle:middle + span])
        parts.append(text[-span:])
    sample = "\n".join(parts)
    try:
        client = openai.OpenAI(
            base_url=base_url,
            api_key=settings.LLM_API_KEY or settings.OPENAI_API_KEY or "local",
        )
        # The chat template adds a fixed number of tokens; measure it once and
        # subtract, so the ratio describes the sample and not the wrapper.
        baseline = client.chat.completions.create(
            model=model, max_tokens=1,
            messages=[{"role": "user", "content": ""}],
        ).usage.prompt_tokens
        measured = client.chat.completions.create(
            model=model, max_tokens=1,
            messages=[{"role": "user", "content": sample}],
        ).usage.prompt_tokens
    except Exception as err:
        logger.warning("Token calibration failed, using fallback ratio: %s", err)
        return None

    tokens = measured - baseline
    if tokens <= 0:
        return None
    return len(sample) / tokens


def _loaded_context(base_url: str, model: str) -> Optional[int]:
    """The context length LM Studio currently has a model loaded at.

    Returns None when the server is not LM Studio, is unreachable, or has the
    model unloaded - every caller then falls back to a configured default.
    """
    try:
        endpoint = base_url.rstrip("/")
        if endpoint.endswith("/v1"):
            endpoint = endpoint[:-3]
        with urllib.request.urlopen(endpoint + "/api/v0/models", timeout=3) as resp:
            data = json.loads(resp.read().decode())
    except Exception:  # not LM Studio, or unreachable - caller falls back
        return None

    for entry in data.get("data", []):
        if entry.get("id") == model and entry.get("state") != "not-loaded":
            ctx = entry.get("loaded_context_length")
            return int(ctx) if ctx else None
    return None


# Appended to a sample to test whether the server kept the whole input. It has
# to be text the document cannot itself contain.
_TAIL_MARKER = " ZZZQQQ distinctive tail marker 987654321"


def measure_embedding_chars_per_token(base_url: str, model: str,
                                      text: str) -> Optional[float]:
    """Measure how many characters of THIS text fit the embedding window.

    Not read from the API, because it is not reported: LM Studio answers every
    embeddings request with ``usage.prompt_tokens: 0``, on both the OpenAI and
    the native route, so the count that works for the chat model does not
    exist here. Worse, oversized input is not rejected - measured against
    EmbeddingGemma, a 53,000-character input returns a perfectly ordinary
    vector of its first ~11,800 characters, and nothing in the response says
    so.

    That silent truncation is what makes the measurement possible. Appending a
    marker to an input that was already truncated cannot change the vector,
    because the marker is discarded with everything else past the limit. So
    the limit is found by binary search on "does adding a marker still move
    the vector", which measures the quantity that actually matters - how much
    of this document's text survives - without needing a tokenizer at all.

    Returns characters per token, so callers can keep sizing in tokens. Costs
    about sixteen embedding calls, once per document.
    """
    if not text:
        return None
    context = _loaded_context(base_url, model) or settings.EMBEDDING_CONTEXT_TOKENS
    try:
        client = openai.OpenAI(
            base_url=base_url,
            api_key=settings.LLM_API_KEY or settings.OPENAI_API_KEY or "local",
        )

        def vector(sample: str) -> tuple:
            reply = client.embeddings.create(model=model, input=sample)
            return tuple(reply.data[0].embedding)

        def survives(sample: str) -> bool:
            """True when the whole sample was embedded, not just a prefix."""
            return vector(sample) != vector(sample + _TAIL_MARKER)

        # Bounds in chars/token. One is below any real tokenizer, eight above
        # any plausible one, so the true limit is bracketed on the first call.
        low, high = context, context * 8
        probe = (text * (1 + high // max(len(text), 1)))[:high]
        if survives(probe):
            return high / context      # nothing truncates; the text is short
        while low < high - context // 8:
            middle = (low + high) // 2
            if survives(probe[:middle]):
                low = middle
            else:
                high = middle
    except Exception as err:  # pylint: disable=broad-exception-caught
        logger.warning("Embedding calibration failed: %s", err)
        return None
    return low / context


class ChunkSizing(NamedTuple):
    """How a document's chunks were sized, and against what.

    ``context_tokens`` is the model's window; ``tokens`` is the target a chunk
    was cut to, which is deliberately well under it. Callers need both: the
    target to size with, the window to check the result against.
    """

    chars: int
    tokens: int
    ratio: float
    context_tokens: int


def chunk_chars(base_url: str, model: str, text: str,
                target_tokens: int) -> ChunkSizing:
    """Chunk size in characters, sized from the embedding model's real limits.

    Returns a :class:`ChunkSizing` for a chunk of ``target_tokens``, clamped
    to what the model is actually loaded to accept.

    A character count cannot on its own say whether a chunk fits, nor say the
    same thing twice: measured on a 10-K, dense financial rows run about 1.5
    chars/token against roughly 4.9 for narrative prose, so a single character
    size is simultaneously unsafe for the tables and wasteful on the prose.
    Sizing in tokens and converting through this document's measured ratio
    makes one number mean one thing for both, and self-corrects when LM Studio
    reloads the model at a different context.

    What a server does with input past the window is its own choice - some
    reject it, some embed the prefix and drop the rest - and neither outcome
    is one the pipeline can distinguish from a good vector. WINDOW_SAFETY
    keeps the measured ratio's error away from that edge rather than relying
    on which behaviour this server happens to have.
    """
    ctx = _loaded_context(base_url, model) or settings.EMBEDDING_CONTEXT_TOKENS
    tokens = min(target_tokens, int(ctx * WINDOW_SAFETY))
    ratio = measure_embedding_chars_per_token(base_url, model, text)
    if ratio is None:
        ratio = FALLBACK_CHARS_PER_TOKEN
    return ChunkSizing(int(tokens * ratio), tokens, ratio, ctx)


def detect_context_tokens(base_url: str, model: str, reply_tokens: int,
                          concurrency: int = 1) -> Optional[int]:
    """Ask the local server how many prompt tokens the model can actually take.

    LM Studio silently re-loads a model at its default context (often 8192)
    after a JIT restart, so a hardcoded window size can start overflowing
    mid-run. Sizing from the live value makes that self-correcting.
    Returns a token budget, or None if the server does not report one.
    """
    ctx = _loaded_context(base_url, model)
    if ctx is None:
        return None
    # Convert the remaining token budget into characters.
    # 3 chars/token holds for prose but NOT for financial tables:
    # dense digits, commas and tabs measured ~2.05 chars/token on a
    # 10-K, which overflowed every window. 1.8 leaves real headroom.
    # PROMPT_OVERHEAD covers the instruction block wrapped around each
    # window; without it the reservation is short by ~600 tokens.
    # Divide first: the whole context, reply included, is shared by
    # every request in flight.
    share = ctx // max(concurrency, 1)
    return max(share - reply_tokens - PROMPT_OVERHEAD_TOKENS, 512)


def window_chars(base_url: str, model: str, reply_tokens: int,
                  text: str, concurrency: int = 1) -> tuple:
    """Window size in characters, sized from measured tokens for this document.

    Returns ``(chars, tokens, ratio)`` where chars is None if the server does
    not report a context length and the caller should keep its configured
    default.

    The context is SHARED across in-flight requests, not allocated per slot.
    Measured against LM Studio with a 16384 context and unified KV cache, an
    11,891-token prompt succeeds alone and fails with "Context size has been
    exceeded" as soon as a second request runs beside it. So concurrency does
    not buy throughput for free - it divides the budget every request gets,
    and a window sized for the whole context will fail the moment anything
    runs next to it.
    """
    tokens = detect_context_tokens(base_url, model, reply_tokens,
                                   concurrency=concurrency)
    if tokens is None:
        return (None, None, None)
    ratio = measure_chars_per_token(base_url, model, text)
    if ratio is None:
        ratio = FALLBACK_CHARS_PER_TOKEN
    return (int(tokens * ratio * WINDOW_SAFETY), tokens, ratio)


def split_windows(text: str, size: int, max_windows: int) -> List[str]:
    """Cut the document into model-sized windows, preferring table boundaries."""
    if not text:
        return []
    blocks = text.split("\n[page ")
    blocks = [blocks[0]] + [f"[page {b}" for b in blocks[1:]]

    windows: List[str] = []
    current = ""
    for block in blocks:
        if current and len(current) + len(block) > size:
            windows.append(current)
            current = block
        else:
            current = f"{current}\n{block}" if current else block
        # A single table larger than one window is split on raw length.
        while len(current) > size:
            windows.append(current[:size])
            current = current[size:]
    if current.strip():
        windows.append(current)
    return windows[:max_windows]
