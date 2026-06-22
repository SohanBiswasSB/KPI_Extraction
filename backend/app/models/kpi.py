from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum, Text, Numeric, ForeignKey, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base
import enum
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class KPICategory(str, enum.Enum):
    FINANCIAL = "financial"
    OPERATIONAL = "operational"
    CUSTOMER = "customer"
    EMPLOYEE = "employee"
    MARKETING = "marketing"
    OTHER = "other"


class KPI(Base):
    __tablename__ = "kpis"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text)
    category = Column(Enum(KPICategory), default=KPICategory.OTHER)
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
    __tablename__ = "kpi_history"
    
    id = Column(Integer, primary_key=True, index=True)
    kpi_id = Column(Integer, ForeignKey("kpis.id"), nullable=False)
    value = Column(Numeric(15, 2), nullable=False)
    recorded_at = Column(DateTime(timezone=True), server_default=func.now())
    notes = Column(Text)
    
    # Relationships
    kpi = relationship("KPI", back_populates="history")


class KPIEmbedding(Base):
    __tablename__ = "kpi_embeddings"
    
    id = Column(Integer, primary_key=True, index=True)
    kpi_id = Column(Integer, ForeignKey("kpis.id"), nullable=False)
    embedding = Column("embedding", type_=None)  # Will be handled by pgvector
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    kpi = relationship("KPI", back_populates="embeddings")


# Pydantic models for API
class KPIBase(BaseModel):
    name: str
    description: Optional[str] = None
    category: KPICategory = KPICategory.OTHER
    unit: Optional[str] = None
    target_value: Optional[float] = None
    current_value: Optional[float] = None


class KPICreate(KPIBase):
    organization_id: int
    dashboard_id: Optional[int] = None


class KPIUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[KPICategory] = None
    unit: Optional[str] = None
    target_value: Optional[float] = None
    current_value: Optional[float] = None
    dashboard_id: Optional[int] = None


class KPIHistoryCreate(BaseModel):
    value: float
    notes: Optional[str] = None


class KPIHistoryResponse(BaseModel):
    id: int
    kpi_id: int
    value: float
    recorded_at: datetime
    notes: Optional[str] = None
    
    class Config:
        from_attributes = True


class KPIResponse(KPIBase):
    id: int
    organization_id: int
    dashboard_id: Optional[int] = None
    created_by: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class KPIWithHistory(KPIResponse):
    history: List[KPIHistoryResponse] = []
    
    class Config:
        from_attributes = True


class KPIAnalytics(BaseModel):
    kpi_id: int
    trend: str  # "increasing", "decreasing", "stable"
    change_percentage: float
    period: str  # "week", "month", "quarter", "year"
    insights: List[str]
    recommendations: List[str] 