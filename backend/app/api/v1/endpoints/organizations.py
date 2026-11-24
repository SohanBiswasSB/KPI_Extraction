"""Organization endpoints: CRUD operations and user-organization membership management."""

import logging
import os
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy import text as sql_text
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.security import get_current_active_user, require_role, UserRole
from app.models.organization import (
    Organization, OrganizationCreate, OrganizationUpdate, OrganizationResponse,
    UserOrganization, UserOrganizationCreate, UserOrganizationUpdate,
    UserOrganizationResponse, OrganizationWithUsers
)
from app.models.user import User
from app.models.file import UploadedFile
from app.models.kpi import KPI

logger = logging.getLogger(__name__)

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
            raise HTTPException(
                status_code=400,
                detail="Organization with this name already exists",
            )

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
    cascade: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN))
):
    """Delete an organization (admin only).

    Refuses by default while the organization still owns files or curated
    KPIs, naming all of them so the caller knows the full extent in one go.
    Pass ``cascade=true`` to delete that content along with it - the caller is
    expected to have confirmed against the counts from the refusal first.
    """
    result = await db.execute(
        select(Organization).where(Organization.id == organization_id)
    )
    organization = result.scalar_one_or_none()

    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Report what is holding the organization rather than letting the delete
    # hit a foreign key and surface as an opaque 500. Say all of it at once, so
    # the caller can clear everything in one pass instead of discovering each
    # blocker on a separate attempt.
    blockers = []
    for label, table in (("file", "uploaded_files"), ("KPI", "kpis")):
        count = await db.scalar(
            sql_text(f"SELECT count(*) FROM {table} WHERE organization_id = :oid"),
            {"oid": organization_id},
        )
        if count:
            blockers.append(f"{count} {label}{'s' if count != 1 else ''}")
    if blockers and not cascade:
        raise HTTPException(
            status_code=409,
            detail=(f"Organization still has {', '.join(blockers)}. "
                    "Delete those first, or retry with cascade to remove "
                    "them along with it."),
        )

    if cascade:
        # Remove the files through the ORM so the tables, extracted KPIs and
        # embeddings hanging off each one go with them, and take the stored
        # upload off disk too - a raw DELETE would orphan both.
        files = (await db.execute(
            select(UploadedFile).where(
                UploadedFile.organization_id == organization_id)
        )).scalars().all()
        for stored in files:
            if stored.file_path and os.path.exists(stored.file_path):
                os.remove(stored.file_path)
            await db.delete(stored)
        curated = (await db.execute(
            select(KPI).where(KPI.organization_id == organization_id)
        )).scalars().all()
        for kpi in curated:
            await db.delete(kpi)
        await db.flush()
        logger.info("Cascade delete of organization %s removed %d file(s), "
                    "%d curated KPI(s)", organization_id, len(files),
                    len(curated))

    # Memberships are not user data to preserve - creating an organization
    # enrols its creator, so treating a membership as a blocker would make
    # every new organization permanently undeletable. They go with the row.
    await db.execute(
        sql_text("DELETE FROM user_organizations WHERE organization_id = :oid"),
        {"oid": organization_id},
    )
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
