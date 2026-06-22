"""Database models and Pydantic schemas for organizations and memberships."""
from datetime import datetime
from typing import Optional, List

from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from pydantic import BaseModel

from app.core.database import Base


class Organization(Base):
    """A tenant organization that owns dashboards, KPIs, and files."""

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
    """Membership link between a user and an organization."""

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
    """Shared organization fields."""

    name: str
    description: Optional[str] = None


class OrganizationCreate(OrganizationBase):
    """Payload for creating an organization."""


class OrganizationUpdate(BaseModel):
    """Mutable organization fields."""

    name: Optional[str] = None
    description: Optional[str] = None


class OrganizationResponse(OrganizationBase):
    """Organization record returned by the API."""

    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        """Enable ORM attribute population."""

        from_attributes = True


class UserOrganizationCreate(BaseModel):
    """Payload for adding a user to an organization."""

    user_id: int
    organization_id: int
    role: str = "viewer"


class UserOrganizationUpdate(BaseModel):
    """Mutable membership fields."""

    role: str


class UserOrganizationResponse(BaseModel):
    """Membership record returned by the API."""

    id: int
    user_id: int
    organization_id: int
    role: str
    created_at: datetime

    class Config:
        """Enable ORM attribute population."""

        from_attributes = True


class OrganizationWithUsers(OrganizationResponse):
    """Organization record including its memberships."""

    users: List[UserOrganizationResponse] = []

    class Config:
        """Enable ORM attribute population."""

        from_attributes = True
