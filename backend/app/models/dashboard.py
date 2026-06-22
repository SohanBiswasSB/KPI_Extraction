from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.user import UserRole
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime


class Dashboard(Base):
    __tablename__ = "dashboards"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"))
    is_public = Column(Boolean, default=False)
    layout = Column(JSON)  # Store dashboard layout configuration
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    organization = relationship("Organization", back_populates="dashboards")
    created_by_user = relationship("User", back_populates="dashboards")
    kpis = relationship("KPI", back_populates="dashboard")
    shares = relationship("DashboardShare", back_populates="dashboard", cascade="all, delete-orphan")


class DashboardShare(Base):
    __tablename__ = "dashboard_shares"
    
    id = Column(Integer, primary_key=True, index=True)
    dashboard_id = Column(Integer, ForeignKey("dashboards.id"), nullable=False)
    shared_with = Column(Integer, ForeignKey("users.id"), nullable=False)
    shared_by = Column(Integer, ForeignKey("users.id"))
    permission_level = Column(ENUM('admin', 'manager', 'analyst', 'viewer', name='user_role'), default='viewer')
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    dashboard = relationship("Dashboard", back_populates="shares")
    shared_with_user = relationship("User", back_populates="shared_dashboards", foreign_keys=[shared_with])
    shared_by_user = relationship("User", foreign_keys=[shared_by])


# Pydantic models for API
class DashboardBase(BaseModel):
    name: str
    description: Optional[str] = None
    is_public: bool = False
    layout: Optional[Dict[str, Any]] = None


class DashboardCreate(DashboardBase):
    organization_id: int


class DashboardUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_public: Optional[bool] = None
    layout: Optional[Dict[str, Any]] = None


class DashboardShareCreate(BaseModel):
    shared_with: int  # user_id
    permission_level: UserRole = UserRole.VIEWER


class DashboardShareUpdate(BaseModel):
    permission_level: UserRole


class DashboardShareResponse(BaseModel):
    id: int
    dashboard_id: int
    shared_with: int
    shared_by: Optional[int] = None
    permission_level: UserRole
    created_at: datetime
    
    class Config:
        from_attributes = True


class DashboardResponse(DashboardBase):
    id: int
    organization_id: int
    created_by: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class DashboardWithShares(DashboardResponse):
    shares: List[DashboardShareResponse] = []
    
    class Config:
        from_attributes = True


class DashboardWidget(BaseModel):
    id: str
    type: str  # "chart", "table", "metric", "kpi"
    title: str
    config: Dict[str, Any]
    position: Dict[str, int]  # x, y, width, height
    data_source: Optional[str] = None


class DashboardLayout(BaseModel):
    widgets: List[DashboardWidget]
    grid_size: Dict[str, int] = {"columns": 12, "rows": 12}
    theme: Optional[str] = "default" 