"""Application settings loaded from environment variables / .env."""
import os
from typing import List, Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Typed application configuration with sensible local-first defaults."""

    # Application settings
    APP_NAME: str = "KPI Extraction Platform"
    VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Database settings
    DATABASE_URL: str = "postgresql://kpi_user:kpi_password@localhost:5432/kpi_platform"

    # Security settings
    SECRET_KEY: str = "your-secret-key-change-in-production"
    JWT_SECRET: str = "your-jwt-secret-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # LLM settings - local-first via an OpenAI-compatible server (LM Studio/Ollama/vLLM).
    # No API key required for local models; LLM_API_KEY is any non-empty placeholder.
    # Point LLM_BASE_URL at a hosted OpenAI endpoint instead to use cloud models.
    #
    # --- Ollama defaults (disabled; not in use) -------------------------------
    # LLM_BASE_URL: str = "http://localhost:11434/v1"  # Ollama default
    # LLM_MODEL: str = "qwen2.5:7b-instruct"           # text -> KPI structuring
    # LLM_VISION_MODEL: str = "qwen2.5vl:7b"           # vision -> tables from page images
    # LLM_EMBEDDING_MODEL: str = "nomic-embed-text"    # local embeddings (768-dim)
    # --------------------------------------------------------------------------
    #
    # Active: LM Studio's OpenAI-compatible server (default port 1234).
    LLM_BASE_URL: str = "http://localhost:1234/v1"
    LLM_API_KEY: Optional[str] = None                  # falls back to a placeholder if unset
    LLM_MODEL: str = "qwen2.5-7b-instruct-1m"

    # Vision path (scanned pages -> tables). Only used when ENABLE_VLM is true.
    # NOTE: qwen2.5-7b-instruct is TEXT-ONLY, so this points at a genuinely
    # multimodal model. On a 24GB machine the two cannot be resident together
    # (15.6GB + 4.7GB), so enabling VLM means swapping LLM_MODEL as well.
    LLM_VISION_MODEL: str = "google/gemma-4-26b-a4b-qat"

    # EmbeddingGemma-300M: 768-dim, matches vector(768) in init.sql. Tiny (229MB),
    # so it stays resident alongside the 4.7GB chat model.
    LLM_EMBEDDING_MODEL: str = "text-embedding-embeddinggemma-300m-qat"

    # Reasoning models (Qwen3, Gemma-4) spend their whole token budget "thinking"
    # and often return an empty message; prefilling an already-closed think block
    # makes them answer immediately (measured 59s/empty -> 7s/correct on
    # bonsai-27b). qwen2.5-7b-instruct is NOT a reasoning model, so this is
    # disabled - set it to "<think>\n\n</think>\n\n" if you switch back.
    LLM_THINK_PREFILL: str = ""

    # Back-compat: legacy code/env may still reference these.
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "google/gemma-4-26b-a4b-qat"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-embeddinggemma-300m-qat"

    # File upload settings
    UPLOAD_DIR: str = "uploads"
    MAX_FILE_SIZE: int = 50 * 1024 * 1024  # 50MB
    ALLOWED_FILE_TYPES: List[str] = [
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # .xlsx
        "application/vnd.ms-excel",                                            # .xls
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
        "text/plain",
        "text/csv",
        "image/png",
        "image/jpeg",
        "image/tiff",
    ]

    # Table-extraction / OCR settings
    ENABLE_OCR: bool = True          # fall back to OCR for scanned PDFs / images
    OCR_DPI: int = 200               # render DPI for the OCR/VLM fallback
    OCR_LANG: str = "eng"            # Tesseract language code(s), e.g. "eng+hin"

    # Vision-LLM fallback for scanned pages (Qwen2.5-VL via LLM_BASE_URL).
    # When enabled, a page with no native tables is sent as an image to the VLM
    # *before* plain OCR. This makes scanned-doc extraction depend on the LLM;
    # leave it off to keep extraction fully deterministic/offline.
    ENABLE_VLM: bool = False
    VLM_MAX_PAGES: int = 10          # cap pages sent to the VLM per document

    # CORS settings
    ALLOWED_HOSTS: List[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001"
    ]

    # Redis settings
    REDIS_URL: str = "redis://localhost:6379"

    # KPI extraction scans the document in windows rather than only the first
    # 4000 chars (which on a 10-K is just the SEC cover page). Window size must
    # leave room for the reply inside the model's loaded context.
    # Hard upper bound on a single extraction window. Normally it does not
    # bind: the real size is measured per document against the loaded model
    # (see services/windowing.py), which is both safer on table-dense text and
    # far larger on prose. Kept as an escape hatch for forcing small windows.
    KPI_WINDOW_CHARS: int = 120000
    KPI_MAX_WINDOWS: int = 40
    # Windows are sent concurrently; this must not exceed the inference
    # server's parallel slot count (LM Studio shows it as "Parallel" on the
    # loaded model, and logs it as n_slots).
    #
    # Sizing note: with the classic per-slot KV cache, context x parallel is
    # what has to fit in RAM - ctx 32768 x 6 slots needs ~22GB and simply fails
    # to load on 24GB. With LM Studio's "Unified KV Cache" enabled (the server
    # logs kv_unified = 'true') the slots draw from one shared pool instead, so
    # raising concurrency no longer multiplies the KV footprint. The current
    # setup runs 6 slots at ctx 16384 with unified KV on.
    KPI_CONCURRENCY: int = 4

    # --- Contextual retrieval -------------------------------------------
    # Generate a one-sentence description of each chunk and prepend it before
    # embedding and lexical indexing, so a chunk carries terms that situate it
    # in the document rather than only the words it happens to contain.
    #
    # Off by default: this turns a ~15 second embedding stage into minutes,
    # which should be a deliberate choice per environment rather than a silent
    # regression in upload time.
    CONTEXTUAL_CHUNKS: bool = False
    # A small instruct model is enough to situate an excerpt and leaves the
    # 7B free. Blank falls back to LLM_MODEL. Note this is the plain instruct
    # build, not the VL (vision) or Coder variant of the same size.
    CONTEXT_MODEL: str = "qwen2.5-3b-instruct"
    # Measured on an M4 Pro against the loaded 7B: 12 chunks took 14.2s at
    # concurrency 1, 6.2s at 2, and 6.9s at 4. The GPU saturates at two
    # in-flight requests, so raising this past 2 buys nothing on this hardware
    # even though LM Studio exposes 6 slots.
    CONTEXT_CONCURRENCY: int = 4
    CONTEXT_MAX_CHARS: int = 1500   # of the chunk shown to the context model

    # Vector database settings
    # Must match LLM_EMBEDDING_MODEL and the vector() dimension in init.sql.
    VECTOR_DIMENSION: int = 768  # nomic-embed-text dimension

    # Pagination settings
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100

    # AI processing settings
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    MAX_TOKENS: int = 4000

    class Config:
        """Pydantic settings configuration."""

        env_file = ".env"
        case_sensitive = True


# Create settings instance
settings = Settings()

# Ensure upload directory exists
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
