from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from datetime import datetime

from app.core.database import get_db
from app.core.security import get_current_active_user, require_minimum_role
from app.models.user import User, UserRole
from app.models.kpi import KPI, KPIHistory, KPICreate, KPIUpdate, KPIResponse, KPIHistoryCreate
from app.services.ai_service import AIService

router = APIRouter()
ai_service = AIService()


@router.get("/", response_model=List[KPIResponse])
async def get_kpis(
    organization_id: int = Query(..., description="Organization ID"),
    dashboard_id: Optional[int] = Query(None, description="Filter by dashboard ID"),
    category: Optional[str] = Query(None, description="Filter by category"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get KPIs for an organization."""
    query = select(KPI).where(KPI.organization_id == organization_id)
    
    if dashboard_id:
        query = query.where(KPI.dashboard_id == dashboard_id)
    
    if category:
        query = query.where(KPI.category == category)
    
    result = await db.execute(query)
    kpis = result.scalars().all()
    
    return kpis


@router.get("/{kpi_id}", response_model=KPIResponse)
async def get_kpi(
    kpi_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get a specific KPI by ID."""
    result = await db.execute(select(KPI).where(KPI.id == kpi_id))
    kpi = result.scalar_one_or_none()
    
    if not kpi:
        raise HTTPException(status_code=404, detail="KPI not found")
    
    return kpi


@router.post("/", response_model=KPIResponse)
async def create_kpi(
    kpi_data: KPICreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_minimum_role(UserRole.ANALYST))
):
    """Create a new KPI with enhanced metadata and vector embeddings."""
    try:
        # Create KPI with all fields
        kpi_dict = kpi_data.dict(exclude_unset=True)
        kpi = KPI(
            **kpi_dict,
            created_by=current_user.id
        )
        
        db.add(kpi)
        await db.commit()
        await db.refresh(kpi)
        
        # Generate embeddings for the KPI for better searchability
        try:
            await ai_service.create_kpi_embedding(kpi, db)
        except Exception as embedding_error:
            # Log the error but don't fail the KPI creation
            print(f"Warning: Failed to create KPI embedding: {embedding_error}")
        
        return kpi
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create KPI: {str(e)}"
        )


@router.put("/{kpi_id}", response_model=KPIResponse)
async def update_kpi(
    kpi_id: int,
    kpi_data: KPIUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_minimum_role(UserRole.ANALYST))
):
    """Update a KPI."""
    result = await db.execute(select(KPI).where(KPI.id == kpi_id))
    kpi = result.scalar_one_or_none()
    
    if not kpi:
        raise HTTPException(status_code=404, detail="KPI not found")
    
    # Update fields
    for field, value in kpi_data.dict(exclude_unset=True).items():
        setattr(kpi, field, value)
    
    await db.commit()
    await db.refresh(kpi)
    
    return kpi


@router.delete("/{kpi_id}")
async def delete_kpi(
    kpi_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_minimum_role(UserRole.MANAGER))
):
    """Delete a KPI."""
    result = await db.execute(select(KPI).where(KPI.id == kpi_id))
    kpi = result.scalar_one_or_none()
    
    if not kpi:
        raise HTTPException(status_code=404, detail="KPI not found")
    
    await db.delete(kpi)
    await db.commit()
    
    return {"message": "KPI deleted successfully"}


@router.get("/{kpi_id}/history")
async def get_kpi_history(
    kpi_id: int,
    limit: int = Query(30, description="Number of history records to return"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get KPI history."""
    result = await db.execute(
        select(KPIHistory)
        .where(KPIHistory.kpi_id == kpi_id)
        .order_by(KPIHistory.recorded_at.desc())
        .limit(limit)
    )
    history = result.scalars().all()
    
    return history


@router.post("/{kpi_id}/history")
async def add_kpi_value(
    kpi_id: int,
    history_data: KPIHistoryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_minimum_role(UserRole.ANALYST))
):
    """Add a new value to KPI history."""
    # Check if KPI exists
    result = await db.execute(select(KPI).where(KPI.id == kpi_id))
    kpi = result.scalar_one_or_none()
    
    if not kpi:
        raise HTTPException(status_code=404, detail="KPI not found")
    
    # Create history record
    history = KPIHistory(
        kpi_id=kpi_id,
        value=history_data.value,
        notes=history_data.notes
    )
    
    db.add(history)
    
    # Update current value
    kpi.current_value = history_data.value
    
    await db.commit()
    await db.refresh(history)
    
    return history


@router.get("/{kpi_id}/analytics")
async def get_kpi_analytics(
    kpi_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get AI-powered analytics for a KPI."""
    analytics = await ai_service.analyze_kpi_trends(kpi_id, db)
    
    if "error" in analytics:
        raise HTTPException(status_code=404, detail=analytics["error"])
    
    return analytics 