"""Database models and Pydantic schemas for users and authentication."""
import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from pydantic import BaseModel, EmailStr

from app.core.database import Base


class UserRole(str, enum.Enum):
    """Access levels available to a user."""

    ADMIN = "admin"
    MANAGER = "manager"
    ANALYST = "analyst"
    VIEWER = "viewer"


class User(Base):
    """An application user account."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    username = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255))
    role = Column(
        Enum(UserRole, name="user_role",
             values_callable=lambda e: [m.value for m in e]),
        default=UserRole.VIEWER,
    )
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    dashboards = relationship("Dashboard", back_populates="created_by_user")
    kpis = relationship("KPI", back_populates="created_by_user")
    uploaded_files = relationship("UploadedFile", back_populates="uploaded_by_user")
    # Association rows linking this user to organizations (mirrors
    # Organization.users); the users endpoints selectinload this.
    organizations = relationship("UserOrganization", back_populates="user")
    # DashboardShare has two FKs to users (shared_with / shared_by), so the
    # join column must be named explicitly on this side too.
    shared_dashboards = relationship(
        "DashboardShare",
        back_populates="shared_with_user",
        foreign_keys="DashboardShare.shared_with",
    )


# Pydantic models for API
class UserBase(BaseModel):
    """Shared user fields."""

    email: EmailStr
    username: str
    full_name: Optional[str] = None
    role: UserRole = UserRole.VIEWER


class UserCreate(UserBase):
    """Payload for creating a user."""

    password: str


class UserUpdate(BaseModel):
    """Mutable user fields."""

    email: Optional[EmailStr] = None
    username: Optional[str] = None
    full_name: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


class UserInDB(UserBase):
    """User record as stored in the database."""

    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        """Enable ORM attribute population."""

        from_attributes = True


class UserResponse(UserBase):
    """User record returned by the API."""

    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        """Enable ORM attribute population."""

        from_attributes = True


class UserLogin(BaseModel):
    """Login credentials payload."""

    email: EmailStr
    password: str


class Token(BaseModel):
    """Issued authentication token bundle."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_token: str


class TokenData(BaseModel):
    """Decoded token claims."""

    email: Optional[str] = None
    user_id: Optional[int] = None
