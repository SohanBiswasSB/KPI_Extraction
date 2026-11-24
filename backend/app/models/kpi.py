"""Database models and Pydantic schemas for KPIs, their history and embeddings."""
import enum
from datetime import datetime
from typing import Optional, List

from sqlalchemy import Column, Integer, String, DateTime, Enum, Text, Numeric, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from pydantic import BaseModel

from pgvector.sqlalchemy import Vector

from app.core.config import settings
from app.core.database import Base


class KPICategory(str, enum.Enum):
    """Classification buckets for a KPI."""

    FINANCIAL = "financial"
    OPERATIONAL = "operational"
    CUSTOMER = "customer"
    EMPLOYEE = "employee"
    MARKETING = "marketing"
    OTHER = "other"


class KPI(Base):
    """A key performance indicator tracked by an organization."""

    __tablename__ = "kpis"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text)
    category = Column(
        Enum(KPICategory, name="kpi_category",
             values_callable=lambda e: [m.value for m in e]),
        default=KPICategory.OTHER,
    )
    unit = Column(String(50))
    target_value = Column(Numeric(15, 2))
    current_value = Column(Numeric(15, 2))
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    dashboard_id = Column(Integer, ForeignKey("dashboards.id"))
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    organization = relationship("Organization", back_populates="kpis")
    dashboard = relationship("Dashboard", back_populates="kpis")
    created_by_user = relationship("User", back_populates="kpis")
    history = relationship("KPIHistory", back_populates="kpi", cascade="all, delete-orphan")
    embeddings = relationship("KPIEmbedding", back_populates="kpi", cascade="all, delete-orphan")


class KPIHistory(Base):
    """A recorded historical value for a KPI."""

    __tablename__ = "kpi_history"

    id = Column(Integer, primary_key=True, index=True)
    kpi_id = Column(Integer, ForeignKey("kpis.id"), nullable=False)
    value = Column(Numeric(15, 2), nullable=False)
    recorded_at = Column(DateTime(timezone=True), server_default=func.now())
    notes = Column(Text)

    # Relationships
    kpi = relationship("KPI", back_populates="history")


class KPIEmbedding(Base):
    """A vector embedding associated with a KPI for semantic search."""

    __tablename__ = "kpi_embeddings"

    id = Column(Integer, primary_key=True, index=True)
    kpi_id = Column(Integer, ForeignKey("kpis.id"), nullable=False)
    embedding = Column(Vector(settings.VECTOR_DIMENSION))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    kpi = relationship("KPI", back_populates="embeddings")


# Pydantic models for API
class KPIBase(BaseModel):
    """Shared KPI fields."""

    name: str
    description: Optional[str] = None
    category: KPICategory = KPICategory.OTHER
    unit: Optional[str] = None
    target_value: Optional[float] = None
    current_value: Optional[float] = None


class KPICreate(KPIBase):
    """Payload for creating a KPI."""

    organization_id: int
    dashboard_id: Optional[int] = None


class KPIUpdate(BaseModel):
    """Mutable KPI fields."""

    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[KPICategory] = None
    unit: Optional[str] = None
    target_value: Optional[float] = None
    current_value: Optional[float] = None
    dashboard_id: Optional[int] = None


class KPIHistoryCreate(BaseModel):
    """Payload for recording a KPI value."""

    value: float
    notes: Optional[str] = None


class KPIHistoryResponse(BaseModel):
    """KPI history record returned by the API."""

    id: int
    kpi_id: int
    value: float
    recorded_at: datetime
    notes: Optional[str] = None

    class Config:
        """Enable ORM attribute population."""

        from_attributes = True


class KPIResponse(KPIBase):
    """KPI record returned by the API."""

    id: int
    organization_id: int
    dashboard_id: Optional[int] = None
    created_by: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        """Enable ORM attribute population."""

        from_attributes = True


class KPIWithHistory(KPIResponse):
    """KPI record including its history."""

    history: List[KPIHistoryResponse] = []

    class Config:
        """Enable ORM attribute population."""

        from_attributes = True


class KPIAnalytics(BaseModel):
    """Computed analytics and insights for a KPI."""

    kpi_id: int
    trend: str  # "increasing", "decreasing", "stable"
    change_percentage: float
    period: str  # "week", "month", "quarter", "year"
    insights: List[str]
    recommendations: List[str]
