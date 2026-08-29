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

    # LLM settings — local-first via an OpenAI-compatible server (LM Studio/Ollama/vLLM).
    # No API key required for local models; LLM_API_KEY is any non-empty placeholder.
    # Point LLM_BASE_URL at a hosted OpenAI endpoint instead to use cloud models.
    #
    # --- Ollama defaults (disabled; not in use) -------------------------------
    # LLM_BASE_URL: str = "http://localhost:11434/v1"  # Ollama default
    # LLM_MODEL: str = "qwen2.5:7b-instruct"           # text → KPI structuring
    # LLM_VISION_MODEL: str = "qwen2.5vl:7b"           # vision → tables from page images
    # LLM_EMBEDDING_MODEL: str = "nomic-embed-text"    # local embeddings (768-dim)
    # --------------------------------------------------------------------------
    #
    # Active: LM Studio's OpenAI-compatible server (default port 1234).
    LLM_BASE_URL: str = "http://localhost:1234/v1"
    LLM_API_KEY: Optional[str] = None                  # falls back to a placeholder if unset
    LLM_MODEL: str = "google/gemma-4-26b-a4b-qat"
    # Same multimodal model serves the vision path; only used when ENABLE_VLM is true.
    # NOTE: gemma-4 is a *reasoning* model — it spends 1.5-2k tokens thinking before
    # answering, so every max_tokens in ai_service.py must stay well above that.
    LLM_VISION_MODEL: str = "google/gemma-4-26b-a4b-qat"
    # EmbeddingGemma-300M: 768-dim, matches vector(768) in init.sql. Tiny (229MB),
    # so it can stay resident alongside the 15.6GB chat model on a 24GB machine.
    LLM_EMBEDDING_MODEL: str = "text-embedding-embeddinggemma-300m-qat"

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
