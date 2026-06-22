"""Analytics endpoints for KPI overviews, trends, queries, and reports."""
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload
from pydantic import BaseModel

from app.core.database import get_db
from app.core.security import get_current_active_user, require_role, UserRole
from app.models.kpi import KPI, KPIHistory
from app.models.dashboard import Dashboard
from app.models.user import User
from app.services.ai_service import AIService
from app.services.embedding_service import EmbeddingService

router = APIRouter()


class AnalyticsQuery(BaseModel):
    """Request body for filtering analytics data by organization and date range."""
    organization_id: int
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    kpi_categories: Optional[List[str]] = None


class NaturalLanguageQuery(BaseModel):
    """Request body for a natural language query against KPI data."""
    query: str
    organization_id: int
    context: Optional[str] = None


class TrendAnalysisRequest(BaseModel):
    """Request body for analyzing trends across a set of KPIs."""
    kpi_ids: List[int]
    time_period: str = "30d"  # 7d, 30d, 90d, 1y
    organization_id: int


class ReportGenerationRequest(BaseModel):
    """Request body for generating a comprehensive analytics report."""
    report_type: str  # "executive", "operational", "financial", "custom"
    organization_id: int
    kpi_categories: Optional[List[str]] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    include_recommendations: bool = True


@router.get("/overview/{organization_id}")
async def get_analytics_overview(
    organization_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get comprehensive analytics overview for an organization."""
    # Verify organization access
    if current_user.role != UserRole.ADMIN:
        # Check if user belongs to organization
        from app.models.organization import UserOrganization
        result = await db.execute(
            select(UserOrganization).where(
                and_(
                    UserOrganization.organization_id == organization_id,
                    UserOrganization.user_id == current_user.id
                )
            )
        )
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=403, detail="Access denied")

    # Get KPI statistics
    result = await db.execute(
        select(func.count(KPI.id)).where(KPI.organization_id == organization_id)
    )
    total_kpis = result.scalar()

    # Get KPIs by category
    result = await db.execute(
        select(KPI.category, func.count(KPI.id)).where(
            KPI.organization_id == organization_id
        ).group_by(KPI.category)
    )
    kpis_by_category = dict(result.all())

    # Get recent KPI updates
    result = await db.execute(
        select(KPIHistory).options(
            selectinload(KPIHistory.kpi)
        ).where(
            KPI.organization_id == organization_id
        ).join(KPI).order_by(KPIHistory.created_at.desc()).limit(10)
    )
    recent_updates = result.scalars().all()

    # Get dashboard statistics
    result = await db.execute(
        select(func.count(Dashboard.id)).where(
            Dashboard.organization_id == organization_id
        )
    )
    total_dashboards = result.scalar()

    # Calculate KPI health score
    result = await db.execute(
        select(KPI).where(KPI.organization_id == organization_id)
    )
    kpis = result.scalars().all()

    health_score = 0
    if kpis:
        healthy_kpis = sum(1 for kpi in kpis if kpi.current_value and kpi.target_value)
        if healthy_kpis > 0:
            on_target_kpis = sum(
                1 for kpi in kpis
                if kpi.current_value and kpi.target_value and kpi.current_value >= kpi.target_value
            )
            health_score = (on_target_kpis / healthy_kpis) * 100

    return {
        "total_kpis": total_kpis,
        "kpis_by_category": kpis_by_category,
        "total_dashboards": total_dashboards,
        "health_score": round(health_score, 2),
        "recent_updates": [
            {
                "kpi_name": update.kpi.name,
                "old_value": update.old_value,
                "new_value": update.new_value,
                "updated_at": update.created_at
            }
            for update in recent_updates
        ]
    }


@router.post("/trends")
async def analyze_kpi_trends(
    request: TrendAnalysisRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Analyze trends for specific KPIs."""
    # Verify organization access
    if current_user.role != UserRole.ADMIN:
        from app.models.organization import UserOrganization
        result = await db.execute(
            select(UserOrganization).where(
                and_(
                    UserOrganization.organization_id == request.organization_id,
                    UserOrganization.user_id == current_user.id
                )
            )
        )
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=403, detail="Access denied")

    # Get KPI history for the specified KPIs
    result = await db.execute(
        select(KPIHistory).options(
            selectinload(KPIHistory.kpi)
        ).where(
            KPIHistory.kpi_id.in_(request.kpi_ids)
        ).order_by(KPIHistory.created_at)
    )
    history_records = result.scalars().all()

    # Group by KPI
    kpi_trends = {}
    for record in history_records:
        if record.kpi_id not in kpi_trends:
            kpi_trends[record.kpi_id] = {
                "kpi_name": record.kpi.name,
                "category": record.kpi.category,
                "unit": record.kpi.unit,
                "target_value": record.kpi.target_value,
                "data_points": []
            }

        kpi_trends[record.kpi_id]["data_points"].append({
            "value": record.new_value,
            "date": record.created_at
        })

    # Use AI service to analyze trends
    ai_service = AIService()
    trend_analysis = await ai_service.analyze_kpi_trends(
        kpi_trends, request.time_period
    )

    return {
        "kpi_trends": kpi_trends,
        "ai_analysis": trend_analysis
    }


@router.post("/query")
async def natural_language_query(
    query: NaturalLanguageQuery,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Answer natural language queries about KPI data."""
    # Verify organization access
    if current_user.role != UserRole.ADMIN:
        from app.models.organization import UserOrganization
        result = await db.execute(
            select(UserOrganization).where(
                and_(
                    UserOrganization.organization_id == query.organization_id,
                    UserOrganization.user_id == current_user.id
                )
            )
        )
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=403, detail="Access denied")

    # Get relevant KPI data
    result = await db.execute(
        select(KPI).options(
            selectinload(KPI.history)
        ).where(KPI.organization_id == query.organization_id)
    )
    kpis = result.scalars().all()

    # Use AI service to answer the query
    ai_service = AIService()
    answer = await ai_service.answer_natural_language_query(
        query.query, kpis, query.context
    )

    return {
        "query": query.query,
        "answer": answer,
        "data_sources": [kpi.name for kpi in kpis]
    }


@router.post("/recommendations")
async def get_kpi_recommendations(
    organization_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get AI-powered KPI recommendations for an organization."""
    # Verify organization access
    if current_user.role != UserRole.ADMIN:
        from app.models.organization import UserOrganization
        result = await db.execute(
            select(UserOrganization).where(
                and_(
                    UserOrganization.organization_id == organization_id,
                    UserOrganization.user_id == current_user.id
                )
            )
        )
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=403, detail="Access denied")

    # Use AI service to generate recommendations (it queries the org's KPIs itself)
    ai_service = AIService()
    recommendations = await ai_service.generate_kpi_recommendations(organization_id, db)

    return recommendations


@router.post("/report")
async def generate_report(
    request: ReportGenerationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ANALYST))
):
    """Generate comprehensive AI-powered reports."""
    # Verify organization access
    if current_user.role != UserRole.ADMIN:
        from app.models.organization import UserOrganization
        result = await db.execute(
            select(UserOrganization).where(
                and_(
                    UserOrganization.organization_id == request.organization_id,
                    UserOrganization.user_id == current_user.id
                )
            )
        )
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=403, detail="Access denied")

    # Get KPI data based on filters
    query = select(KPI).options(selectinload(KPI.history)).where(
        KPI.organization_id == request.organization_id
    )

    if request.kpi_categories:
        query = query.where(KPI.category.in_(request.kpi_categories))

    result = await db.execute(query)
    kpis = result.scalars().all()

    # Get dashboard data
    result = await db.execute(
        select(Dashboard).where(Dashboard.organization_id == request.organization_id)
    )
    dashboards = result.scalars().all()

    # Use AI service to generate report
    ai_service = AIService()
    report = await ai_service.generate_comprehensive_report(
        kpis, dashboards, request.report_type, request.include_recommendations
    )

    return {
        "report_type": request.report_type,
        "generated_at": datetime.utcnow(),
        "data_period": {
            "start_date": request.start_date,
            "end_date": request.end_date
        },
        "report_content": report
    }


@router.get("/performance/{organization_id}")
async def get_performance_metrics(
    organization_id: int,
    period: str = Query("30d", regex="^(7d|30d|90d|1y)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get performance metrics and comparisons."""
    # Verify organization access
    if current_user.role != UserRole.ADMIN:
        from app.models.organization import UserOrganization
        result = await db.execute(
            select(UserOrganization).where(
                and_(
                    UserOrganization.organization_id == organization_id,
                    UserOrganization.user_id == current_user.id
                )
            )
        )
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=403, detail="Access denied")

    # Calculate date range
    end_date = datetime.utcnow()
    if period == "7d":
        start_date = end_date - timedelta(days=7)
    elif period == "30d":
        start_date = end_date - timedelta(days=30)
    elif period == "90d":
        start_date = end_date - timedelta(days=90)
    else:  # 1y
        start_date = end_date - timedelta(days=365)

    # Get KPI performance data
    result = await db.execute(
        select(KPI).options(selectinload(KPI.history)).where(
            KPI.organization_id == organization_id
        )
    )
    kpis = result.scalars().all()

    # Calculate performance metrics
    performance_data = []
    for kpi in kpis:
        if kpi.history:
            # Get values within the period
            period_values = [
                h.new_value for h in kpi.history
                if start_date <= h.created_at <= end_date and h.new_value is not None
            ]

            if period_values:
                current_value = period_values[-1]
                avg_value = sum(period_values) / len(period_values)
                min_value = min(period_values)
                max_value = max(period_values)

                # Calculate trend
                if len(period_values) >= 2:
                    trend = (period_values[-1] - period_values[0]) / len(period_values)
                else:
                    trend = 0

                # Calculate target achievement
                target_achievement = None
                if kpi.target_value:
                    target_achievement = (current_value / kpi.target_value) * 100

                performance_data.append({
                    "kpi_id": kpi.id,
                    "kpi_name": kpi.name,
                    "category": kpi.category,
                    "current_value": current_value,
                    "average_value": avg_value,
                    "min_value": min_value,
                    "max_value": max_value,
                    "trend": trend,
                    "target_achievement": target_achievement,
                    "unit": kpi.unit
                })

    return {
        "period": period,
        "start_date": start_date,
        "end_date": end_date,
        "performance_metrics": performance_data,
        "summary": {
            "total_kpis": len(performance_data),
            "on_target_kpis": len([
                p for p in performance_data
                if p["target_achievement"] and p["target_achievement"] >= 100
            ]),
            "improving_kpis": len([p for p in performance_data if p["trend"] > 0]),
            "declining_kpis": len([p for p in performance_data if p["trend"] < 0])
        }
    }


@router.get("/search")
async def search_analytics(
    query: str = Query(..., min_length=1),
    organization_id: int = Query(...),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Search through KPI data and analytics using semantic search."""
    # Verify organization access
    if current_user.role != UserRole.ADMIN:
        from app.models.organization import UserOrganization
        result = await db.execute(
            select(UserOrganization).where(
                and_(
                    UserOrganization.organization_id == organization_id,
                    UserOrganization.user_id == current_user.id
                )
            )
        )
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=403, detail="Access denied")

    # Use embedding service for semantic search
    embedding_service = EmbeddingService()
    search_results = await embedding_service.semantic_search(
        query, organization_id, limit, db
    )

    return {
        "query": query,
        "results": search_results,
        "total_results": len(search_results)
    }
