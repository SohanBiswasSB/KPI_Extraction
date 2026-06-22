from pydantic_settings import BaseSettings
from typing import List, Optional
import os


class Settings(BaseSettings):
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
    
    # LLM settings — local-first via an OpenAI-compatible server (Ollama/vLLM/LM Studio).
    # No API key required for local models; LLM_API_KEY is any non-empty placeholder.
    # Point LLM_BASE_URL at a hosted OpenAI endpoint instead to use cloud models.
    LLM_BASE_URL: str = "http://localhost:11434/v1"   # Ollama default
    LLM_API_KEY: Optional[str] = None                  # falls back to "ollama" if unset
    LLM_MODEL: str = "qwen2.5:7b-instruct"             # text → KPI structuring
    LLM_VISION_MODEL: str = "qwen2.5vl:7b"             # vision → tables from page images
    LLM_EMBEDDING_MODEL: str = "nomic-embed-text"      # local embeddings (768-dim)

    # Back-compat: legacy code/env may still reference these.
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "qwen2.5:7b-instruct"
    OPENAI_EMBEDDING_MODEL: str = "nomic-embed-text"

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
    VECTOR_DIMENSION: int = 768  # nomic-embed-text dimension (must match init.sql + LLM_EMBEDDING_MODEL)
    
    # Pagination settings
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100
    
    # AI processing settings
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    MAX_TOKENS: int = 4000
    
    class Config:
        env_file = ".env"
        case_sensitive = True


# Create settings instance
settings = Settings()

# Ensure upload directory exists
os.makedirs(settings.UPLOAD_DIR, exist_ok=True) 