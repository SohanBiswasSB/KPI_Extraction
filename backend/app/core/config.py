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
    
    # OpenAI settings
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-ada-002"
    
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
    OCR_DPI: int = 200               # render DPI for the OCR fallback
    OCR_LANG: str = "eng"            # Tesseract language code(s), e.g. "eng+hin"
    
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
    VECTOR_DIMENSION: int = 1536  # OpenAI embedding dimension
    
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