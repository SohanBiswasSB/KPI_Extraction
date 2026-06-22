from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class Organization(Base):
    __tablename__ = "organizations"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    users = relationship("UserOrganization", back_populates="organization")
    dashboards = relationship("Dashboard", back_populates="organization")
    kpis = relationship("KPI", back_populates="organization")
    uploaded_files = relationship("UploadedFile", back_populates="organization")


class UserOrganization(Base):
    __tablename__ = "user_organizations"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    role = Column(String(50), default="viewer")  # Using string instead of enum for flexibility
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    user = relationship("User")
    organization = relationship("Organization", back_populates="users")


# Pydantic models for API
class OrganizationBase(BaseModel):
    name: str
    description: Optional[str] = None


class OrganizationCreate(OrganizationBase):
    pass


class OrganizationUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class OrganizationResponse(OrganizationBase):
    id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class UserOrganizationCreate(BaseModel):
    user_id: int
    organization_id: int
    role: str = "viewer"


class UserOrganizationUpdate(BaseModel):
    role: str


class UserOrganizationResponse(BaseModel):
    id: int
    user_id: int
    organization_id: int
    role: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class OrganizationWithUsers(OrganizationResponse):
    users: List[UserOrganizationResponse] = []
    
    class Config:
        from_attributes = True 