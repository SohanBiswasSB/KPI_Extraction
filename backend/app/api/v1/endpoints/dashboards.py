"""Dashboard endpoints: CRUD operations, access control, and dashboard sharing."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.security import get_current_active_user, require_role, UserRole
from app.models.dashboard import (
    Dashboard, DashboardCreate, DashboardUpdate, DashboardResponse,
    DashboardShare, DashboardShareCreate, DashboardShareUpdate, DashboardShareResponse,
    DashboardWithShares
)
from app.models.user import User
from app.models.organization import Organization

router = APIRouter()


@router.get("/", response_model=List[DashboardResponse])
async def get_dashboards(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    organization_id: Optional[int] = Query(None),
    is_public: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get list of dashboards accessible to the current user."""
    # Build query based on user's access
    query = select(Dashboard).options(
        selectinload(Dashboard.creator),
        selectinload(Dashboard.organization),
        selectinload(Dashboard.shares).selectinload(DashboardShare.user)
    )

    # Filter by organization if specified
    if organization_id:
        query = query.where(Dashboard.organization_id == organization_id)

    # Filter by public status if specified
    if is_public is not None:
        query = query.where(Dashboard.is_public == is_public)

    # Apply pagination
    query = query.offset(skip).limit(limit)

    result = await db.execute(query)
    dashboards = result.scalars().unique().all()

    # Filter dashboards based on user permissions
    accessible_dashboards = []
    for dashboard in dashboards:
        # User can access if:
        # 1. They created the dashboard
        # 2. Dashboard is public
        # 3. They have explicit share permissions
        # 4. They are admin
        if (dashboard.creator_id == current_user.id or
            dashboard.is_public or
            current_user.role == UserRole.ADMIN or
            any(share.user_id == current_user.id for share in dashboard.shares)):
            accessible_dashboards.append(dashboard)

    return accessible_dashboards


@router.get("/{dashboard_id}", response_model=DashboardWithShares)
async def get_dashboard(
    dashboard_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get a specific dashboard by ID."""
    result = await db.execute(
        select(Dashboard).options(
            selectinload(Dashboard.creator),
            selectinload(Dashboard.organization),
            selectinload(Dashboard.shares).selectinload(DashboardShare.user),
            selectinload(Dashboard.kpis)
        ).where(Dashboard.id == dashboard_id)
    )
    dashboard = result.scalar_one_or_none()

    if not dashboard:
        raise HTTPException(status_code=404, detail="Dashboard not found")

    # Check access permissions
    if (dashboard.creator_id != current_user.id and
        not dashboard.is_public and
        current_user.role != UserRole.ADMIN and
        not any(share.user_id == current_user.id for share in dashboard.shares)):
        raise HTTPException(status_code=403, detail="Access denied")

    return dashboard


@router.post("/", response_model=DashboardResponse)
async def create_dashboard(
    dashboard_data: DashboardCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ANALYST))
):
    """Create a new dashboard."""
    # Verify organization exists and user has access
    result = await db.execute(
        select(Organization).where(Organization.id == dashboard_data.organization_id)
    )
    organization = result.scalar_one_or_none()

    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Create dashboard
    dashboard = Dashboard(
        name=dashboard_data.name,
        description=dashboard_data.description,
        organization_id=dashboard_data.organization_id,
        creator_id=current_user.id,
        is_public=dashboard_data.is_public,
        layout=dashboard_data.layout.dict() if dashboard_data.layout else None
    )

    db.add(dashboard)
    await db.commit()
    await db.refresh(dashboard)

    return dashboard


@router.put("/{dashboard_id}", response_model=DashboardResponse)
async def update_dashboard(
    dashboard_id: int,
    dashboard_data: DashboardUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Update a dashboard."""
    result = await db.execute(
        select(Dashboard).where(Dashboard.id == dashboard_id)
    )
    dashboard = result.scalar_one_or_none()

    if not dashboard:
        raise HTTPException(status_code=404, detail="Dashboard not found")

    # Check permissions: creator or admin can update
    if dashboard.creator_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    # Update fields
    update_data = dashboard_data.dict(exclude_unset=True)

    # Handle layout update
    if "layout" in update_data and update_data["layout"]:
        update_data["layout"] = update_data["layout"].dict()

    for field, value in update_data.items():
        setattr(dashboard, field, value)

    await db.commit()
    await db.refresh(dashboard)

    return dashboard


@router.delete("/{dashboard_id}")
async def delete_dashboard(
    dashboard_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Delete a dashboard."""
    result = await db.execute(
        select(Dashboard).where(Dashboard.id == dashboard_id)
    )
    dashboard = result.scalar_one_or_none()

    if not dashboard:
        raise HTTPException(status_code=404, detail="Dashboard not found")

    # Check permissions: creator or admin can delete
    if dashboard.creator_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    await db.delete(dashboard)
    await db.commit()

    return {"message": "Dashboard deleted successfully"}


@router.post("/{dashboard_id}/share", response_model=DashboardShareResponse)
async def share_dashboard(
    dashboard_id: int,
    share_data: DashboardShareCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Share a dashboard with another user."""
    # Verify dashboard exists
    result = await db.execute(
        select(Dashboard).where(Dashboard.id == dashboard_id)
    )
    dashboard = result.scalar_one_or_none()

    if not dashboard:
        raise HTTPException(status_code=404, detail="Dashboard not found")

    # Check permissions: creator or admin can share
    if dashboard.creator_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    # Verify user exists
    result = await db.execute(
        select(User).where(User.id == share_data.user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Check if share already exists
    result = await db.execute(
        select(DashboardShare).where(
            and_(
                DashboardShare.dashboard_id == dashboard_id,
                DashboardShare.user_id == share_data.user_id
            )
        )
    )
    existing_share = result.scalar_one_or_none()

    if existing_share:
        raise HTTPException(status_code=400, detail="Dashboard already shared with this user")

    # Create share
    share = DashboardShare(
        dashboard_id=dashboard_id,
        user_id=share_data.user_id,
        permission_level=share_data.permission_level
    )

    db.add(share)
    await db.commit()
    await db.refresh(share)

    return share


@router.put("/{dashboard_id}/share/{share_id}", response_model=DashboardShareResponse)
async def update_dashboard_share(
    dashboard_id: int,
    share_id: int,
    share_data: DashboardShareUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Update dashboard share permissions."""
    result = await db.execute(
        select(DashboardShare).where(DashboardShare.id == share_id)
    )
    share = result.scalar_one_or_none()

    if not share or share.dashboard_id != dashboard_id:
        raise HTTPException(status_code=404, detail="Share not found")

    # Check permissions: dashboard creator or admin can update shares
    result = await db.execute(
        select(Dashboard).where(Dashboard.id == dashboard_id)
    )
    dashboard = result.scalar_one_or_none()

    if dashboard.creator_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    # Update share
    update_data = share_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(share, field, value)

    await db.commit()
    await db.refresh(share)

    return share


@router.delete("/{dashboard_id}/share/{share_id}")
async def remove_dashboard_share(
    dashboard_id: int,
    share_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Remove dashboard share."""
    result = await db.execute(
        select(DashboardShare).where(DashboardShare.id == share_id)
    )
    share = result.scalar_one_or_none()

    if not share or share.dashboard_id != dashboard_id:
        raise HTTPException(status_code=404, detail="Share not found")

    # Check permissions: dashboard creator or admin can remove shares
    result = await db.execute(
        select(Dashboard).where(Dashboard.id == dashboard_id)
    )
    dashboard = result.scalar_one_or_none()

    if dashboard.creator_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    await db.delete(share)
    await db.commit()

    return {"message": "Dashboard share removed successfully"}


@router.get("/{dashboard_id}/shares", response_model=List[DashboardShareResponse])
async def get_dashboard_shares(
    dashboard_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get all shares for a dashboard."""
    # Verify dashboard exists
    result = await db.execute(
        select(Dashboard).where(Dashboard.id == dashboard_id)
    )
    dashboard = result.scalar_one_or_none()

    if not dashboard:
        raise HTTPException(status_code=404, detail="Dashboard not found")

    # Check permissions: creator or admin can view shares
    if dashboard.creator_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    result = await db.execute(
        select(DashboardShare).options(
            selectinload(DashboardShare.user)
        ).where(DashboardShare.dashboard_id == dashboard_id)
    )
    shares = result.scalars().all()

    return shares
