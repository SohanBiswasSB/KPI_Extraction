"""Database models and Pydantic schemas for uploaded files and their extractions."""
import enum
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import Column, Integer, String, DateTime, Enum, Text, ForeignKey, JSON, Numeric
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from pydantic import BaseModel

from app.core.database import Base


class FileStatus(str, enum.Enum):
    """Lifecycle states of an uploaded file."""

    UPLOADED = "uploaded"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class UploadedFile(Base):
    """A document uploaded for table/KPI extraction."""

    __tablename__ = "uploaded_files"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False, index=True)
    original_filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size = Column(Integer, nullable=False)
    file_type = Column(String(100), nullable=False)
    status = Column(Enum(FileStatus), default=FileStatus.UPLOADED)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    uploaded_by = Column(Integer, ForeignKey("users.id"))
    processing_metadata = Column(JSON)  # Store processing results and metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    organization = relationship("Organization", back_populates="uploaded_files")
    uploaded_by_user = relationship("User", back_populates="uploaded_files")
    extracted_kpis = relationship(
        "ExtractedKPI", back_populates="file", cascade="all, delete-orphan"
    )
    extracted_tables = relationship(
        "ExtractedTable", back_populates="file", cascade="all, delete-orphan"
    )
    embeddings = relationship(
        "DocumentEmbedding", back_populates="file", cascade="all, delete-orphan"
    )


class ExtractedKPI(Base):
    """A KPI value identified within a document."""

    __tablename__ = "extracted_kpis"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, ForeignKey("uploaded_files.id"), nullable=False)
    kpi_name = Column(String(255), nullable=False, index=True)
    kpi_value = Column(Numeric(15, 2))
    kpi_unit = Column(String(50))
    confidence_score = Column(Numeric(3, 2))  # 0.00 to 1.00
    extraction_method = Column(String(100))  # "ai", "regex", "manual"
    raw_text = Column(Text)  # Original text where KPI was found
    context = Column(Text)  # Surrounding context
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    file = relationship("UploadedFile", back_populates="extracted_kpis")


class ExtractedTable(Base):
    """A structured table extracted from a document (rows/cols preserved)."""

    __tablename__ = "extracted_tables"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, ForeignKey("uploaded_files.id"), nullable=False)
    page = Column(Integer, nullable=False, default=1)        # 1-based page/sheet
    table_index = Column(Integer, nullable=False, default=0)  # index within the page
    source = Column(String(20))                               # pdfplumber|ocr|excel|csv|docx
    sheet_name = Column(String(255))
    caption = Column(Text)
    n_rows = Column(Integer, default=0)
    n_cols = Column(Integer, default=0)
    confidence = Column(Numeric(3, 2), default=1.0)
    rows = Column(JSON, nullable=False)                       # full grid incl. header
    bbox = Column(JSON)                                       # [x0,y0,x1,y1] when known
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    file = relationship("UploadedFile", back_populates="extracted_tables")


class DocumentEmbedding(Base):
    """A text chunk and its vector embedding for semantic search."""

    __tablename__ = "document_embeddings"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, ForeignKey("uploaded_files.id"), nullable=False)
    content_chunk = Column(Text, nullable=False)
    embedding = Column("embedding", type_=None)  # Will be handled by pgvector
    chunk_index = Column(Integer)
    chunk_metadata = Column(JSON)  # Store additional metadata about the chunk
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    file = relationship("UploadedFile", back_populates="embeddings")


# Pydantic models for API
class FileBase(BaseModel):
    """Shared file fields."""

    original_filename: str
    file_type: str
    file_size: int


class FileCreate(FileBase):
    """Payload for registering a file."""

    organization_id: int


class FileUpdate(BaseModel):
    """Mutable file fields."""

    status: Optional[FileStatus] = None
    processing_metadata: Optional[Dict[str, Any]] = None


class FileResponse(FileBase):
    """File record returned by the API."""

    id: int
    filename: str
    file_path: str
    status: FileStatus
    organization_id: int
    uploaded_by: Optional[int] = None
    processing_metadata: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        """Enable ORM attribute population."""

        from_attributes = True


class ExtractedKPIBase(BaseModel):
    """Shared KPI fields."""

    kpi_name: str
    kpi_value: Optional[float] = None
    kpi_unit: Optional[str] = None
    confidence_score: Optional[float] = None
    extraction_method: Optional[str] = None
    raw_text: Optional[str] = None
    context: Optional[str] = None


class ExtractedKPICreate(ExtractedKPIBase):
    """Payload for creating a KPI."""

    file_id: int


class ExtractedKPIResponse(ExtractedKPIBase):
    """KPI record returned by the API."""

    id: int
    file_id: int
    created_at: datetime

    class Config:
        """Enable ORM attribute population."""

        from_attributes = True


class ExtractedTableResponse(BaseModel):
    """Structured table record returned by the API."""

    id: int
    file_id: int
    page: int
    table_index: int
    source: Optional[str] = None
    sheet_name: Optional[str] = None
    caption: Optional[str] = None
    n_rows: int
    n_cols: int
    confidence: Optional[float] = None
    rows: List[List[Any]]
    bbox: Optional[List[float]] = None
    created_at: datetime

    class Config:
        """Enable ORM attribute population."""

        from_attributes = True


class TablePreview(BaseModel):
    """A single table in a stateless preview response."""

    page: int
    index: int
    source: Optional[str] = None
    sheet_name: Optional[str] = None
    caption: Optional[str] = None
    confidence: Optional[float] = None
    n_rows: int
    n_cols: int
    rows: List[List[Any]]


class TablePreviewResponse(BaseModel):
    """Result of previewing a file's tables off disk."""

    tables_found: int
    tables: List[TablePreview] = []


class FileProcessingResult(BaseModel):
    """Summary of a completed processing run."""

    file_id: int
    status: FileStatus
    extracted_kpis: List[ExtractedKPIResponse] = []
    processing_metadata: Dict[str, Any] = {}
    error_message: Optional[str] = None


class FileUploadResponse(BaseModel):
    """Response returned after an upload."""

    file: FileResponse
    upload_url: Optional[str] = None
    message: str


class DocumentSearchQuery(BaseModel):
    """Semantic document-search request."""

    query: str
    file_ids: Optional[List[int]] = None
    organization_id: int
    limit: int = 10
    similarity_threshold: float = 0.7


class DocumentSearchResult(BaseModel):
    """A single semantic-search hit."""

    content_chunk: str
    file_id: int
    filename: str
    similarity_score: float
    chunk_metadata: Dict[str, Any] = {}
