from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.security import get_current_active_user, require_role, UserRole
from app.models.user import User, UserCreate, UserUpdate, UserResponse, UserInDB
from app.models.organization import UserOrganization, UserOrganizationCreate
from app.core.security import get_password_hash

router = APIRouter()


@router.get("/", response_model=List[UserResponse])
async def get_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    organization_id: Optional[int] = Query(None),
    role: Optional[UserRole] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get list of users with optional filtering."""
    # Only admins can list all users
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    
    query = select(User).options(selectinload(User.organizations))
    
    if organization_id:
        query = query.join(UserOrganization).where(UserOrganization.organization_id == organization_id)
    
    if role:
        query = query.where(User.role == role)
    
    query = query.offset(skip).limit(limit)
    
    result = await db.execute(query)
    users = result.scalars().unique().all()
    
    return users


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_active_user)
):
    """Get current user information."""
    return current_user


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get user by ID."""
    # Users can only view their own profile or admins can view any user
    if current_user.id != user_id and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    
    result = await db.execute(
        select(User).options(selectinload(User.organizations)).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return user


@router.post("/", response_model=UserResponse)
async def create_user(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN))
):
    """Create a new user (admin only)."""
    # Check if user with email already exists
    result = await db.execute(select(User).where(User.email == user_data.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Check if username already exists
    result = await db.execute(select(User).where(User.username == user_data.username))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username already taken")
    
    # Create new user
    hashed_password = get_password_hash(user_data.password)
    user = User(
        email=user_data.email,
        username=user_data.username,
        full_name=user_data.full_name,
        hashed_password=hashed_password,
        role=user_data.role
    )
    
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    return user


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Update user information."""
    # Users can only update their own profile or admins can update any user
    if current_user.id != user_id and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    
    # Get user to update
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update fields
    update_data = user_data.dict(exclude_unset=True)
    
    # Handle password update
    if "password" in update_data:
        update_data["hashed_password"] = get_password_hash(update_data.pop("password"))
    
    # Check email uniqueness if being updated
    if "email" in update_data and update_data["email"] != user.email:
        result = await db.execute(select(User).where(User.email == update_data["email"]))
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Email already registered")
    
    # Check username uniqueness if being updated
    if "username" in update_data and update_data["username"] != user.username:
        result = await db.execute(select(User).where(User.username == update_data["username"]))
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Username already taken")
    
    # Apply updates
    for field, value in update_data.items():
        setattr(user, field, value)
    
    await db.commit()
    await db.refresh(user)
    
    return user


@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN))
):
    """Delete a user (admin only)."""
    # Prevent self-deletion
    if current_user.id == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    await db.delete(user)
    await db.commit()
    
    return {"message": "User deleted successfully"}


@router.post("/{user_id}/organizations")
async def add_user_to_organization(
    user_id: int,
    org_data: UserOrganizationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MANAGER))
):
    """Add user to an organization."""
    # Check if user exists
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Check if user is already in the organization
    result = await db.execute(
        select(UserOrganization).where(
            UserOrganization.user_id == user_id,
            UserOrganization.organization_id == org_data.organization_id
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="User is already in this organization")
    
    # Create user-organization relationship
    user_org = UserOrganization(
        user_id=user_id,
        organization_id=org_data.organization_id,
        role=org_data.role
    )
    
    db.add(user_org)
    await db.commit()
    
    return {"message": "User added to organization successfully"}


@router.delete("/{user_id}/organizations/{organization_id}")
async def remove_user_from_organization(
    user_id: int,
    organization_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MANAGER))
):
    """Remove user from an organization."""
    result = await db.execute(
        select(UserOrganization).where(
            UserOrganization.user_id == user_id,
            UserOrganization.organization_id == organization_id
        )
    )
    user_org = result.scalar_one_or_none()
    
    if not user_org:
        raise HTTPException(status_code=404, detail="User not found in organization")
    
    await db.delete(user_org)
    await db.commit()
    
    return {"message": "User removed from organization successfully"} 