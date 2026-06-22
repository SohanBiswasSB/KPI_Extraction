from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.security import get_current_active_user, require_role, UserRole
from app.models.organization import (
    Organization, OrganizationCreate, OrganizationUpdate, OrganizationResponse,
    UserOrganization, UserOrganizationCreate, UserOrganizationUpdate,
    UserOrganizationResponse, OrganizationWithUsers
)
from app.models.user import User

router = APIRouter()


@router.get("/", response_model=List[OrganizationResponse])
async def get_organizations(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get list of organizations accessible to the current user."""
    query = select(Organization).options(
        selectinload(Organization.users)
    )
    
    # Apply pagination
    query = query.offset(skip).limit(limit)
    
    result = await db.execute(query)
    organizations = result.scalars().all()
    
    # Filter organizations based on user access
    accessible_organizations = []
    for org in organizations:
        # User can access if:
        # 1. They are a member of the organization
        # 2. They are admin
        if (current_user.role == UserRole.ADMIN or
            any(user_org.user_id == current_user.id for user_org in org.users)):
            accessible_organizations.append(org)
    
    return accessible_organizations


@router.get("/{organization_id}", response_model=OrganizationWithUsers)
async def get_organization(
    organization_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get a specific organization by ID."""
    result = await db.execute(
        select(Organization).options(
            selectinload(Organization.users).selectinload(UserOrganization.user)
        ).where(Organization.id == organization_id)
    )
    organization = result.scalar_one_or_none()
    
    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found")
    
    # Check access permissions
    if (current_user.role != UserRole.ADMIN and
        not any(user_org.user_id == current_user.id for user_org in organization.users)):
        raise HTTPException(status_code=403, detail="Access denied")
    
    return organization


@router.post("/", response_model=OrganizationResponse)
async def create_organization(
    organization_data: OrganizationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MANAGER))
):
    """Create a new organization."""
    # Check if organization with same name already exists
    result = await db.execute(
        select(Organization).where(Organization.name == organization_data.name)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Organization with this name already exists")
    
    # Create organization
    organization = Organization(
        name=organization_data.name,
        description=organization_data.description
    )
    
    db.add(organization)
    await db.commit()
    await db.refresh(organization)
    
    # Add current user as admin of the organization
    user_org = UserOrganization(
        user_id=current_user.id,
        organization_id=organization.id,
        role=UserRole.MANAGER  # Creator becomes manager
    )
    
    db.add(user_org)
    await db.commit()
    
    return organization


@router.put("/{organization_id}", response_model=OrganizationResponse)
async def update_organization(
    organization_id: int,
    organization_data: OrganizationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Update an organization."""
    result = await db.execute(
        select(Organization).where(Organization.id == organization_id)
    )
    organization = result.scalar_one_or_none()
    
    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found")
    
    # Check permissions: user must be manager of the organization or admin
    result = await db.execute(
        select(UserOrganization).where(
            and_(
                UserOrganization.organization_id == organization_id,
                UserOrganization.user_id == current_user.id
            )
        )
    )
    user_org = result.scalar_one_or_none()
    
    if (current_user.role != UserRole.ADMIN and 
        (not user_org or user_org.role not in [UserRole.MANAGER, UserRole.ADMIN])):
        raise HTTPException(status_code=403, detail="Not enough permissions")
    
    # Check name uniqueness if being updated
    if "name" in organization_data.dict(exclude_unset=True):
        result = await db.execute(
            select(Organization).where(
                and_(
                    Organization.name == organization_data.name,
                    Organization.id != organization_id
                )
            )
        )
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Organization with this name already exists")
    
    # Update fields
    update_data = organization_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(organization, field, value)
    
    await db.commit()
    await db.refresh(organization)
    
    return organization


@router.delete("/{organization_id}")
async def delete_organization(
    organization_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN))
):
    """Delete an organization (admin only)."""
    result = await db.execute(
        select(Organization).where(Organization.id == organization_id)
    )
    organization = result.scalar_one_or_none()
    
    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found")
    
    await db.delete(organization)
    await db.commit()
    
    return {"message": "Organization deleted successfully"}


@router.post("/{organization_id}/users", response_model=UserOrganizationResponse)
async def add_user_to_organization(
    organization_id: int,
    user_org_data: UserOrganizationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Add a user to an organization."""
    # Verify organization exists
    result = await db.execute(
        select(Organization).where(Organization.id == organization_id)
    )
    organization = result.scalar_one_or_none()
    
    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found")
    
    # Check permissions: user must be manager of the organization or admin
    result = await db.execute(
        select(UserOrganization).where(
            and_(
                UserOrganization.organization_id == organization_id,
                UserOrganization.user_id == current_user.id
            )
        )
    )
    user_org = result.scalar_one_or_none()
    
    if (current_user.role != UserRole.ADMIN and 
        (not user_org or user_org.role not in [UserRole.MANAGER, UserRole.ADMIN])):
        raise HTTPException(status_code=403, detail="Not enough permissions")
    
    # Verify user exists
    result = await db.execute(
        select(User).where(User.id == user_org_data.user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Check if user is already in the organization
    result = await db.execute(
        select(UserOrganization).where(
            and_(
                UserOrganization.organization_id == organization_id,
                UserOrganization.user_id == user_org_data.user_id
            )
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="User is already in this organization")
    
    # Create user-organization relationship
    user_org = UserOrganization(
        user_id=user_org_data.user_id,
        organization_id=organization_id,
        role=user_org_data.role
    )
    
    db.add(user_org)
    await db.commit()
    await db.refresh(user_org)
    
    return user_org


@router.put("/{organization_id}/users/{user_id}", response_model=UserOrganizationResponse)
async def update_user_organization_role(
    organization_id: int,
    user_id: int,
    user_org_data: UserOrganizationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Update a user's role in an organization."""
    # Verify organization exists
    result = await db.execute(
        select(Organization).where(Organization.id == organization_id)
    )
    organization = result.scalar_one_or_none()
    
    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found")
    
    # Check permissions: user must be manager of the organization or admin
    result = await db.execute(
        select(UserOrganization).where(
            and_(
                UserOrganization.organization_id == organization_id,
                UserOrganization.user_id == current_user.id
            )
        )
    )
    current_user_org = result.scalar_one_or_none()
    
    if (current_user.role != UserRole.ADMIN and 
        (not current_user_org or current_user_org.role not in [UserRole.MANAGER, UserRole.ADMIN])):
        raise HTTPException(status_code=403, detail="Not enough permissions")
    
    # Get user-organization relationship to update
    result = await db.execute(
        select(UserOrganization).where(
            and_(
                UserOrganization.organization_id == organization_id,
                UserOrganization.user_id == user_id
            )
        )
    )
    user_org = result.scalar_one_or_none()
    
    if not user_org:
        raise HTTPException(status_code=404, detail="User not found in organization")
    
    # Update role
    update_data = user_org_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user_org, field, value)
    
    await db.commit()
    await db.refresh(user_org)
    
    return user_org


@router.delete("/{organization_id}/users/{user_id}")
async def remove_user_from_organization(
    organization_id: int,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Remove a user from an organization."""
    # Verify organization exists
    result = await db.execute(
        select(Organization).where(Organization.id == organization_id)
    )
    organization = result.scalar_one_or_none()
    
    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found")
    
    # Check permissions: user must be manager of the organization or admin
    result = await db.execute(
        select(UserOrganization).where(
            and_(
                UserOrganization.organization_id == organization_id,
                UserOrganization.user_id == current_user.id
            )
        )
    )
    current_user_org = result.scalar_one_or_none()
    
    if (current_user.role != UserRole.ADMIN and 
        (not current_user_org or current_user_org.role not in [UserRole.MANAGER, UserRole.ADMIN])):
        raise HTTPException(status_code=403, detail="Not enough permissions")
    
    # Prevent self-removal
    if current_user.id == user_id:
        raise HTTPException(status_code=400, detail="Cannot remove yourself from organization")
    
    # Get user-organization relationship to remove
    result = await db.execute(
        select(UserOrganization).where(
            and_(
                UserOrganization.organization_id == organization_id,
                UserOrganization.user_id == user_id
            )
        )
    )
    user_org = result.scalar_one_or_none()
    
    if not user_org:
        raise HTTPException(status_code=404, detail="User not found in organization")
    
    await db.delete(user_org)
    await db.commit()
    
    return {"message": "User removed from organization successfully"}


@router.get("/{organization_id}/users", response_model=List[UserOrganizationResponse])
async def get_organization_users(
    organization_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get all users in an organization."""
    # Verify organization exists
    result = await db.execute(
        select(Organization).where(Organization.id == organization_id)
    )
    organization = result.scalar_one_or_none()
    
    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found")
    
    # Check access permissions
    result = await db.execute(
        select(UserOrganization).where(
            and_(
                UserOrganization.organization_id == organization_id,
                UserOrganization.user_id == current_user.id
            )
        )
    )
    user_org = result.scalar_one_or_none()
    
    if (current_user.role != UserRole.ADMIN and not user_org):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get organization users
    result = await db.execute(
        select(UserOrganization).options(
            selectinload(UserOrganization.user)
        ).where(
            UserOrganization.organization_id == organization_id
        ).offset(skip).limit(limit)
    )
    users = result.scalars().all()
    
    return users 